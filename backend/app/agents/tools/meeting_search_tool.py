"""ADK Tool tìm kiếm transcript meeting trong Qdrant."""

import asyncio

import structlog
from google.adk.tools import ToolContext
from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.core.database import get_qdrant_client
from app.services.transcript_rag_service import TranscriptRAGService
from app.utils.gemini_utils import get_query_embedding

logger = structlog.get_logger(__name__)


def _search_meeting(client: QdrantClient, query: str, user_id: str | None, settings) -> list[dict]:
    """Sync search — chạy trong asyncio.to_thread để không block event loop."""
    query_vector = list(get_query_embedding(query))
    return TranscriptRAGService(client).search(
        query_vector=query_vector,
        user_id=user_id,
        top_k=settings.top_k_results,
        score_threshold=settings.score_threshold,
    )


async def search_meeting_transcripts(query: str, tool_context: ToolContext) -> str:
    """Tìm kiếm trong transcript các cuộc họp đã ghi âm và dừng (đã index vào kho).

    Dùng khi người dùng hỏi về nội dung họp, lời thoại, tóm tắt meeting, quyết định, hoặc ai nói gì.
    Không dùng cho tài liệu PDF/file upload — với tài liệu hãy gọi `search_documents`.

    Args:
        query: Câu hỏi hoặc từ khóa tìm trong transcript.

    Returns:
        Các đoạn transcript liên quan kèm tên meeting, speaker (nếu có), điểm khớp.
    """
    settings = get_settings()
    user_id = tool_context.state.get("user_id", "default_user")
    client = get_qdrant_client()

    try:
        results = await asyncio.to_thread(_search_meeting, client, query, user_id, settings)

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

        logger.info("meeting_search_done", user_id=user_id, count=len(results))
        return "\n\n".join(parts)

    except Exception as e:
        logger.error("meeting_search_error", user_id=user_id, error=str(e))
        return f"Lỗi khi tìm kiếm transcript: {str(e)}"
