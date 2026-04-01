"""Tools để tương tác với mem0 long-term memory."""
import structlog
from google.adk.tools import ToolContext

from app.core.database import get_mem0_client
from app.repositories.mem0_repo import Mem0Repository

logger = structlog.get_logger(__name__)


def retrieve_memories(query: str, tool_context: ToolContext) -> dict:
    """
    Lấy các ký ức liên quan của người dùng từ long-term memory.

    Args:
        query: Câu hỏi hoặc chủ đề cần tìm ký ức liên quan.
        tool_context: ADK tool context.

    Returns:
        Dict với danh sách memories liên quan đến query.
    """
    user_id = tool_context.state.get("user_id", "default_user")

    try:
        repo = Mem0Repository(get_mem0_client())
        memories = repo.search_memory(query=query, user_id=user_id, limit=5)

        if not memories:
            return {"found": False, "memories": [], "message": "Không có ký ức liên quan."}

        formatted = [
            {
                "memory": m.get("memory", ""),
                "id": m.get("id", ""),
                "score": round(m.get("score", 0), 4) if m.get("score") else None,
            }
            for m in memories
        ]

        logger.info("memories_retrieved", user_id=user_id, count=len(formatted))
        return {"found": True, "memories": formatted, "count": len(formatted)}

    except Exception as e:
        logger.error("retrieve_memories_error", error=str(e))
        return {"found": False, "memories": [], "message": f"Lỗi lấy memory: {str(e)}"}


def store_memory(content: str, tool_context: ToolContext) -> dict:
    """
    Lưu thông tin quan trọng vào long-term memory của người dùng.

    Args:
        content: Nội dung cần ghi nhớ (preferences, facts, v.v.).
        tool_context: ADK tool context.

    Returns:
        Dict xác nhận đã lưu thành công.
    """
    user_id = tool_context.state.get("user_id", "default_user")

    try:
        repo = Mem0Repository(get_mem0_client())
        messages = [{"role": "user", "content": content}]
        repo.add_memory(messages=messages, user_id=user_id)

        logger.info("memory_stored", user_id=user_id)
        return {"success": True, "message": "Đã lưu vào long-term memory."}

    except Exception as e:
        logger.error("store_memory_error", error=str(e))
        return {"success": False, "message": f"Lỗi lưu memory: {str(e)}"}
