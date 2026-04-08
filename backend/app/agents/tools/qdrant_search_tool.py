"""
Tool tìm kiếm tài liệu trong Qdrant.

Chiến lược:
1. expand_query sinh thêm N queries gần nghĩa (model nhẹ, non-blocking)
2. Tất cả queries embed + search chạy song song qua asyncio.gather()
3. Merge kết quả: dedup by document_id, cộng dồn score từ nhiều queries
4. Rerank descending, trả top_k chất lượng cao nhất
"""

import asyncio

import structlog
from google.adk.tools import ToolContext

from app.core.config import get_settings
from app.core.database import get_qdrant_client
from app.repositories.qdrant_repo import QdrantRepository
from app.utils.gemini_utils import expand_query, get_query_embedding

logger = structlog.get_logger(__name__)


def _search_one(repo: QdrantRepository, query: str, user_id: str | None, settings) -> list[dict]:
    """Chạy một query search đơn — dùng trong asyncio.to_thread vì Qdrant client là sync."""
    query_vector = list(get_query_embedding(query))
    return repo.search(
        query_vector=query_vector,
        user_id=user_id,
        top_k=settings.top_k_results,
        score_threshold=settings.score_threshold,
    )


async def search_documents(query: str, tool_context: ToolContext) -> dict:
    """
    Tìm kiếm tài liệu liên quan trong vector database dựa trên câu hỏi.

    Query expansion + parallel search: sinh N queries gần nghĩa rồi chạy
    tất cả song song, merge + rerank kết quả — tăng recall mà không tăng latency.

    Args:
        query: Câu hỏi hoặc từ khóa tìm kiếm.
        tool_context: ADK tool context chứa session state.

    Returns:
        Dict với danh sách các đoạn tài liệu liên quan và nguồn trích dẫn.
    """
    settings = get_settings()
    user_id = tool_context.state.get("user_id")

    try:
        repo = QdrantRepository(get_qdrant_client())

        # Expand query và search song song — expand_query + tất cả searches chạy concurrently
        expanded_task = expand_query(query, n=settings.query_expansion_count)
        original_search_task = asyncio.to_thread(_search_one, repo, query, user_id, settings)

        # Chờ expand xong rồi launch searches cho expanded queries
        expanded, original_results = await asyncio.gather(expanded_task, original_search_task)

        # Search tất cả expanded queries song song
        if expanded:
            expanded_results_list = await asyncio.gather(
                *[asyncio.to_thread(_search_one, repo, q, user_id, settings) for q in expanded]
            )
        else:
            expanded_results_list = []

        # Merge: dedup by document_id, cộng dồn score
        merged: dict[str, dict] = {}
        for results in [original_results, *expanded_results_list]:
            for r in results:
                doc_id = r["document_id"]
                if doc_id in merged:
                    merged[doc_id]["relevance_score"] += round(r["score"], 4)
                else:
                    merged[doc_id] = {
                        "text": r["text"],
                        "source": r["filename"],
                        "document_id": doc_id,
                        "relevance_score": round(r["score"], 4),
                    }

        if not merged:
            return {"found": False, "message": "Không tìm thấy tài liệu liên quan.", "results": []}

        # Rerank descending by accumulated score
        ranked = sorted(merged.values(), key=lambda x: x["relevance_score"], reverse=True)
        top_results = ranked[: settings.top_k_results]

        logger.info(
            "qdrant_search_done",
            user_id=user_id,
            queries=1 + len(expanded),
            candidates=len(merged),
            returned=len(top_results),
        )
        return {"found": True, "results": top_results, "count": len(top_results)}

    except Exception as e:
        logger.error("qdrant_search_error", error=str(e))
        return {"found": False, "message": f"Lỗi tìm kiếm: {str(e)}", "results": []}
