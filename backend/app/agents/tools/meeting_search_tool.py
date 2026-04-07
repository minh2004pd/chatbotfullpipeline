"""ADK Tool: tìm kiếm transcript meeting trong Qdrant (voice → text RAG)."""

import structlog
from google.adk.tools import ToolContext

from app.core.config import get_settings
from app.core.database import get_qdrant_client
from app.services.transcript_rag_service import TranscriptRAGService
from app.utils.gemini_utils import get_query_embedding

logger = structlog.get_logger(__name__)


def search_meeting_transcripts(query: str, tool_context: ToolContext) -> str:
    """Tìm kiếm trong transcript các cuộc họp đã ghi âm và dừng (transcription đã index vào kho).

    Dùng khi người dùng hỏi về nội dung họp, lời thoại, tóm tắt meeting, quyết định, hoặc ai nói gì.
    Không dùng cho tài liệu PDF/file upload — với tài liệu hãy gọi `search_documents`.

    Args:
        query: Câu hỏi hoặc từ khóa tìm trong transcript.

    Returns:
        Các đoạn transcript liên quan kèm tên meeting, speaker (nếu có), điểm khớp.
    """
    settings = get_settings()
    user_id = tool_context.state.get("user_id", "default_user")

    try:
        rag_service = TranscriptRAGService(get_qdrant_client())
        query_vector = get_query_embedding(query)
        results = rag_service.search(
            query_vector=query_vector,
            user_id=user_id,
            top_k=settings.top_k_results,
        )

        if not results:
            return "Không tìm thấy transcript nào liên quan đến câu hỏi này."

        parts = []
        for i, r in enumerate(results, 1):
            speakers = ", ".join(r.get("speakers", [])) or "Unknown"
            title = r.get("title", "Untitled Meeting")
            text = r.get("text", "")
            score = r.get("score", 0)
            parts.append(
                f"[{i}] Meeting: {title}\n"
                f"    Speakers: {speakers}\n"
                f"    Score: {score:.3f}\n"
                f"    Content: {text}"
            )

        logger.info(
            "meeting_search_done",
            user_id=user_id,
            count=len(results),
        )
        return "\n\n".join(parts)

    except Exception as e:
        logger.error("meeting_search_error", user_id=user_id, error=str(e))
        return f"Lỗi khi tìm kiếm transcript: {str(e)}"
