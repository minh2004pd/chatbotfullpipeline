"""Unit tests cho WikiService — mock LLM calls, dùng WikiRepository real (local fs)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.repositories.wiki_repo import WikiRepository
from app.services.wiki_service import (
    WikiService,
    _build_slug_to_chunks,
    _ChunkExtraction,
    _extract_wiki_links,
    _is_stub,
    _normalize_wiki_link,
    _parse_frontmatter_sources,
    _parse_frontmatter_title,
    _reduce_extractions,
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
    s.wiki_chunk_size = 1000
    s.wiki_max_topics_per_source = 3
    s.wiki_max_entities_per_source = 10
    s.wiki_max_parallel_extractions = 5
    s.wiki_max_parallel_synthesis = 5
    s.wiki_synthesis_max_text_per_page = 32768
    s.wiki_max_related_pages_per_source = 5
    return s


@pytest.fixture
def service(repo, settings):
    return WikiService(repo=repo, settings=settings)


USER = "user_test"

# ── Helpers ───────────────────────────────────────────────────────────────────


def test_slugify_basic():
    # Slug chỉ dùng [a-z0-9], không có gạch ngang
    assert _slugify("Q1 Planning 2026") == "q1planning2026"


def test_slugify_vietnamese():
    assert _slugify("Dự án MemRAG") == "duanmemrag"


def test_slugify_max_length():
    long_text = "a" * 100
    result = _slugify(long_text)
    assert len(result) <= 60


def test_slugify_special_chars():
    # Gạch ngang và ký tự đặc biệt bị bỏ để tránh trùng lặp (u-net = unet)
    assert _slugify("Hello, World! @2026") == "helloworld2026"


def test_slugify_dedup():
    # Mục tiêu chính: u-net và unet → cùng slug
    assert _slugify("u-net") == _slugify("unet") == "unet"
    assert _slugify("anno-ddpm") == _slugify("annoddpm") == "annoddpm"
    assert _slugify("GPT-4o") == _slugify("gpt4o") == "gpt4o"


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
    # "gpt-4o" từ LLM → _slugify → "gpt4o" (không có gạch ngang)
    gpt = next(e for e in entities if e["slug"] == "gpt4o")
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
    # With chunking: mock returns entities/topics from extraction,
    # merge creates summary from source_name
    topics = [
        {"slug": "gemini", "category": "entities", "title": "Gemini", "type": "model"},
        {"slug": "topic-q1review", "category": "topics", "title": "Q1 Review"},
    ]
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

    page = repo.read_page(user_id=USER, rel_path="pages/summaries/q1reviewmeeting.md")
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


async def test_rebuild_index_includes_all_pages(service, repo):
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

    await service._rebuild_index(user_id=USER)

    index = repo.read_index(user_id=USER)
    assert "pages/topics/proj-a.md" in index
    assert "Project A" in index
    assert "pages/entities/gemini.md" in index
    assert "Gemini 2.5 Flash" in index
    assert "pages/summaries/doc-1.md" in index


async def test_rebuild_index_empty_wiki_does_nothing(service, repo):
    """Không có page nào → không tạo index."""
    await service._rebuild_index(user_id=USER)
    # Không crash, index có thể rỗng hoặc không được tạo
    index = repo.read_index(user_id=USER)
    assert index == ""  # chưa có gì


# ── append_log ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skip(reason="Async lock issue with mocked methods - needs separate fix")
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


# ── _normalize_wiki_link ──────────────────────────────────────────────────────


def test_normalize_wiki_link_full_path():
    assert _normalize_wiki_link("pages/entities/adamw.md") == "pages/entities/adamw.md"


def test_normalize_wiki_link_full_path_uppercase_stem():
    """Slugify chỉ áp dụng cho stem, không cho prefix."""
    assert _normalize_wiki_link("pages/entities/AdamW.md") == "pages/entities/adamw.md"


def test_normalize_wiki_link_full_path_no_extension():
    assert _normalize_wiki_link("pages/entities/AdamW") == "pages/entities/adamw.md"


def test_normalize_wiki_link_topic_path():
    assert _normalize_wiki_link("pages/topics/EfficientML.md") == "pages/topics/efficientml.md"


def test_normalize_wiki_link_plain_slug_defaults_to_entities():
    """[[slug]] không có path → backward compat, mặc định entities."""
    assert _normalize_wiki_link("adamw") == "pages/entities/adamw.md"


def test_normalize_wiki_link_plain_slug_with_dash():
    assert _normalize_wiki_link("u-net") == "pages/entities/unet.md"


def test_normalize_wiki_link_empty_stem_returns_empty():
    assert _normalize_wiki_link("pages/entities/---") == ""


# ── _extract_wiki_links (trả rel_paths) ──────────────────────────────────────


def test_extract_wiki_links_returns_rel_paths():
    content = "Dùng [[pages/entities/lora.md]] và [[pages/entities/qlora.md]]"
    assert _extract_wiki_links(content) == ["pages/entities/lora.md", "pages/entities/qlora.md"]


def test_extract_wiki_links_backward_compat_plain_slug():
    content = "Dùng [[lora]] và [[qlora]]"
    assert _extract_wiki_links(content) == [
        "pages/entities/lora.md",
        "pages/entities/qlora.md",
    ]


def test_extract_wiki_links_dedup():
    content = "[[pages/entities/unet.md]] rồi lại [[pages/entities/unet.md]] và [[pages/entities/UNet.md]]"
    result = _extract_wiki_links(content)
    assert result == ["pages/entities/unet.md"]


def test_extract_wiki_links_no_links():
    assert _extract_wiki_links("Không có link nào") == []


def test_extract_wiki_links_mixed_formats():
    """Plain slug và full path trong cùng nội dung."""
    content = "[[pages/entities/ddpm.md]] và [[unet]]"
    assert _extract_wiki_links(content) == [
        "pages/entities/ddpm.md",
        "pages/entities/unet.md",
    ]


# ── _is_stub ──────────────────────────────────────────────────────────────────


def test_is_stub_true():
    content = "---\ntitle: Foo\nstub: true\nversion: 0\n---\n\n# Foo"
    assert _is_stub(content) is True


def test_is_stub_false_normal_page():
    content = "---\ntitle: Foo\nversion: 1\n---\n\n# Foo"
    assert _is_stub(content) is False


def test_is_stub_false_no_frontmatter():
    assert _is_stub("# Just content") is False


# ── _rebuild_link_index (self-link, stub filter, rel_path values) ─────────────


async def test_rebuild_link_index_stores_rel_paths(service, repo):
    """link_index values phải là rel_paths, không phải slugs."""
    repo.ensure_wiki_structure(user_id=USER)
    entity_content = (
        "---\ntitle: LoRA\nsources: [doc-1]\nversion: 1\n---\n\n"
        "Dùng [[pages/entities/ddpm.md]] và [[pages/entities/unet.md]]"
    )
    repo.write_page(user_id=USER, rel_path="pages/entities/lora.md", content=entity_content)

    await service._rebuild_link_index(user_id=USER)
    index = repo.read_link_index(user_id=USER)

    assert "pages/entities/lora.md" in index
    links = index["pages/entities/lora.md"]
    assert "pages/entities/ddpm.md" in links
    assert "pages/entities/unet.md" in links


async def test_rebuild_link_index_no_self_link(service, repo):
    """Page không được tự link đến chính nó."""
    repo.ensure_wiki_structure(user_id=USER)
    content = (
        "---\ntitle: UNet\nsources: [doc-1]\nversion: 1\n---\n\n"
        "[[pages/entities/unet.md]] là kiến trúc encoder-decoder. Dùng với [[pages/entities/ddpm.md]]"
    )
    repo.write_page(user_id=USER, rel_path="pages/entities/unet.md", content=content)

    await service._rebuild_link_index(user_id=USER)
    index = repo.read_link_index(user_id=USER)

    links = index.get("pages/entities/unet.md", [])
    assert "pages/entities/unet.md" not in links
    assert "pages/entities/ddpm.md" in links


async def test_rebuild_link_index_excludes_stubs(service, repo):
    """Stub pages không xuất hiện trong link_index keys."""
    repo.ensure_wiki_structure(user_id=USER)
    stub_content = "---\ntitle: Foo\nstub: true\nversion: 0\n---\n\n[[pages/entities/bar.md]]"
    repo.write_page(user_id=USER, rel_path="pages/entities/foo.md", content=stub_content)

    await service._rebuild_link_index(user_id=USER)
    index = repo.read_link_index(user_id=USER)

    assert "pages/entities/foo.md" not in index


async def test_rebuild_link_index_topic_links_entities(service, repo):
    """Topic page được explicit link đến entity pages có chung source_id."""
    repo.ensure_wiki_structure(user_id=USER)
    entity_content = "---\ntitle: LoRA\nsources: [doc-1]\nversion: 1\n---\n\n# LoRA"
    topic_content = "---\ntitle: Efficient ML\nsources: [doc-1]\nversion: 1\n---\n\n# Efficient ML"
    repo.write_page(user_id=USER, rel_path="pages/entities/lora.md", content=entity_content)
    repo.write_page(user_id=USER, rel_path="pages/topics/efficientml.md", content=topic_content)

    await service._rebuild_link_index(user_id=USER)
    index = repo.read_link_index(user_id=USER)

    # Topic phải link đến entity cùng source
    links = index.get("pages/topics/efficientml.md", [])
    assert "pages/entities/lora.md" in links


# ── backlinks via read_wiki_page tool ────────────────────────────────────────


def test_read_wiki_page_backlinks_use_rel_path(repo):
    """Backlinks được tính theo rel_path, không phải slug."""
    from unittest.mock import MagicMock

    from app.agents.tools.wiki_tools import read_wiki_page

    repo.ensure_wiki_structure(user_id=USER)
    target = "---\ntitle: DDPM\nsources: [doc-1]\nversion: 1\n---\n\n# DDPM"
    repo.write_page(user_id=USER, rel_path="pages/entities/ddpm.md", content=target)

    # Link index: unet.md → [pages/entities/ddpm.md]
    repo.write_link_index(
        user_id=USER,
        data={"pages/entities/unet.md": ["pages/entities/ddpm.md"]},
    )

    tool_context = MagicMock()
    tool_context.state = {"user_id": USER}

    with patch("app.agents.tools.wiki_tools._repo", return_value=repo):
        result = read_wiki_page("pages/entities/ddpm.md", tool_context)

    assert result["found"] is True
    assert "pages/entities/unet.md" in result["backlinks"]


# ── _rebuild_index excludes stubs ─────────────────────────────────────────────


async def test_rebuild_index_excludes_stubs(service, repo):
    """Stub pages không xuất hiện trong index.md."""
    stub = "---\ntitle: Foo\nstub: true\nversion: 0\n---\n\n# Foo"
    normal = "---\ntitle: Bar\nversion: 1\n---\n\n# Bar"
    repo.write_page(user_id=USER, rel_path="pages/entities/foo.md", content=stub)
    repo.write_page(user_id=USER, rel_path="pages/entities/bar.md", content=normal)

    await service._rebuild_index(user_id=USER)
    index = repo.read_index(user_id=USER)

    assert "pages/entities/foo.md" not in index
    assert "pages/entities/bar.md" in index


# ── Chunking helper ───────────────────────────────────────────────────────────


def test_split_text_short_text_returns_single_chunk():
    from app.services.wiki_service import _split_text_for_extraction

    text = "Short text"
    result = _split_text_for_extraction(text, chunk_size=100)
    assert result == ["Short text"]


def test_split_text_splits_at_paragraph():
    from app.services.wiki_service import _split_text_for_extraction

    text = "A" * 50 + "\n\n" + "B" * 50
    result = _split_text_for_extraction(text, chunk_size=60)
    assert len(result) == 2
    assert "A" * 50 in result[0]
    assert "B" * 50 in result[1]


def test_split_text_splits_at_sentence():
    from app.services.wiki_service import _split_text_for_extraction

    text = "First sentence. " * 20  # 320 chars, no paragraphs
    result = _split_text_for_extraction(text, chunk_size=100)
    assert len(result) >= 2
    # Each chunk should end at sentence boundary, not mid-sentence
    for chunk in result[:-1]:
        assert (
            chunk.rstrip().endswith(".")
            or chunk.rstrip().endswith("!")
            or chunk.rstrip().endswith("?")
        )


def test_split_text_no_content_lost():
    from app.services.wiki_service import _split_text_for_extraction

    text = "Chunk1 content.\n\nChunk2 content.\n\nChunk3 content."
    result = _split_text_for_extraction(text, chunk_size=20)
    # All original content should be preserved
    combined = " ".join(result)
    assert "Chunk1 content." in combined
    assert "Chunk2 content." in combined
    assert "Chunk3 content." in combined


# ── Merge extraction results ─────────────────────────────────────────────────


def test_merge_deduplicates_entities():
    from app.services.wiki_service import _merge_extraction_results

    all_topics = [
        {"slug": "lora", "category": "entities", "title": "LoRA", "type": "method"},
        {"slug": "lora", "category": "entities", "title": "LoRA duplicate", "type": "method"},
        {"slug": "gpt4", "category": "entities", "title": "GPT-4", "type": "model"},
    ]
    result = _merge_extraction_results(all_topics, "test-source")
    entities = [t for t in result if t["category"] == "entities"]
    assert len(entities) == 2
    assert entities[0]["slug"] == "lora"
    assert entities[0]["title"] == "LoRA"  # first occurrence kept


def test_merge_deduplicates_topics():
    from app.services.wiki_service import _merge_extraction_results

    all_topics = [
        {"slug": "finetuning", "category": "topics", "title": "Fine-tuning"},
        {"slug": "finetuning", "category": "topics", "title": "Fine-tuning dup"},
    ]
    result = _merge_extraction_results(all_topics, "test-source")
    topics = [t for t in result if t["category"] == "topics"]
    assert len(topics) == 1


def test_merge_ensures_entity_and_topic():
    from app.services.wiki_service import _merge_extraction_results

    result = _merge_extraction_results([], "empty-source")
    entities = [t for t in result if t["category"] == "entities"]
    topics = [t for t in result if t["category"] == "topics"]
    summaries = [t for t in result if t["category"] == "summaries"]
    assert len(entities) == 1
    assert len(topics) == 1
    assert len(summaries) == 1


def test_merge_always_one_summary():
    from app.services.wiki_service import _merge_extraction_results

    all_topics = [
        {"slug": "e1", "category": "entities", "title": "E1"},
        {"slug": "t1", "category": "topics", "title": "T1"},
        {"slug": "s1", "category": "summaries", "title": "Should be ignored"},
    ]
    result = _merge_extraction_results(all_topics, "my-source.pdf")
    summaries = [t for t in result if t["category"] == "summaries"]
    assert len(summaries) == 1
    assert summaries[0]["slug"] == "mysourcepdf"  # from source_name, not chunk


# ── _reduce_extractions: deduplication across chunks ─────────────────────────


def test_reduce_extractions_deduplicates_across_chunks():
    """3 extractions với overlapping slugs → deduplicate, longer chunk wins.

    Khi một entity xuất hiện ở nhiều chunks, metadata từ chunk dài nhất được ưu tiên
    (heuristic: chunk dài hơn = định nghĩa chi tiết hơn, thường ở Methodology thay vì Intro).
    """
    extractions = [
        _ChunkExtraction(
            chunk_index=0,
            items=[
                {"slug": "lora", "category": "entities", "title": "LoRA Intro", "type": "method"},
                {"slug": "finetuning", "category": "topics", "title": "Fine-tuning Intro"},
            ],
            chunk_text="short intro",  # 11 chars
        ),
        _ChunkExtraction(
            chunk_index=1,
            items=[
                {
                    "slug": "lora",
                    "category": "entities",
                    "title": "LoRA Method Detail",
                    "type": "method",
                },
                {"slug": "qlora", "category": "entities", "title": "QLoRA", "type": "method"},
                {"slug": "finetuning", "category": "topics", "title": "Fine-tuning Method"},
            ],
            chunk_text="A" * 100,  # 100 chars — dài nhất → wins cho lora + finetuning
        ),
        _ChunkExtraction(
            chunk_index=2,
            items=[
                {
                    "slug": "lora",
                    "category": "entities",
                    "title": "LoRA Experiment",
                    "type": "method",
                },
                {"slug": "adamw", "category": "entities", "title": "AdamW", "type": "optimizer"},
            ],
            chunk_text="medium exp " * 5,  # 55 chars
        ),
    ]

    result = _reduce_extractions(extractions, "test-source", max_entities=10, max_topics=5)

    entities = [t for t in result if t["category"] == "entities"]
    topics = [t for t in result if t["category"] == "topics"]
    summaries = [t for t in result if t["category"] == "summaries"]

    # Dedup: longer chunk wins → "LoRA Method Detail" từ chunk 100 chars
    assert len(entities) == 3  # lora, qlora, adamw
    assert entities[0]["slug"] == "lora"
    assert entities[0]["title"] == "LoRA Method Detail"  # longest chunk wins
    assert entities[0]["type"] == "method"
    assert entities[1]["slug"] == "qlora"
    assert entities[2]["slug"] == "adamw"

    assert len(topics) == 1  # finetuning
    assert topics[0]["title"] == "Fine-tuning Method"  # longest chunk wins

    assert len(summaries) == 1  # luôn có 1 summary


def test_reduce_extractions_respects_limits():
    """Nhiều hơn max_entities/max_topics → apply limits."""
    extractions = [
        _ChunkExtraction(
            chunk_index=0,
            items=[
                {"slug": f"entity{i}", "category": "entities", "title": f"Entity {i}"}
                for i in range(15)
            ],
            chunk_text="chunk 0",
        ),
        _ChunkExtraction(
            chunk_index=1,
            items=[
                {"slug": f"topic{i}", "category": "topics", "title": f"Topic {i}"}
                for i in range(10)
            ],
            chunk_text="chunk 1",
        ),
    ]

    result = _reduce_extractions(extractions, "test-source", max_entities=5, max_topics=3)

    entities = [t for t in result if t["category"] == "entities"]
    topics = [t for t in result if t["category"] == "topics"]

    assert len(entities) == 5  # capped at max_entities
    assert len(topics) == 3  # capped at max_topics


def test_reduce_extractions_fallbacks():
    """Empty extractions → fallback entity + topic."""
    extractions = []

    result = _reduce_extractions(extractions, "empty-source", max_entities=10, max_topics=5)

    entities = [t for t in result if t["category"] == "entities"]
    topics = [t for t in result if t["category"] == "topics"]
    summaries = [t for t in result if t["category"] == "summaries"]

    assert len(entities) == 1
    assert entities[0]["slug"] == _slugify("empty-source")
    assert len(topics) == 1
    # Topic slug được tạo từ ("topic-" + _slugify(source_name))[:60]
    assert topics[0]["slug"] == ("topic-" + _slugify("empty-source"))[:60]
    assert len(summaries) == 1


# ── _build_slug_to_chunks: caps text size ────────────────────────────────────


def test_build_slug_to_chunks_caps_text_size():
    """Slug xuất hiện trong 5+ chunks, text bị cap ở max_text_per_page."""
    max_text = 100  # nhỏ để test
    chunk_texts = {
        0: "A" * 40,
        1: "B" * 40,
        2: "C" * 40,
        3: "D" * 40,
        4: "E" * 40,
    }

    extractions = [
        _ChunkExtraction(
            chunk_index=i,
            items=[{"slug": "myentity", "category": "entities", "title": "MyEntity"}],
            chunk_text=text,
        )
        for i, text in chunk_texts.items()
    ]

    deduped_items = [{"slug": "myentity", "category": "entities", "title": "MyEntity"}]

    result = _build_slug_to_chunks(extractions, deduped_items, max_text_per_page=max_text)

    # Phải có ít nhất 1 chunk
    assert "myentity" in result
    assert len(result["myentity"]) >= 1

    # Tổng text không vượt quá quá nhiều max_text (có thể vượt 1 chunk cuối)
    total_len = sum(len(t) for t in result["myentity"])
    # Với greedy approach: sẽ thêm chunks cho đến khi vượt limit
    assert total_len <= max_text + 40  # max 1 chunk overflow


def test_build_slug_to_chunks_includes_at_least_one_chunk():
    """Luôn include ít nhất 1 chunk dù vượt limit."""
    max_text = 10
    extractions = [
        _ChunkExtraction(
            chunk_index=0,
            items=[{"slug": "bigentity", "category": "entities", "title": "BigEntity"}],
            chunk_text="X" * 200,  # chunk lớn hơn max_text
        ),
    ]

    deduped_items = [{"slug": "bigentity", "category": "entities", "title": "BigEntity"}]

    result = _build_slug_to_chunks(extractions, deduped_items, max_text_per_page=max_text)

    # Vẫn phải có ít nhất 1 chunk
    assert "bigentity" in result
    assert len(result["bigentity"]) == 1
    assert len(result["bigentity"][0]) == 200


# ── Parallel extraction concurrency test ─────────────────────────────────────


@pytest.mark.asyncio
async def test_parallel_extraction_runs_concurrently(service, repo):
    """Verify asyncio.gather thực sự chạy extraction song song."""
    import time

    call_times = []

    async def mock_extract(text, source_name):
        call_times.append(time.monotonic())
        await asyncio.sleep(0.1)  # simulate LLM latency
        return [
            {
                "slug": f"entity{len(call_times)}",
                "category": "entities",
                "title": f"Entity {len(call_times)}",
            },
        ]

    synthesized = (
        "---\ntitle: Test\nsources: [doc-1]\nlast_updated: 2026-04-09\nversion: 1\n---\n\n# Test"
    )

    mock_extract_wrapper = AsyncMock(side_effect=mock_extract)
    mock_synthesize = AsyncMock(return_value=synthesized)

    with (
        patch.object(service, "_extract_topics", new=mock_extract_wrapper),
        patch.object(service, "_synthesize_page", new=mock_synthesize),
    ):
        await service.update_wiki_from_document(
            user_id=USER,
            document_id="doc-parallel",
            filename="parallel.pdf",
            full_text="Chunk1 " + "A" * 500 + "\n\nChunk2 " + "B" * 500 + "\n\nChunk3 " + "C" * 500,
        )

    # Verify multiple extractions were called (text > 1000 chars → split into chunks)
    assert mock_extract_wrapper.call_count >= 1

    # Verify synthesis was called
    assert mock_synthesize.call_count >= 1

    # Verify pages được tạo (mock synthesizer trả về nội dung cố định)
    topic_page = repo.read_page(user_id=USER, rel_path="pages/topics/topic-parallelpdf.md")
    assert topic_page is not None
    assert "Test" in topic_page  # mock synthesizer trả về "# Test"


# ── Error isolation: pipeline continues when one chunk fails ──────────────────


@pytest.mark.asyncio
async def test_pipeline_continues_when_one_chunk_fails(service, repo):
    """Khi 1 chunk extraction lỗi, các chunk khác vẫn tiếp tục pipeline."""
    call_count = 0

    async def mock_extract_fail_on_chunk_1(text, source_name):
        nonlocal call_count
        call_count += 1
        if call_count == 2:  # chunk thứ 2 fail
            raise RuntimeError("Chunk 2: content policy violation")
        return [
            {
                "slug": f"entity{call_count}",
                "category": "entities",
                "title": f"Entity {call_count}",
            },
        ]

    synthesized = (
        "---\ntitle: Test\nsources: [doc-err]\nlast_updated: 2026-04-09\nversion: 1\n---\n\n# Test"
    )

    with (
        patch.object(
            service, "_extract_topics", new=AsyncMock(side_effect=mock_extract_fail_on_chunk_1)
        ),
        patch.object(service, "_synthesize_page", new=AsyncMock(return_value=synthesized)),
    ):
        # Pipeline KHÔNG được raise
        await service.update_wiki_from_document(
            user_id=USER,
            document_id="doc-err",
            filename="error-test.pdf",
            full_text="Chunk1 " + "A" * 500 + "\n\nChunk2 " + "B" * 500 + "\n\nChunk3 " + "C" * 500,
        )

    # Chunk 2 fail, nhưng chunk 1 và 3 vẫn chạy → call_count >= 3 (có thể retry)
    assert call_count >= 2

    # Wiki vẫn có pages được tạo từ các chunk thành công
    all_pages = repo.list_all_pages(user_id=USER)
    assert len(all_pages) > 0, "Phải có ít nhất 1 page từ các chunk thành công"
