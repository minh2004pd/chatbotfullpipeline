"""Tool để ingest PDF files vào Qdrant."""

import structlog
from google.adk.tools import ToolContext

from app.core.config import get_settings
from app.core.database import get_qdrant_client
from app.repositories.qdrant_repo import QdrantRepository
from app.utils.file_utils import chunk_text, extract_pdf_text
from app.utils.gemini_utils import get_embeddings_batch

logger = structlog.get_logger(__name__)


def ingest_pdf_artifact(artifact_name: str, tool_context: ToolContext) -> dict:
    """
    Thực hiện quy trình xử lý nội dung (Ingestion): Trích xuất văn bản, chia nhỏ (chunking) và vector hóa file PDF để đưa vào cơ sở dữ liệu RAG.

    HƯỚNG DẪN SỬ DỤNG CHO AI (QUAN TRỌNG):
    - BẮT BUỘC gọi công cụ này ngay lập tức khi người dùng vừa tải lên một file PDF mới (artifact).
    - Bạn KHÔNG THỂ sử dụng 'search_documents' để tìm nội dung trong file đó nếu chưa chạy 'ingest_pdf_artifact' thành công.
    - Sau khi hoàn tất, hãy thông báo cho người dùng rằng tài liệu đã sẵn sàng để tra cứu.

    Args:
        artifact_name (str): Tên định danh của artifact (file đính kèm) trong phiên hội thoại hiện tại.
        tool_context (ToolContext): Đối tượng ngữ cảnh hệ thống, dùng để tải file từ bộ nhớ tạm và lưu trữ thông tin vào database của người dùng.

    Returns:
        dict: Kết quả của quá trình nạp dữ liệu:
            - 'success' (bool): Trạng thái thực hiện (Thành công/Thất bại).
            - 'chunk_count' (int): Số lượng đoạn văn bản đã được vector hóa (cho biết độ dày của dữ liệu).
            - 'document_id' (str): ID định danh tài liệu trong hệ thống để sử dụng cho việc truy vấn sau này.
            - 'message' (str): Mô tả chi tiết lỗi nếu 'success' là False.
    """
    settings = get_settings()
    user_id = tool_context.state.get("user_id", "default_user")
    document_id = tool_context.state.get("document_id", artifact_name)

    try:
        # Lấy artifact từ ADK session
        artifact = tool_context.load_artifact(artifact_name)
        if artifact is None:
            return {"success": False, "message": f"Artifact '{artifact_name}' không tồn tại."}

        pdf_bytes = artifact.inline_data.data
        text = extract_pdf_text(pdf_bytes)

        if not text.strip():
            return {"success": False, "message": "PDF không có nội dung text."}

        chunks = chunk_text(
            text,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

        embeddings = get_embeddings_batch(chunks)
        repo = QdrantRepository(get_qdrant_client())
        count = repo.upsert_chunks(
            chunks=chunks,
            embeddings=embeddings,
            document_id=document_id,
            filename=artifact_name,
            user_id=user_id,
        )

        logger.info("pdf_ingested", artifact=artifact_name, chunks=count)
        return {"success": True, "chunk_count": count, "document_id": document_id}

    except Exception as e:
        logger.error("pdf_ingestion_error", artifact=artifact_name, error=str(e))
        return {"success": False, "message": f"Lỗi ingest PDF: {str(e)}"}
