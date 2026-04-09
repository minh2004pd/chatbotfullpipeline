"""Unit tests cho WikiRepository — local filesystem backend."""

import pytest

from app.repositories.wiki_repo import WikiRepository


@pytest.fixture
def wiki_dir(tmp_path):
    return str(tmp_path / "wiki")


@pytest.fixture
def repo(wiki_dir):
    return WikiRepository(base_dir=wiki_dir)


USER = "user_test"


# ── ensure_wiki_structure ─────────────────────────────────────────────────────


def test_ensure_creates_index_and_log(repo, wiki_dir):
    repo.ensure_wiki_structure(user_id=USER)

    # index.md được tạo với nội dung mặc định
    index = repo.read_index(user_id=USER)
    assert "Wiki Index" in index
    # log.md được tạo (rỗng)
    from pathlib import Path

    assert (Path(wiki_dir) / USER / "log.md").exists()


def test_ensure_creates_claude_md(repo, wiki_dir):
    """CLAUDE.md (schema/hiến pháp) phải được tạo cùng với cấu trúc wiki."""
    from pathlib import Path

    repo.ensure_wiki_structure(user_id=USER)
    claude_md = Path(wiki_dir) / USER / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text()
    assert "Wiki Schema" in content
    assert "entities/" in content
    assert "topics/" in content
    assert "summaries/" in content


def test_ensure_claude_md_idempotent(repo, wiki_dir):
    """Gọi nhiều lần không overwrite CLAUDE.md đã có."""
    from pathlib import Path

    repo.ensure_wiki_structure(user_id=USER)
    claude_path = Path(wiki_dir) / USER / "CLAUDE.md"
    claude_path.write_text("# Custom Schema")
    repo.ensure_wiki_structure(user_id=USER)
    assert claude_path.read_text() == "# Custom Schema"


def test_ensure_creates_page_subdirs(repo, wiki_dir):
    from pathlib import Path

    repo.ensure_wiki_structure(user_id=USER)
    for sub in ("pages/entities", "pages/topics", "pages/summaries"):
        assert (Path(wiki_dir) / USER / sub).is_dir()


def test_ensure_idempotent(repo):
    """Gọi nhiều lần không lỗi, không overwrite nội dung đã có."""
    repo.ensure_wiki_structure(user_id=USER)
    repo.write_index(user_id=USER, content="# Custom Index")
    repo.ensure_wiki_structure(user_id=USER)
    # Index giữ nguyên nội dung custom
    assert "Custom Index" in repo.read_index(user_id=USER)


# ── Pages CRUD ────────────────────────────────────────────────────────────────


def test_write_and_read_page(repo):
    content = "---\ntitle: Q1 Planning\n---\n\n# Q1 Planning\n\nNội dung test."
    repo.write_page(user_id=USER, rel_path="pages/topics/q1-planning.md", content=content)
    result = repo.read_page(user_id=USER, rel_path="pages/topics/q1-planning.md")
    assert result == content


def test_read_nonexistent_page_returns_none(repo):
    result = repo.read_page(user_id=USER, rel_path="pages/topics/nonexistent.md")
    assert result is None


def test_write_page_creates_parent_dirs(repo):
    """write_page tự tạo thư mục nếu chưa có."""
    repo.write_page(user_id=USER, rel_path="pages/entities/gemini.md", content="# Gemini")
    assert repo.read_page(user_id=USER, rel_path="pages/entities/gemini.md") == "# Gemini"


def test_delete_page(repo):
    repo.write_page(user_id=USER, rel_path="pages/topics/test.md", content="test")
    repo.delete_page(user_id=USER, rel_path="pages/topics/test.md")
    assert repo.read_page(user_id=USER, rel_path="pages/topics/test.md") is None


def test_delete_nonexistent_page_no_error(repo):
    # Không raise nếu file không tồn tại
    repo.delete_page(user_id=USER, rel_path="pages/topics/ghost.md")


# ── list_pages_in_category ────────────────────────────────────────────────────


def test_list_pages_empty_category(repo):
    repo.ensure_wiki_structure(user_id=USER)
    result = repo.list_pages_in_category(user_id=USER, category="topics")
    assert result == []


def test_list_pages_returns_filenames(repo):
    repo.write_page(user_id=USER, rel_path="pages/topics/alpha.md", content="a")
    repo.write_page(user_id=USER, rel_path="pages/topics/beta.md", content="b")
    repo.write_page(user_id=USER, rel_path="pages/entities/gemini.md", content="c")

    topics = repo.list_pages_in_category(user_id=USER, category="topics")
    assert set(topics) == {"alpha.md", "beta.md"}

    entities = repo.list_pages_in_category(user_id=USER, category="entities")
    assert entities == ["gemini.md"]


def test_list_all_pages_cross_categories(repo):
    repo.write_page(user_id=USER, rel_path="pages/topics/proj-x.md", content="x")
    repo.write_page(user_id=USER, rel_path="pages/entities/soniox.md", content="s")
    repo.write_page(user_id=USER, rel_path="pages/summaries/doc-1.md", content="d")

    all_pages = repo.list_all_pages(user_id=USER)
    rel_paths = {p["rel_path"] for p in all_pages}
    assert "pages/topics/proj-x.md" in rel_paths
    assert "pages/entities/soniox.md" in rel_paths
    assert "pages/summaries/doc-1.md" in rel_paths
    # Kiểm tra category field
    for p in all_pages:
        assert p["category"] in ("entities", "topics", "summaries")
        assert p["filename"].endswith(".md")


# ── Index & Log ───────────────────────────────────────────────────────────────


def test_read_index_empty(repo):
    result = repo.read_index(user_id=USER)
    assert result == ""


def test_write_and_read_index(repo):
    repo.write_index(user_id=USER, content="# Wiki Index\n\n## Topics\n- [[pages/topics/x.md]] — X")
    result = repo.read_index(user_id=USER)
    assert "Wiki Index" in result
    assert "pages/topics/x.md" in result


def test_append_log_creates_and_accumulates(repo):
    repo.ensure_wiki_structure(user_id=USER)
    repo.append_log(user_id=USER, entry="## [2026-04-09] INGEST | doc1")
    repo.append_log(user_id=USER, entry="## [2026-04-09] INGEST | doc2")

    from pathlib import Path

    log_content = (Path(repo._base_dir) / USER / "log.md").read_text()
    assert "doc1" in log_content
    assert "doc2" in log_content


def test_append_log_rotation(repo):
    """Khi quá 1000 dòng, chỉ giữ 1000 dòng gần nhất."""
    from app.repositories.wiki_repo import _LOG_MAX_LINES

    repo.ensure_wiki_structure(user_id=USER)
    # Ghi 1005 entries
    for i in range(_LOG_MAX_LINES + 5):
        repo.append_log(user_id=USER, entry=f"line {i}")

    from pathlib import Path

    lines = (Path(repo._base_dir) / USER / "log.md").read_text().splitlines()
    assert len(lines) <= _LOG_MAX_LINES
    # Dòng cuối cùng phải là dòng mới nhất
    assert f"line {_LOG_MAX_LINES + 4}" in lines[-1]


# ── Raw sources ───────────────────────────────────────────────────────────────


def test_write_and_read_raw(repo):
    repo.write_raw(user_id=USER, category="documents", filename="doc-abc.txt", content="Nội dung PDF")
    result = repo.read_raw(user_id=USER, category="documents", filename="doc-abc.txt")
    assert result == "Nội dung PDF"


def test_read_raw_nonexistent_returns_none(repo):
    assert repo.read_raw(user_id=USER, category="transcripts", filename="missing.txt") is None


# ── Multi-user isolation ──────────────────────────────────────────────────────


def test_users_are_isolated(repo):
    """Pages của user A không nhìn thấy được từ user B."""
    repo.write_page(user_id="user_a", rel_path="pages/topics/secret.md", content="User A data")
    result = repo.read_page(user_id="user_b", rel_path="pages/topics/secret.md")
    assert result is None
