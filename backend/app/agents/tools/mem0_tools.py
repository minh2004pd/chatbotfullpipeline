"""Tools để tương tác với mem0 long-term memory."""

import structlog
from google.adk.tools import ToolContext

from app.agents.tools.utils import get_user_id
from app.core.config import get_settings
from app.core.database import get_mem0_client
from app.repositories.mem0_repo import Mem0Repository

logger = structlog.get_logger(__name__)

# Số memories tối thiểu trả về sau reranking
_MEMORY_RETURN_LIMIT = 7


def retrieve_memories(query: str, tool_context: ToolContext) -> dict:
    """
    Lấy thông tin cá nhân và sở thích của người dùng từ long-term memory.

    Dùng khi người dùng nhắc đến thông tin đã chia sẻ trước đây ("như tôi đã nói",
    "bạn có nhớ không"), hỏi về sở thích/thói quen cá nhân, hoặc khi cần personalize
    câu trả lời dựa trên context lịch sử. Không dùng để tìm nội dung tài liệu hay meeting.

    Args:
        query: Chủ đề hoặc thông tin cần tìm trong memory của người dùng.
        tool_context: ADK tool context.

    Returns:
        Dict với danh sách memories liên quan, được rerank theo relevance score (top-7).
    """
    settings = get_settings()
    user_id = get_user_id(tool_context)

    try:
        repo = Mem0Repository(get_mem0_client())
        # Search nhiều hơn → rerank → trả về top tốt nhất
        raw_memories = repo.search_memory(
            query=query,
            user_id=user_id,
            limit=settings.memory_search_limit,
        )

        if not raw_memories:
            return {"found": False, "memories": [], "message": "Không có ký ức liên quan."}

        # Rerank: sort descending by score (mem0 đã tính vector similarity)
        ranked = sorted(raw_memories, key=lambda m: m.get("score", 0.0), reverse=True)
        top = ranked[:_MEMORY_RETURN_LIMIT]

        formatted = [
            {
                "memory": m.get("memory", ""),
                "id": m.get("id", ""),
                "score": round(m.get("score", 0.0), 4) if m.get("score") is not None else None,
            }
            for m in top
        ]

        logger.info(
            "memories_retrieved",
            user_id=user_id,
            searched=len(raw_memories),
            returned=len(formatted),
        )
        return {"found": True, "memories": formatted, "count": len(formatted)}

    except Exception as e:
        logger.error("retrieve_memories_error", error=str(e))
        return {"found": False, "memories": [], "message": f"Lỗi lấy memory: {str(e)}"}


def store_memory(content: str, tool_context: ToolContext) -> dict:
    """
    Lưu thông tin cá nhân quan trọng vào long-term memory của người dùng.

    Dùng khi: người dùng yêu cầu nhớ ("hãy ghi nhớ...", "lưu lại..."), hoặc người dùng
    chia sẻ thông tin cá nhân đáng nhớ (sở thích, vai trò, dự án đang làm, preference).
    Không dùng để lưu kết quả tìm kiếm hay nội dung tài liệu — chỉ lưu thông tin về người dùng.

    Args:
        content: Thông tin cần lưu, viết dưới dạng fact ngắn gọn.
        tool_context: ADK tool context.

    Returns:
        Dict xác nhận đã lưu thành công hay thất bại.
    """
    user_id = get_user_id(tool_context)

    try:
        repo = Mem0Repository(get_mem0_client())
        messages = [{"role": "user", "content": content}]
        repo.add_memory(messages=messages, user_id=user_id)

        logger.info("memory_stored", user_id=user_id)
        return {"success": True, "message": "Đã lưu vào long-term memory."}

    except Exception as e:
        logger.error("store_memory_error", error=str(e))
        return {"success": False, "message": f"Lỗi lưu memory: {str(e)}"}
