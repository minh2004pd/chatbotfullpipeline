"""ADK Tools: đọc LLM Wiki Layer.

Agent chỉ READ wiki qua các tools này.
Wiki được ghi bởi background WikiService sau mỗi ingestion event.

Flow đề xuất cho agent:
  1. read_wiki_index() → xem bản đồ tri thức (~1-2k tokens)
  2. read_wiki_page(rel_path) → đọc nội dung trang cụ thể
  3. Nếu không đủ → fall back sang search_documents / search_meeting_transcripts
"""

import structlog
from google.adk.tools import ToolContext

logger = structlog.get_logger(__name__)


def _repo():
    """Lazy import để tránh circular import (wiki_tools → dependencies → root_agent → wiki_tools)."""
    from app.core.dependencies import get_wiki_repo

    return get_wiki_repo()


def read_wiki_index(tool_context: ToolContext) -> dict:
    """
    Đọc "bản đồ tri thức" Wiki — liệt kê tất cả trang Wiki AI đã tổng hợp.

    Dùng TRƯỚC khi đọc trang cụ thể. Index (~1-2k tokens) cho biết wiki đang có gì,
    giúp chọn đúng trang cần đọc tiếp. Gọi khi câu hỏi yêu cầu tổng hợp cross-source
    hoặc overview về project/topic/entity (ví dụ: "dự án X hiện tại thế nào?",
    "tóm tắt về Y", "Q1 planning ra sao?").

    Sau khi đọc index, dùng rel_path từ index để gọi read_wiki_page.

    Returns:
        Dict với content (nội dung index.md), page_count (số trang).
        found=False nếu wiki chưa được khởi tạo.
    """
    user_id = tool_context.state.get("user_id", "default_user")
    logger.info("agent_tool_called", tool="read_wiki_index", user_id=user_id)

    try:
        repo = _repo()
        content = repo.read_index(user_id=user_id)

        if not content or "Chưa có trang Wiki" in content:
            logger.info("wiki_index_empty", user_id=user_id)
            return {
                "found": False,
                "content": "",
                "page_count": 0,
                "message": (
                    "Wiki chưa có trang nào. Hệ thống sẽ tự động tạo khi bạn "
                    "upload tài liệu hoặc ghi âm meeting."
                ),
            }

        # Đếm số trang (đếm dòng bắt đầu bằng "- [[")
        page_count = content.count("- [[")
        logger.info("wiki_index_read", user_id=user_id, page_count=page_count)
        return {
            "found": True,
            "content": content,
            "page_count": page_count,
        }

    except Exception as e:
        logger.error("read_wiki_index_error", user_id=user_id, error=str(e))
        return {
            "found": False,
            "content": "",
            "page_count": 0,
            "message": f"Lỗi đọc wiki index: {str(e)}",
        }


def read_wiki_page(rel_path: str, tool_context: ToolContext) -> dict:
    """
    Đọc nội dung đầy đủ một trang Wiki cụ thể (Markdown + YAML frontmatter).

    Dùng SAU read_wiki_index khi biết chính xác trang cần đọc.
    rel_path là đường dẫn tương đối xuất hiện trong index.md,
    ví dụ: "pages/topics/q1-planning.md", "pages/entities/gemini-2-5-flash.md".

    Wiki page chứa synthesis từ nhiều documents/meetings, kèm lịch sử thay đổi quyết định.

    Args:
        rel_path: Đường dẫn tương đối tới trang Wiki (lấy từ read_wiki_index).
        tool_context: ADK tool context.

    Returns:
        Dict với content (Markdown đầy đủ), rel_path, found.
        found=False nếu trang không tồn tại.
    """
    user_id = tool_context.state.get("user_id", "default_user")
    logger.info("agent_tool_called", tool="read_wiki_page", user_id=user_id, rel_path=rel_path)

    try:
        repo = _repo()
        # Sanitize rel_path: chỉ cho phép pages/ prefix, tránh path traversal
        rel_path = rel_path.strip().lstrip("/")
        if not rel_path.startswith("pages/"):
            logger.warning("wiki_page_invalid_path", user_id=user_id, rel_path=rel_path)
            return {
                "found": False,
                "content": "",
                "rel_path": rel_path,
                "message": "rel_path phải bắt đầu bằng 'pages/' (lấy từ read_wiki_index).",
            }

        content = repo.read_page(user_id=user_id, rel_path=rel_path)
        if not content:
            logger.warning("wiki_page_not_found", user_id=user_id, rel_path=rel_path)
            return {
                "found": False,
                "content": "",
                "rel_path": rel_path,
                "message": f"Trang Wiki '{rel_path}' không tồn tại.",
            }

        logger.info("wiki_page_read", user_id=user_id, path=rel_path)
        return {
            "found": True,
            "content": content,
            "rel_path": rel_path,
        }

    except Exception as e:
        logger.error("read_wiki_page_error", user_id=user_id, rel_path=rel_path, error=str(e))
        return {
            "found": False,
            "content": "",
            "rel_path": rel_path,
            "message": f"Lỗi đọc trang wiki: {str(e)}",
        }


def list_wiki_pages(category: str, tool_context: ToolContext) -> dict:
    """
    Liệt kê tên file trong một category cụ thể của Wiki.

    Dùng khi cần xem tất cả trang trong một nhóm mà không cần đọc nội dung.
    Sau khi có danh sách, dùng read_wiki_page để đọc trang cụ thể.

    Args:
        category: Nhóm wiki cần liệt kê — một trong: "entities", "topics", "summaries".
                  - entities: người, công ty, công cụ/sản phẩm cụ thể
                  - topics: dự án, khái niệm, chủ đề thảo luận
                  - summaries: tóm tắt từng nguồn tài liệu/meeting riêng lẻ
        tool_context: ADK tool context.

    Returns:
        Dict với category, pages (list filenames), count. found=False nếu không có trang nào.
    """
    user_id = tool_context.state.get("user_id", "default_user")
    logger.info("agent_tool_called", tool="list_wiki_pages", user_id=user_id, category=category)

    valid_categories = ("entities", "topics", "summaries")
    if category not in valid_categories:
        logger.warning("wiki_pages_invalid_category", user_id=user_id, category=category)
        return {
            "found": False,
            "category": category,
            "pages": [],
            "count": 0,
            "message": f"category phải là một trong: {', '.join(valid_categories)}",
        }

    try:
        repo = _repo()
        pages = repo.list_pages_in_category(user_id=user_id, category=category)

        if not pages:
            logger.info("wiki_pages_empty", user_id=user_id, category=category)
            return {
                "found": False,
                "category": category,
                "pages": [],
                "count": 0,
                "message": f"Chưa có trang Wiki nào trong category '{category}'.",
            }

        logger.info("wiki_pages_listed", user_id=user_id, category=category, count=len(pages))
        return {
            "found": True,
            "category": category,
            "pages": pages,
            "count": len(pages),
        }

    except Exception as e:
        logger.error("list_wiki_pages_error", user_id=user_id, category=category, error=str(e))
        return {
            "found": False,
            "category": category,
            "pages": [],
            "count": 0,
            "message": f"Lỗi liệt kê wiki: {str(e)}",
        }
