"""
ContextFilterPlugin: Giới hạn context gửi lên LLM, tự động tóm tắt khi hội thoại quá dài.

Luồng xử lý:
1. len(contents) <= max_context_messages  → không làm gì
2. len(contents) >= summary_threshold hoặc đã có summary → summarization path:
   - Gọi Gemini tóm tắt các messages cũ (ngoài keep_recent)
   - Lưu summary vào session state (ADK tự persist vào DynamoDB)
   - Inject [summary_msg + summary_ack] + recent_messages vào llm_request
3. Fallback (chưa đủ threshold, chưa có summary) → truncate đơn giản
"""

import structlog
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai.types import Content, Part

from app.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)


async def context_filter_before_model(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    """
    Callback chạy trước khi gọi LLM.
    Tự động tóm tắt context nếu quá dài.
    """
    settings = get_settings()
    max_ctx: int = callback_context.state.get(
        "max_context_messages", settings.max_context_messages
    )

    contents = llm_request.contents or []
    n = len(contents)

    if n <= max_ctx:
        return None  # vẫn trong giới hạn, không làm gì

    existing_summary: str = callback_context.state.get("conversation_summary", "")

    # Dùng summarization khi đã có summary hoặc vượt quá threshold
    if n >= settings.summary_threshold or existing_summary:
        await _apply_summarization(
            callback_context, llm_request, contents, existing_summary, settings
        )
    else:
        # Chưa đủ để summarize → truncate đơn giản
        llm_request.contents = contents[-max_ctx:]
        logger.info("context_truncated", original=n, kept=max_ctx)

    return None


async def _apply_summarization(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
    contents: list,
    existing_summary: str,
    settings: Settings,
) -> None:
    """Tóm tắt messages cũ, inject summary + recent vào llm_request."""
    n = len(contents)
    keep_recent = settings.summary_keep_recent
    summary_covered: int = callback_context.state.get("summary_covered_count", 0)
    uncovered = n - summary_covered

    # Re-generate summary khi có đủ messages mới chưa được tóm tắt
    resummary_trigger = settings.summary_threshold - keep_recent

    if uncovered > resummary_trigger:
        to_summarize = contents[: n - keep_recent]
        try:
            new_summary = await _generate_summary(to_summarize, existing_summary, settings)
            callback_context.state["conversation_summary"] = new_summary
            callback_context.state["summary_covered_count"] = n - keep_recent
            existing_summary = new_summary
            logger.info(
                "summary_generated",
                covered=n - keep_recent,
                keep_recent=keep_recent,
            )
        except Exception as exc:
            logger.warning("summarization_failed", error=str(exc))
            # Fallback: truncate đơn giản
            llm_request.contents = contents[-settings.max_context_messages :]
            return

    if existing_summary:
        recent = list(contents[-keep_recent:])
        # Gemini yêu cầu alternating roles; đảm bảo recent bắt đầu bằng "user"
        while recent and recent[0].role != "user":
            recent = recent[1:]

        summary_msg = Content(
            role="user",
            parts=[Part.from_text(f"[Tóm tắt cuộc hội thoại trước]\n{existing_summary}")],
        )
        summary_ack = Content(
            role="model",
            parts=[Part.from_text("Đã hiểu. Tôi sẽ tiếp tục dựa trên tóm tắt này.")],
        )
        llm_request.contents = [summary_msg, summary_ack] + recent
        logger.info(
            "context_with_summary",
            original=n,
            after=len(llm_request.contents),
        )
    else:
        # Threshold đạt nhưng summarization chưa chạy → truncate
        llm_request.contents = contents[-settings.max_context_messages :]


async def _generate_summary(
    contents: list,
    existing_summary: str,
    settings: Settings,
) -> str:
    """Gọi Gemini để tóm tắt danh sách Content objects."""
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)

    lines: list[str] = []
    if existing_summary:
        lines.append(f"=== Tóm tắt trước đó ===\n{existing_summary}\n")
        lines.append("=== Các tin nhắn tiếp theo ===")

    for c in contents:
        role_label = "Người dùng" if c.role == "user" else "Trợ lý"
        text = " ".join(p.text for p in (c.parts or []) if p.text)
        if text.strip():
            lines.append(f"{role_label}: {text.strip()}")

    transcript = "\n".join(lines)

    prompt = (
        "Tóm tắt ngắn gọn cuộc hội thoại dưới đây. "
        "Giữ lại: thông tin quan trọng, quyết định đã đưa ra, "
        "ngữ cảnh cần thiết để tiếp tục hội thoại, tên/số liệu/chi tiết quan trọng.\n\n"
        f"{transcript}"
    )

    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
    )
    return response.text or ""


def context_filter_after_model(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Callback sau khi nhận response từ LLM (dùng để log/audit)."""
    return None
