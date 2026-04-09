"""
ContextFilterPlugin: Giới hạn context gửi lên LLM, tự động tóm tắt khi hội thoại quá dài.

Chiến lược:
1. n <= max_context_messages: pass through
2. n > max_context_messages: summarization path
   - Nếu cần re-summarize (uncovered > trigger): chạy summary ngay (blocking, lần đầu)
     hoặc fire-and-forget background task (lần sau, khi đã có summary cũ dùng được)
   - Inject [structured_summary + ack] + recent_keep_recent messages
   - Summary dùng model nhẹ (summary_model) để giảm latency

Background optimization:
   - Lần đầu chưa có summary: phải chờ (blocking) để có context cho LLM
   - Lần sau đã có summary cũ: inject summary cũ ngay, chạy re-summarize ở background
     → LLM không bị block, summary mới sẵn sàng cho turn tiếp theo
"""

import asyncio

import structlog
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai.types import Content, Part

from app.core.config import get_settings
from app.core.llm_config import get_llm_config
from app.utils.gemini_utils import _with_retry, get_genai_client

logger = structlog.get_logger(__name__)


async def context_filter_before_model(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    """Callback chạy trước khi gọi LLM. Tự động tóm tắt context nếu quá dài."""
    settings = get_settings()
    max_ctx: int = callback_context.state.get("max_context_messages", settings.max_context_messages)

    contents = llm_request.contents or []
    n = len(contents)

    if n <= max_ctx:
        return None

    existing_summary: str = callback_context.state.get("conversation_summary", "")
    await _apply_summarization(callback_context, llm_request, contents, existing_summary)
    return None


async def _apply_summarization(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
    contents: list,
    existing_summary: str,
) -> None:
    """Tóm tắt messages cũ, inject summary + recent vào llm_request.

    Nếu đã có summary cũ dùng được: inject ngay (không block), re-summarize ở background.
    Nếu chưa có summary: phải chờ để LLM có đủ context.
    """
    settings = get_settings()
    n = len(contents)
    keep_recent = settings.summary_keep_recent
    summary_covered: int = callback_context.state.get("summary_covered_count", 0)
    uncovered = n - summary_covered
    resummary_trigger = settings.summary_threshold - keep_recent

    needs_resummary = uncovered > resummary_trigger

    if needs_resummary:
        if existing_summary:
            # Đã có summary cũ → inject ngay để không block LLM
            # Re-summarize chạy background, sẵn sàng cho turn tiếp theo
            _schedule_background_summary(
                callback_context, contents, existing_summary, n, keep_recent
            )
        else:
            # Chưa có summary → buộc phải chờ lần đầu
            to_summarize = contents[: n - keep_recent]
            try:
                new_summary = await _generate_summary(to_summarize, existing_summary)
                callback_context.state["conversation_summary"] = new_summary
                callback_context.state["summary_covered_count"] = n - keep_recent
                existing_summary = new_summary
                logger.info("summary_generated_blocking", covered=n - keep_recent)
            except Exception as exc:
                logger.warning("summarization_failed", error=str(exc))
                llm_request.contents = contents[-settings.max_context_messages :]
                return

    if existing_summary:
        recent = list(contents[-keep_recent:])
        # ADK yêu cầu alternating roles; đảm bảo bắt đầu từ "user"
        while recent and recent[0].role != "user":
            recent = recent[1:]

        summary_msg = Content(
            role="user",
            parts=[Part.from_text(text=f"[Tóm tắt trước đó]\n{existing_summary}")],
        )
        summary_ack = Content(
            role="model",
            parts=[Part.from_text(text="Đã hiểu. Tôi sẽ tiếp tục dựa trên tóm tắt.")],
        )
        llm_request.contents = [summary_msg, summary_ack] + recent
        logger.info("context_with_summary", original=n, after=len(llm_request.contents))
    else:
        llm_request.contents = contents[-settings.max_context_messages :]


def _schedule_background_summary(
    callback_context: CallbackContext,
    contents: list,
    existing_summary: str,
    n: int,
    keep_recent: int,
) -> None:
    """Fire-and-forget: chạy re-summarize ở background, cập nhật session state khi xong."""
    to_summarize = contents[: n - keep_recent]

    async def _run() -> None:
        try:
            new_summary = await _generate_summary(to_summarize, existing_summary)
            callback_context.state["conversation_summary"] = new_summary
            callback_context.state["summary_covered_count"] = n - keep_recent
            logger.info("summary_generated_background", covered=n - keep_recent)
        except Exception as exc:
            logger.warning("background_summary_failed", error=str(exc))

    asyncio.ensure_future(_run())


async def _generate_summary(contents: list, existing_summary: str) -> str:
    """Tóm tắt danh sách Content objects bằng Gemini (model nhẹ, structured output)."""
    config = get_llm_config()
    client = get_genai_client()

    lines: list[str] = []
    if existing_summary:
        lines.append(f"=== Tóm tắt trước đó ===\n{existing_summary}\n")
        lines.append("=== Các tin nhắn tiếp theo ===")

    for content in contents:
        role_label = "Người dùng" if content.role == "user" else "Trợ lý"
        text_parts = [part.text for part in (content.parts or []) if part.text]
        text = " ".join(text_parts)
        if text.strip():
            lines.append(f"{role_label}: {text.strip()}")

    transcript = "\n".join(lines)
    prompt = (
        "Tóm tắt cuộc hội thoại dưới đây theo đúng cấu trúc sau. "
        "Không bịa thông tin, chỉ ghi những gì có trong hội thoại.\n\n"
        "## Quyết định & Cam kết\n"
        "- Liệt kê các quyết định, cam kết, hành động đã được xác nhận\n\n"
        "## Câu hỏi & Giải đáp chính\n"
        "- Người dùng hỏi gì và đã được giải đáp chưa\n\n"
        "## Ngữ cảnh kỹ thuật\n"
        "- Tên, số liệu, công nghệ, constraint quan trọng\n\n"
        "## Follow-up chưa giải quyết\n"
        "- Câu hỏi còn mở, vấn đề chưa xong\n\n"
        f"---\n{transcript}"
    )

    async def _call():
        return await client.aio.models.generate_content(
            model=config.llm.summary_model,
            contents=prompt,
        )

    response = await _with_retry(_call)
    return response.text or ""


def context_filter_after_model(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Callback sau khi nhận response từ LLM (dùng để log/audit)."""
    return None
