"""Tool để tìm kiếm tài liệu trong Qdrant (RAG retrieval)."""
import structlog
from google.adk.tools import ToolContext

from app.core.config import get_settings
from app.core.database import get_qdrant_client
from app.repositories.qdrant_repo import QdrantRepository
from app.utils.gemini_utils import get_embedding

logger = structlog.get_logger(__name__)


def search_documents(query: str, tool_context: ToolContext) -> dict:
    """
    Tìm kiếm tài liệu liên quan trong vector database dựa trên câu hỏi.

    Args:
        query: Câu hỏi hoặc từ khóa tìm kiếm.
        tool_context: ADK tool context chứa session state.

    Returns:
        Dict với danh sách các đoạn tài liệu liên quan và nguồn trích dẫn.
    """
    settings = get_settings()
    user_id = tool_context.state.get("user_id")

    try:
        query_vector = get_embedding(query)
        repo = QdrantRepository(get_qdrant_client())
        results = repo.search(
            query_vector=query_vector,
            user_id=user_id,
            top_k=settings.top_k_results,
        )

        if not results:
            return {"found": False, "message": "Không tìm thấy tài liệu liên quan.", "results": []}

        formatted = [
            {
                "text": r["text"],
                "source": r["filename"],
                "document_id": r["document_id"],
                "relevance_score": round(r["score"], 4),
            }
            for r in results
        ]

        logger.info("qdrant_search_done", user_id=user_id, query=query, count=len(formatted))
        return {"found": True, "results": formatted, "count": len(formatted)}

    except Exception as e:
        logger.error("qdrant_search_error", error=str(e))
        return {"found": False, "message": f"Lỗi tìm kiếm: {str(e)}", "results": []}
