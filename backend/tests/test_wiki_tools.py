"""Unit tests cho wiki ADK tools (read_wiki_index, read_wiki_page, list_wiki_pages)."""

from unittest.mock import MagicMock, patch

from app.agents.tools.wiki_tools import list_wiki_pages, read_wiki_index, read_wiki_page


def _make_tool_context(user_id: str = "user_test") -> MagicMock:
    ctx = MagicMock()
    ctx.state = {"user_id": user_id}
    return ctx


# ── read_wiki_index ───────────────────────────────────────────────────────────


def test_read_wiki_index_found():
    content = "# Wiki Index\n\n## Topics\n- [[pages/topics/proj.md]] — Project A\n- [[pages/entities/gemini.md]] — Gemini"
    mock_repo = MagicMock()
    mock_repo.read_index.return_value = content

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = read_wiki_index(_make_tool_context())

    assert result["found"] is True
    assert result["page_count"] == 2
    assert "Wiki Index" in result["content"]


def test_read_wiki_index_empty():
    mock_repo = MagicMock()
    mock_repo.read_index.return_value = ""

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = read_wiki_index(_make_tool_context())

    assert result["found"] is False
    assert result["page_count"] == 0
    assert "message" in result


def test_read_wiki_index_not_initialized():
    mock_repo = MagicMock()
    mock_repo.read_index.return_value = "Chưa có trang Wiki nào."

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = read_wiki_index(_make_tool_context())

    assert result["found"] is False


def test_read_wiki_index_error():
    mock_repo = MagicMock()
    mock_repo.read_index.side_effect = RuntimeError("S3 error")

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = read_wiki_index(_make_tool_context())

    assert result["found"] is False
    assert "message" in result


# ── read_wiki_page ────────────────────────────────────────────────────────────


def test_read_wiki_page_found():
    content = "---\ntitle: Q1 Plan\n---\n\n# Q1 Plan"
    mock_repo = MagicMock()
    mock_repo.read_page.return_value = content

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = read_wiki_page("pages/topics/q1-plan.md", _make_tool_context())

    assert result["found"] is True
    assert result["content"] == content
    assert result["rel_path"] == "pages/topics/q1-plan.md"


def test_read_wiki_page_not_found():
    mock_repo = MagicMock()
    mock_repo.read_page.return_value = None

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = read_wiki_page("pages/topics/nonexistent.md", _make_tool_context())

    assert result["found"] is False
    assert "message" in result


def test_read_wiki_page_invalid_path():
    mock_repo = MagicMock()

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = read_wiki_page("../../etc/passwd", _make_tool_context())

    assert result["found"] is False
    assert "pages/" in result["message"]
    mock_repo.read_page.assert_not_called()


def test_read_wiki_page_strips_leading_slash():
    content = "# Content"
    mock_repo = MagicMock()
    mock_repo.read_page.return_value = content

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = read_wiki_page("/pages/topics/test.md", _make_tool_context())

    assert result["found"] is True
    mock_repo.read_page.assert_called_once_with(
        user_id="user_test", rel_path="pages/topics/test.md"
    )


def test_read_wiki_page_error():
    mock_repo = MagicMock()
    mock_repo.read_page.side_effect = RuntimeError("disk error")

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = read_wiki_page("pages/topics/test.md", _make_tool_context())

    assert result["found"] is False
    assert "message" in result


# ── list_wiki_pages ───────────────────────────────────────────────────────────


def test_list_wiki_pages_found():
    mock_repo = MagicMock()
    mock_repo.list_pages_in_category.return_value = ["alpha.md", "beta.md"]

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = list_wiki_pages("topics", _make_tool_context())

    assert result["found"] is True
    assert result["count"] == 2
    assert "alpha.md" in result["pages"]
    mock_repo.list_pages_in_category.assert_called_once_with(user_id="user_test", category="topics")


def test_list_wiki_pages_empty():
    mock_repo = MagicMock()
    mock_repo.list_pages_in_category.return_value = []

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = list_wiki_pages("entities", _make_tool_context())

    assert result["found"] is False
    assert result["count"] == 0


def test_list_wiki_pages_invalid_category():
    mock_repo = MagicMock()

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = list_wiki_pages("invalid_cat", _make_tool_context())

    assert result["found"] is False
    assert "message" in result
    mock_repo.list_pages_in_category.assert_not_called()


def test_list_wiki_pages_all_valid_categories():
    mock_repo = MagicMock()
    mock_repo.list_pages_in_category.return_value = ["x.md"]

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        for cat in ("entities", "topics", "summaries"):
            result = list_wiki_pages(cat, _make_tool_context())
            assert result["found"] is True, f"category '{cat}' should be valid"


def test_list_wiki_pages_error():
    mock_repo = MagicMock()
    mock_repo.list_pages_in_category.side_effect = RuntimeError("storage error")

    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        result = list_wiki_pages("topics", _make_tool_context())

    assert result["found"] is False
    assert "message" in result


def test_list_wiki_pages_uses_correct_user_id():
    mock_repo = MagicMock()
    mock_repo.list_pages_in_category.return_value = ["doc.md"]

    ctx = _make_tool_context(user_id="special_user")
    with patch("app.agents.tools.wiki_tools._repo", return_value=mock_repo):
        list_wiki_pages("summaries", ctx)

    mock_repo.list_pages_in_category.assert_called_once_with(
        user_id="special_user", category="summaries"
    )
