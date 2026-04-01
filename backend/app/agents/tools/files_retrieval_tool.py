"""Tool để list các tài liệu đã upload của người dùng."""

import structlog
from google.adk.tools import ToolContext

from app.core.database import get_qdrant_client
from app.repositories.qdrant_repo import QdrantRepository

logger = structlog.get_logger(__name__)


def list_user_documents(tool_context: ToolContext) -> dict:
    """
    Truy xuất danh sách tất cả các tài liệu (PDF) mà người dùng hiện tại đã tải lên và lưu trữ trong hệ thống.

    HƯỚNG DẪN SỬ DỤNG CHO AI:
    - Đây là công cụ ưu tiên để xác định phạm vi kiến thức.
    - Hãy gọi công cụ này khi người dùng hỏi về danh sách file, hoặc khi bạn cần 'document_id' chính xác để phục vụ việc tìm kiếm chuyên sâu trong một file cụ thể.
    - Nếu người dùng hỏi về một chủ đề mà bạn không chắc nằm ở file nào, hãy chạy lệnh này để xem danh sách tên file gợi ý.

    Args:
        tool_context (ToolContext): Đối tượng ngữ cảnh của hệ thống, chứa thông tin định danh người dùng (user_id) và trạng thái phiên làm việc.

    Returns:
        dict: Một dictionary chứa kết quả:
            - 'found' (bool): True nếu có tài liệu, False nếu thư viện trống.
            - 'documents' (list): Danh sách các object gồm 'document_id' (ID duy nhất) và 'filename' (tên file gốc).
            - 'count' (int): Tổng số lượng tài liệu tìm thấy.
            - 'message' (str): Thông báo trạng thái hoặc hướng dẫn cho người dùng.
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
