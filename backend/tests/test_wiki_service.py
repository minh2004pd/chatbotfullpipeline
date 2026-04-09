"""Unit tests cho WikiService — mock LLM calls, dùng WikiRepository real (local fs)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.repositories.wiki_repo import WikiRepository
from app.services.wiki_service import (
    WikiService,
    _parse_frontmatter_sources,
    _parse_frontmatter_title,
    _slugify,
    _strip_code_fence,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def wiki_dir(tmp_path):
    return str(tmp_path / "wiki")


@pytest.fixture
def repo(wiki_dir):
    return WikiRepository(base_dir=wiki_dir)


@pytest.fixture
def settings():
    s = MagicMock()
    s.wiki_enabled = True
    s.wiki_max_text_chars = 1000
    s.wiki_max_topics_per_source = 3
    s.wiki_max_entities_per_source = 10
    return s


@pytest.fixture
def service(repo, settings):
    return WikiService(repo=repo, settings=settings)


USER = "user_test"

# ── Helpers ───────────────────────────────────────────────────────────────────


def test_slugify_basic():
    assert _slugify("Q1 Planning 2026") == "q1-planning-2026"


def test_slugify_vietnamese():
    assert _slugify("Dự án MemRAG") == "du-an-memrag"


def test_slugify_max_length():
    long_text = "a" * 100
    result = _slugify(long_text)
    assert len(result) <= 60


def test_slugify_special_chars():
    assert _slugify("Hello, World! @2026") == "hello-world-2026"


def test_parse_frontmatter_title_found():
    content = "---\ntitle: Dự Án X\ntags: [ai]\n---\n\n# Content"
    assert _parse_frontmatter_title(content) == "Dự Án X"


def test_parse_frontmatter_title_not_found():
    assert _parse_frontmatter_title("# No frontmatter") == ""


def test_parse_frontmatter_sources_found():
    content = "---\ntitle: X\nsources: [doc-1, meeting-2, doc-3]\n---\n\n# Content"
    sources = _parse_frontmatter_sources(content)
    assert sources == ["doc-1", "meeting-2", "doc-3"]


def test_parse_frontmatter_sources_empty():
    assert _parse_frontmatter_sources("# No frontmatter") == []


def test_parse_frontmatter_sources_with_code_fence():
    """Frontmatter bên trong code fence vẫn được parse đúng."""
    content = "```markdown\n---\ntitle: X\nsources: [doc-1, doc-2]\n---\n# Content\n```"
    assert _parse_frontmatter_sources(content) == ["doc-1", "doc-2"]


def test_strip_code_fence_markdown():
    raw = "```markdown\n---\ntitle: X\n---\n# Content\n```"
    result = _strip_code_fence(raw)
    assert result.startswith("---")
    assert "```" not in result


def test_strip_code_fence_no_fence():
    raw = "---\ntitle: X\n---\n# Content"
    assert _strip_code_fence(raw) == raw


# ── _extract_topics: guarantee 3 categories ──────────────────────────────────


@pytest.mark.asyncio
async def test_extract_topics_fallback_has_all_3_categories(service):
    """Khi LLM fail, fallback phải trả về đủ entities + topics + summaries."""
    with patch.object(service, "_extract_topics", wraps=service._extract_topics):
        # Patch LLM để raise exception → trigger fallback
        from unittest.mock import patch as _patch

        with _patch("app.services.wiki_service.get_genai_client") as mock_client:
            mock_client.return_value.aio.models.generate_content.side_effect = RuntimeError(
                "LLM down"
            )
            result = await service._extract_topics(text="some text", source_name="paper.pdf")

    categories = {t["category"] for t in result}
    assert "entities" in categories, "Fallback phải có ít nhất 1 entity"
    assert "topics" in categories, "Fallback phải có ít nhất 1 topic"
    assert "summaries" in categories, "Fallback phải có ít nhất 1 summary"


@pytest.mark.asyncio
async def test_extract_topics_preserves_entity_type(service):
    """LLM trả về type cho entities → phải được giữ lại để synthesis dùng đúng template."""
    import json
    from unittest.mock import patch as _patch

    llm_response = json.dumps(
        {
            "entities": [
                {"slug": "lora", "title": "LoRA", "type": "method"},
                {"slug": "gpt-4o", "title": "GPT-4o", "type": "model"},
            ],
            "topics": [{"slug": "peft", "title": "Parameter-efficient Fine-tuning"}],
            "summary": {"slug": "lora-paper", "title": "Tóm tắt: LoRA paper"},
        }
    )
    mock_resp = MagicMock()
    mock_resp.text = llm_response

    with _patch("app.services.wiki_service._with_retry", new=AsyncMock(return_value=mock_resp)):
        result = await service._extract_topics(text="content", source_name="lora.pdf")

    entities = [t for t in result if t["category"] == "entities"]
    assert len(entities) == 2
    lora = next(e for e in entities if e["slug"] == "lora")
    assert lora["type"] == "method", "type phải được giữ lại từ LLM output"
    gpt = next(e for e in entities if e["slug"] == "gpt-4o")
    assert gpt["type"] == "model"


@pytest.mark.asyncio
async def test_extract_topics_empty_llm_arrays_gets_fallbacks(service):
    """Khi LLM trả về entities=[] hoặc topics=[], Python fallback phải bổ sung."""
    import json
    from unittest.mock import patch as _patch

    llm_response = json.dumps(
        {
            "entities": [],  # LLM không tìm thấy entity nào
            "topics": [],  # LLM không tìm thấy topic nào
            "summary": {"slug": "paper-summary", "title": "Tóm tắt: paper.pdf"},
        }
    )

    mock_resp = MagicMock()
    mock_resp.text = llm_response

    with (
        _patch("app.services.wiki_service.get_genai_client") as mock_client,
        _patch("app.services.wiki_service._with_retry", new=AsyncMock(return_value=mock_resp)),
    ):
        mock_client.return_value  # không dùng trực tiếp vì _with_retry bị mock
        result = await service._extract_topics(text="some text", source_name="paper.pdf")

    categories = {t["category"] for t in result}
    assert "entities" in categories, "Phải tự thêm entity fallback khi LLM trả về []"
    assert "topics" in categories, "Phải tự thêm topic fallback khi LLM trả về []"
    assert "summaries" in categories


# ── update_wiki_from_document ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_wiki_from_document_creates_page(service, repo):
    """Sau update, wiki phải có ít nhất 1 page."""
    topics = [{"slug": "memrag-project", "category": "topics", "title": "MemRAG Project"}]
    synthesized = "---\ntitle: MemRAG Project\ntags: []\nsources: [doc-abc]\nlast_updated: 2026-04-09\nversion: 1\n---\n\n# MemRAG Project"

    with (
        patch.object(service, "_extract_topics", new=AsyncMock(return_value=topics)),
        patch.object(service, "_synthesize_page", new=AsyncMock(return_value=synthesized)),
    ):
        await service.update_wiki_from_document(
            user_id=USER,
            document_id="doc-abc",
            filename="spec.pdf",
            full_text="Đây là spec của dự án MemRAG",
        )

    page = repo.read_page(user_id=USER, rel_path="pages/topics/memrag-project.md")
    assert page is not None
    assert "MemRAG Project" in page


@pytest.mark.asyncio
async def test_synthesize_page_receives_source_id(service):
    """_synthesize_page phải nhận source_id để put vào frontmatter — critical cho deletion."""
    topics = [{"slug": "test-topic", "category": "topics", "title": "Test Topic"}]
    synthesized = "---\ntitle: Test Topic\nsources: [doc-real-id]\n---\n# Test"

    mock_synthesize = AsyncMock(return_value=synthesized)
    with (
        patch.object(service, "_extract_topics", new=AsyncMock(return_value=topics)),
        patch.object(service, "_synthesize_page", new=mock_synthesize),
    ):
        await service.update_wiki_from_document(
            user_id=USER,
            document_id="doc-real-id",
            filename="paper.pdf",
            full_text="content",
        )

    # Verify _synthesize_page được gọi với source_id=document_id (không phải filename)
    call_kwargs = mock_synthesize.call_args.kwargs
    assert call_kwargs["source_id"] == "doc-real-id", (
        "source_id phải là document_id, không phải filename. "
        "Nếu sai, remove_source_from_wiki sẽ không tìm thấy page khi xóa."
    )
    assert call_kwargs["source_name"] == "paper.pdf"
    # topic_type phải được forward (có thể rỗng cho topics/summaries, nhưng key phải có)
    assert "topic_type" in call_kwargs


@pytest.mark.asyncio
async def test_update_wiki_saves_raw_text(service, repo):
    """Text thô phải được lưu vào raw/documents/."""
    with (
        patch.object(service, "_extract_topics", new=AsyncMock(return_value=[])),
    ):
        await service.update_wiki_from_document(
            user_id=USER,
            document_id="doc-xyz",
            filename="test.pdf",
            full_text="Nội dung thô của PDF",
        )

    raw = repo.read_raw(user_id=USER, category="documents", filename="doc-xyz.txt")
    assert raw == "Nội dung thô của PDF"


@pytest.mark.asyncio
async def test_update_wiki_disabled_does_nothing(repo, settings):
    settings.wiki_enabled = False
    service = WikiService(repo=repo, settings=settings)

    await service.update_wiki_from_document(
        user_id=USER,
        document_id="doc-1",
        filename="test.pdf",
        full_text="Nội dung",
    )

    # Không có gì được tạo
    assert repo.list_all_pages(user_id=USER) == []


@pytest.mark.asyncio
async def test_update_wiki_from_document_catches_errors(service):
    """Lỗi trong pipeline phải được catch, không propagate."""
    with patch.object(
        service, "_extract_topics", new=AsyncMock(side_effect=RuntimeError("LLM fail"))
    ):
        # Không raise
        await service.update_wiki_from_document(
            user_id=USER,
            document_id="doc-1",
            filename="test.pdf",
            full_text="text",
        )


# ── update_wiki_from_transcript ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_wiki_from_transcript_creates_page(service, repo):
    utterances = [
        {"speaker": "speaker_A", "text": "Chúng ta quyết định dùng Gemini 2.5"},
        {"speaker": "speaker_B", "text": "Đồng ý, và deploy lên ECS"},
    ]
    topics = [{"slug": "meeting-q1-review", "category": "summaries", "title": "Q1 Review Meeting"}]
    synthesized = "---\ntitle: Q1 Review Meeting\nsources: [meet-1]\nlast_updated: 2026-04-09\nversion: 1\n---\n\n# Q1 Review"

    with (
        patch.object(service, "_extract_topics", new=AsyncMock(return_value=topics)),
        patch.object(service, "_synthesize_page", new=AsyncMock(return_value=synthesized)),
    ):
        await service.update_wiki_from_transcript(
            user_id=USER,
            meeting_id="meet-1",
            title="Q1 Review Meeting",
            utterances=utterances,
        )

    page = repo.read_page(user_id=USER, rel_path="pages/summaries/meeting-q1-review.md")
    assert page is not None
    assert "Q1 Review" in page


@pytest.mark.asyncio
async def test_update_wiki_empty_utterances_does_nothing(service, repo):
    """Transcript rỗng không tạo wiki."""
    await service.update_wiki_from_transcript(
        user_id=USER,
        meeting_id="meet-empty",
        title="Empty Meeting",
        utterances=[],
    )
    assert repo.list_all_pages(user_id=USER) == []


# ── remove_source_from_wiki ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remove_source_deletes_single_source_page(service, repo):
    """Page có đúng 1 source → bị xóa."""
    page_content = "---\ntitle: Q1 Plan\nsources: [doc-to-delete]\nlast_updated: 2026-04-09\nversion: 1\n---\n\n# Q1 Plan"
    repo.ensure_wiki_structure(user_id=USER)
    repo.write_page(user_id=USER, rel_path="pages/topics/q1-plan.md", content=page_content)

    await service.remove_source_from_wiki(user_id=USER, source_id="doc-to-delete")

    assert repo.read_page(user_id=USER, rel_path="pages/topics/q1-plan.md") is None


@pytest.mark.asyncio
async def test_remove_source_resynthesize_multi_source_page(service, repo):
    """Page có nhiều sources → LLM re-synthesize, không xóa."""
    page_content = "---\ntitle: Multi\nsources: [doc-keep, doc-delete]\nlast_updated: 2026-04-09\nversion: 2\n---\n\n# Multi"
    repo.ensure_wiki_structure(user_id=USER)
    repo.write_page(user_id=USER, rel_path="pages/topics/multi.md", content=page_content)

    resynth = "---\ntitle: Multi\nsources: [doc-keep]\nlast_updated: 2026-04-09\nversion: 3\n---\n\n# Multi (updated)"

    with patch.object(service, "_resynthesize_without_source", new=AsyncMock(return_value=resynth)):
        await service.remove_source_from_wiki(user_id=USER, source_id="doc-delete")

    result = repo.read_page(user_id=USER, rel_path="pages/topics/multi.md")
    assert result is not None
    assert "doc-keep" in result
    assert "doc-delete" not in result


@pytest.mark.asyncio
async def test_remove_source_skips_unrelated_pages(service, repo):
    """Page không chứa source_id → không bị ảnh hưởng."""
    page_content = "---\ntitle: Other\nsources: [other-doc]\nlast_updated: 2026-04-09\nversion: 1\n---\n\n# Other"
    repo.ensure_wiki_structure(user_id=USER)
    repo.write_page(user_id=USER, rel_path="pages/topics/other.md", content=page_content)

    await service.remove_source_from_wiki(user_id=USER, source_id="doc-not-here")

    # Page vẫn còn nguyên
    assert repo.read_page(user_id=USER, rel_path="pages/topics/other.md") is not None


# ── _rebuild_index ────────────────────────────────────────────────────────────


def test_rebuild_index_includes_all_pages(service, repo):
    repo.write_page(
        user_id=USER, rel_path="pages/topics/proj-a.md", content="---\ntitle: Project A\n---\n# A"
    )
    repo.write_page(
        user_id=USER,
        rel_path="pages/entities/gemini.md",
        content="---\ntitle: Gemini 2.5 Flash\n---\n# G",
    )
    repo.write_page(
        user_id=USER,
        rel_path="pages/summaries/doc-1.md",
        content="---\ntitle: Document 1 Summary\n---\n# D",
    )

    service._rebuild_index(user_id=USER)

    index = repo.read_index(user_id=USER)
    assert "pages/topics/proj-a.md" in index
    assert "Project A" in index
    assert "pages/entities/gemini.md" in index
    assert "Gemini 2.5 Flash" in index
    assert "pages/summaries/doc-1.md" in index


def test_rebuild_index_empty_wiki_does_nothing(service, repo):
    """Không có page nào → không tạo index."""
    service._rebuild_index(user_id=USER)
    # Không crash, index có thể rỗng hoặc không được tạo
    index = repo.read_index(user_id=USER)
    assert index == ""  # chưa có gì


# ── append_log ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_wiki_appends_log_entry(service, repo):
    topics = [{"slug": "topic-x", "category": "topics", "title": "Topic X"}]
    synth = "---\ntitle: Topic X\nsources: [doc-1]\nlast_updated: 2026-04-09\nversion: 1\n---\n# X"

    with (
        patch.object(service, "_extract_topics", new=AsyncMock(return_value=topics)),
        patch.object(service, "_synthesize_page", new=AsyncMock(return_value=synth)),
    ):
        await service.update_wiki_from_document(
            user_id=USER,
            document_id="doc-1",
            filename="doc.pdf",
            full_text="content",
        )

    from pathlib import Path

    log_content = (Path(repo._base_dir) / USER / "log.md").read_text()
    assert "INGEST" in log_content
    assert "doc.pdf" in log_content
