"""ADK Tools: liệt kê và tìm kiếm transcript meeting."""

import structlog
from google.adk.tools import ToolContext

from app.agents.tools.utils import get_user_id
from app.core.config import get_settings
from app.core.database import get_dynamodb_resource, get_qdrant_client
from app.repositories.meeting_repo import MeetingRepository
from app.services.transcript_rag_service import TranscriptRAGService
from app.utils.gemini_utils import get_query_embedding

logger = structlog.get_logger(__name__)


def list_meetings(tool_context: ToolContext) -> dict:
    """
    Liệt kê tất cả cuộc họp đã được ghi âm của người dùng.

    Dùng TRƯỚC khi search transcript khi: người dùng hỏi chung chung về meeting như
    "tôi có những cuộc họp nào?", "danh sách buổi họp", "có bao nhiêu recording?",
    "tóm tắt tất cả các cuộc họp", "meeting gần nhất là gì?", hoặc khi cần biết
    tên/ID meeting trước khi tra nội dung cụ thể bên trong.

    Không dùng để tìm nội dung bên trong transcript — hãy dùng search_meeting_transcripts.

    Returns:
        Dict với danh sách meeting gồm: title, meeting_id, status, created_at,
        duration_ms, speakers, utterance_count. Trả về found=False nếu chưa có cuộc họp nào.
    """
    settings = get_settings()
    user_id = get_user_id(tool_context)

    try:
        resource = get_dynamodb_resource()
        table = resource.Table(settings.meetings_table_name)
        repo = MeetingRepository(table)
        meetings = repo.list_meetings(user_id=user_id)

        if not meetings:
            return {
                "found": False,
                "meetings": [],
                "message": "Bạn chưa có cuộc họp nào được ghi âm.",
            }

        formatted = [
            {
                "meeting_id": m.get("meeting_id", ""),
                "title": m.get("title", "Untitled Meeting"),
                "status": m.get("status", ""),
                "created_at": m.get("created_at", ""),
                "duration_ms": m.get("duration_ms"),
                "speakers": m.get("speakers", []),
                "utterance_count": m.get("utterance_count", 0),
            }
            for m in meetings
        ]
        # Sắp xếp mới nhất trước
        formatted.sort(key=lambda x: x["created_at"], reverse=True)

        logger.info("meetings_listed", user_id=user_id, count=len(formatted))
        return {
            "found": True,
            "meetings": formatted,
            "count": len(formatted),
        }

    except Exception as e:
        logger.error("list_meetings_error", user_id=user_id, error=str(e))
        return {"found": False, "meetings": [], "message": f"Lỗi liệt kê meeting: {str(e)}"}


def search_meeting_transcripts(query: str, tool_context: ToolContext) -> str:
    """
    Tìm kiếm trong transcript các cuộc họp đã được ghi âm và dừng ghi (RAG).

    ⚠️ FALLBACK TOOL — CHỈ gọi tool này SAU KHI đã gọi read_wiki_index và xác định wiki
    không đủ thông tin cần thiết. KHÔNG bao giờ gọi trước read_wiki_index.

    Dùng khi cần: nội dung cuộc họp, ai nói gì, quyết định, action items, cam kết.
    Không dùng cho tài liệu PDF/file đã upload.
    Chỉ có dữ liệu sau khi user bấm dừng ghi — transcript realtime chưa tồn tại.

    Query nên là cụm từ khóa về chủ đề hoặc người nói, không phải câu hỏi nguyên văn.
    Nếu kết quả rỗng, thử lại với keyword khác hoặc diễn đạt khác (tối đa 2 lần).

    Args:
        query: Cụm từ khóa mô tả nội dung cần tìm trong transcript cuộc họp.

    Returns:
        Các đoạn transcript liên quan kèm tên meeting, speaker (nếu có), relevance score.
        Trả về thông báo không tìm thấy nếu không có kết quả vượt score threshold.
    """
    settings = get_settings()
    user_id = get_user_id(tool_context)

    try:
        rag_service = TranscriptRAGService(get_qdrant_client())
        query_vector = list(get_query_embedding(query))
        results = rag_service.search(
            query_vector=query_vector,
            user_id=user_id,
            top_k=settings.top_k_results,
            score_threshold=settings.score_threshold,
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
