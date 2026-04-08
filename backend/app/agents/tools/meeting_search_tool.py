"""
ADK Tool tìm kiếm transcript meeting trong Qdrant.

Chiến lược giống qdrant_search_tool: query expansion + parallel search
→ merge + rerank → trả top_k chất lượng cao nhất.
"""

import asyncio

import structlog
from google.adk.tools import ToolContext
from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.core.database import get_qdrant_client
from app.services.transcript_rag_service import TranscriptRAGService
from app.utils.gemini_utils import expand_query, get_query_embedding

logger = structlog.get_logger(__name__)


def _search_meeting_one(
    client: QdrantClient,
    query: str,
    user_id: str | None,
    settings,
) -> list[dict]:
    """Chạy một query search đơn cho meetings — sync, dùng với asyncio.to_thread."""
    query_vector = list(get_query_embedding(query))
    return TranscriptRAGService(client).search(
        query_vector=query_vector,
        user_id=user_id,
        top_k=settings.top_k_results,
        score_threshold=settings.score_threshold,
    )


async def search_meeting_transcripts(query: str, tool_context: ToolContext) -> str:
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
    client = get_qdrant_client()

    try:
        # Expand query và original search chạy song song
        expanded_task = expand_query(query, n=settings.query_expansion_count)
        original_task = asyncio.to_thread(_search_meeting_one, client, query, user_id, settings)

        expanded, original_results = await asyncio.gather(expanded_task, original_task)

        # Search expanded queries song song
        if expanded:
            expanded_results_list = await asyncio.gather(
                *[
                    asyncio.to_thread(_search_meeting_one, client, q, user_id, settings)
                    for q in expanded
                ]
            )
        else:
            expanded_results_list = []

        # Merge: key = meeting_id + start_ms (chunk identity)
        merged: dict[str, dict] = {}
        for results in [original_results, *expanded_results_list]:
            for r in results:
                key = f"{r['meeting_id']}_{r.get('start_ms', '')}"
                if key in merged:
                    merged[key]["score"] += r["score"]
                else:
                    merged[key] = r.copy()

        if not merged:
            return "Không tìm thấy transcript nào liên quan đến câu hỏi này."

        ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
        top_results = ranked[: settings.top_k_results]

        parts = []
        for i, r in enumerate(top_results, 1):
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
            queries=1 + len(expanded),
            candidates=len(merged),
            returned=len(top_results),
        )
        return "\n\n".join(parts)

    except Exception as e:
        logger.error("meeting_search_error", user_id=user_id, error=str(e))
        return f"Lỗi khi tìm kiếm transcript: {str(e)}"
