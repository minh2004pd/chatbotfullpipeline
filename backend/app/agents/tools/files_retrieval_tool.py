"""Tool để list các tài liệu đã upload của người dùng."""

import structlog
from google.adk.tools import ToolContext

from app.core.database import get_qdrant_client
from app.repositories.qdrant_repo import QdrantRepository

logger = structlog.get_logger(__name__)


def list_user_documents(tool_context: ToolContext) -> dict:
    """
    Liệt kê tất cả tài liệu (PDF, file) mà người dùng đã upload vào hệ thống.

    Dùng khi: người dùng hỏi "tôi có những file gì?", "danh sách tài liệu", hoặc khi
    search_documents trả về rỗng và cần xác định xem dữ liệu có tồn tại không.
    Không dùng để tìm nội dung bên trong tài liệu — hãy dùng search_documents cho việc đó.

    Args:
        tool_context: ADK tool context chứa session state.

    Returns:
        Dict với danh sách filename và document_id của từng tài liệu đã upload.
        Trả về found=False nếu chưa có tài liệu nào.
    """
    user_id = tool_context.state.get("user_id", "default_user")

    try:
        repo = QdrantRepository(get_qdrant_client())
        documents = repo.list_documents(user_id=user_id)

        if not documents:
            return {
                "found": False,
                "documents": [],
                "message": "Bạn chưa upload tài liệu nào.",
            }

        logger.info("documents_listed", user_id=user_id, count=len(documents))
        return {
            "found": True,
            "documents": [
                {"document_id": d["document_id"], "filename": d["filename"]} for d in documents
            ],
            "count": len(documents),
        }

    except Exception as e:
        logger.error("list_documents_error", error=str(e))
        return {"found": False, "documents": [], "message": f"Lỗi liệt kê tài liệu: {str(e)}"}
