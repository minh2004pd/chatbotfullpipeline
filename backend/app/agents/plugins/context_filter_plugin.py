"""
ContextFilterPlugin: Giới hạn số lượng messages được gửi lên LLM
để tránh token explosion trong long conversations.
"""
import structlog
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse

logger = structlog.get_logger(__name__)


def context_filter_before_model(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmRequest | None:
    """
    Callback chạy trước khi gọi LLM.
    Giới hạn lịch sử hội thoại để tránh context quá dài.
    """
    max_messages: int = callback_context.state.get("max_context_messages", 20)

    if not llm_request.contents:
        return None

    # Luôn giữ system instruction, chỉ filter user/assistant messages
    if len(llm_request.contents) > max_messages:
        # Giữ lại max_messages cuối cùng
        original_count = len(llm_request.contents)
        llm_request.contents = llm_request.contents[-max_messages:]
        logger.info(
            "context_filtered",
            original=original_count,
            kept=len(llm_request.contents),
            max_messages=max_messages,
        )

    return None  # None = dùng llm_request đã modify in-place


def context_filter_after_model(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Callback sau khi nhận response từ LLM (có thể dùng để log/audit)."""
    return None
