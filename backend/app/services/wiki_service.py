"""WikiService — tổng hợp và duy trì LLM Wiki Layer.

Pipeline:
  Ingestion event (PDF upload / transcript stop)
    → update_wiki_from_document / update_wiki_from_transcript   [fire-and-forget]
      → _process_source()
        → write_raw()
        → _extract_topics() [LLM: gemini-2.0-flash]
        → for each topic:
            read_page() → _synthesize_page() [LLM] → write_page()
        → _rebuild_index()  [rule-based, không cần LLM]
        → append_log()

Deletion event:
    → remove_source_from_wiki()
        → scan pages → re-synthesize hoặc xóa page

Agent READ:
    Chỉ dùng WikiRepository qua ADK tools (read_wiki_index, read_wiki_page).
    WikiService không được gọi trong chat flow.
"""

import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import structlog

from app.core.config import Settings
from app.core.llm_config import get_llm_config
from app.repositories.wiki_repo import WikiRepository
from app.utils.gemini_utils import _with_retry, get_genai_client

logger = structlog.get_logger(__name__)


@dataclass
class _ChunkExtraction:
    """Result of extracting topics from one chunk."""

    chunk_index: int
    items: list[dict]  # entities + topics từ _extract_topics()
    chunk_text: str  # original chunk text


# asyncio.Lock per page path để tránh race condition khi 2 ingestions cùng update 1 trang
_page_locks: dict[str, asyncio.Lock] = {}
# asyncio.Lock per user cho link_index.json (1 file chia sẻ toàn user)
_link_index_locks: dict[str, asyncio.Lock] = {}
# Regex extract [[slug]] links từ wiki content
_WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _get_page_lock(user_id: str, rel_path: str) -> asyncio.Lock:
    key = f"{user_id}:{rel_path}"
    if key not in _page_locks:
        _page_locks[key] = asyncio.Lock()
    return _page_locks[key]


def _get_link_index_lock(user_id: str) -> asyncio.Lock:
    if user_id not in _link_index_locks:
        _link_index_locks[user_id] = asyncio.Lock()
    return _link_index_locks[user_id]


class WikiService:
    def __init__(self, repo: WikiRepository, settings: Settings) -> None:
        self._repo = repo
        self._settings = settings

    # ── Public entry points ───────────────────────────────────────────────────

    async def update_wiki_from_document(
        self,
        *,
        user_id: str,
        document_id: str,
        filename: str,
        full_text: str,
    ) -> None:
        """Entry point sau PDF upload. Safe để gọi với asyncio.create_task."""
        if not self._settings.wiki_enabled:
            return
        from app.core.indexing_status import set_wiki_status

        try:
            await self._process_source(
                user_id=user_id,
                source_id=document_id,
                source_name=filename,
                raw_text=full_text,
                raw_category="documents",
                raw_filename=f"{document_id}.txt",
            )
            set_wiki_status(user_id, document_id, "done")
        except Exception as e:
            set_wiki_status(user_id, document_id, "error")
            logger.error("wiki_update_document_failed", document_id=document_id, error=str(e))

    async def update_wiki_from_transcript(
        self,
        *,
        user_id: str,
        meeting_id: str,
        title: str,
        utterances: list[dict],
    ) -> None:
        """Entry point sau transcript stop. Safe để gọi với asyncio.create_task."""
        if not self._settings.wiki_enabled:
            return
        try:
            full_text = "\n".join(
                f"[{u.get('speaker', 'speaker')}] {u.get('text', '')}"
                for u in utterances
                if u.get("text")
            )
            if not full_text.strip():
                return
            await self._process_source(
                user_id=user_id,
                source_id=meeting_id,
                source_name=title,
                raw_text=full_text,
                raw_category="transcripts",
                raw_filename=f"{meeting_id}.txt",
            )
        except Exception as e:
            logger.error("wiki_update_transcript_failed", meeting_id=meeting_id, error=str(e))

    def normalize_page_filenames(self, *, user_id: str) -> dict[str, int]:
        """Migration: rename/merge các page files có slug không chuẩn về [a-z0-9].

        - "Adam.md" → "adam.md"  (uppercase)
        - "long-context.md" → "longcontext.md"  (gạch ngang)
        - Nếu target đã tồn tại: merge sources, giữ nội dung target (version cao hơn)

        Trả về: {"renamed": N, "merged": N, "skipped": N}
        """
        stats = {"renamed": 0, "merged": 0, "skipped": 0}
        all_pages = self._repo.list_all_pages(user_id=user_id)

        for page_info in all_pages:
            filename = page_info["filename"]
            category = page_info["category"]
            old_rel = page_info["rel_path"]

            raw_slug = filename.replace(".md", "")
            new_slug = _slugify(raw_slug)

            if not new_slug or new_slug == raw_slug:
                stats["skipped"] += 1
                continue  # đã chuẩn rồi

            new_rel = f"pages/{category}/{new_slug}.md"
            old_content = self._repo.read_page(user_id=user_id, rel_path=old_rel) or ""
            existing_new = self._repo.read_page(user_id=user_id, rel_path=new_rel)

            if existing_new:
                # Merge sources: thêm sources của file cũ vào file mới
                old_sources = _parse_frontmatter_sources(old_content)
                new_sources = _parse_frontmatter_sources(existing_new)
                merged_sources = list(
                    dict.fromkeys(new_sources + old_sources)
                )  # deduplicate, preserve order
                if merged_sources != new_sources:
                    updated = re.sub(
                        r"^sources:\s*\[.*?\]",
                        f"sources: [{', '.join(merged_sources)}]",
                        existing_new,
                        flags=re.MULTILINE,
                    )
                    self._repo.write_page(user_id=user_id, rel_path=new_rel, content=updated)
                self._repo.delete_page(user_id=user_id, rel_path=old_rel)
                logger.info("wiki_page_merged", user_id=user_id, old=old_rel, new=new_rel)
                stats["merged"] += 1
            else:
                # Rename: ghi vào path mới, xóa path cũ
                self._repo.write_page(user_id=user_id, rel_path=new_rel, content=old_content)
                self._repo.delete_page(user_id=user_id, rel_path=old_rel)
                logger.info("wiki_page_renamed", user_id=user_id, old=old_rel, new=new_rel)
                stats["renamed"] += 1

        if stats["renamed"] or stats["merged"]:
            self._rebuild_index(user_id=user_id)
            self._rebuild_link_index(user_id=user_id)

        return stats

    async def remove_source_from_wiki(
        self,
        *,
        user_id: str,
        source_id: str,
    ) -> None:
        """
        Dọn dẹp wiki khi source (document hoặc meeting) bị xóa.
        - Page chỉ có 1 source = source này → xóa page.
        - Page có nhiều sources → LLM re-synthesize không có source này.
        - Raw file → xóa.
        - Index & log → luôn cập nhật.
        """
        if not self._settings.wiki_enabled:
            return
        try:
            # 1. Xóa pages liên quan
            all_pages = self._repo.list_all_pages(user_id=user_id)
            pages_deleted = 0
            pages_updated = 0
            for page_info in all_pages:
                rel_path = page_info["rel_path"]
                content = self._repo.read_page(user_id=user_id, rel_path=rel_path)
                if not content or source_id not in content:
                    continue

                sources = _parse_frontmatter_sources(content)
                # Nếu parse thành công và source_id không có trong list → bỏ qua
                # Nếu parse thất bại (sources=[]) nhưng source_id xuất hiện trong content
                # → vẫn xử lý (UUID là unique, chắc chắn page này liên quan đến source)
                if sources and source_id not in sources:
                    continue

                if len(sources) <= 1:
                    # Chỉ có source này → xóa page
                    self._repo.delete_page(user_id=user_id, rel_path=rel_path)
                    # Xóa khỏi link index
                    await self._update_link_index(user_id=user_id, rel_path=rel_path, new_links=[])
                    logger.info("wiki_page_deleted_orphan", user_id=user_id, path=rel_path)
                    pages_deleted += 1
                else:
                    # Nhiều sources → re-synthesize không có source này
                    new_sources = [s for s in sources if s != source_id]
                    new_content = await self._resynthesize_without_source(
                        content=content,
                        removed_source=source_id,
                        remaining_sources=new_sources,
                    )
                    if new_content:
                        async with _get_page_lock(user_id, rel_path):
                            self._repo.write_page(
                                user_id=user_id, rel_path=rel_path, content=new_content
                            )
                            # Cập nhật link index sau khi re-synthesize
                            await self._update_link_index(
                                user_id=user_id,
                                rel_path=rel_path,
                                new_links=_extract_wiki_links(new_content),
                            )
                        pages_updated += 1

            # 2. Xóa raw file (documents hoặc transcripts)
            self._repo.delete_raw(user_id=user_id, source_id=source_id)

            # 3. Luôn rebuild index + link index và ghi log
            self._rebuild_index(user_id=user_id)
            self._rebuild_link_index(user_id=user_id)
            self._repo.append_log(
                user_id=user_id,
                entry=(
                    f"## [{_now_iso()}] DELETE | source={source_id} | "
                    f"pages_deleted={pages_deleted} pages_updated={pages_updated}"
                ),
            )
            logger.info(
                "wiki_remove_source_done",
                user_id=user_id,
                source_id=source_id,
                pages_deleted=pages_deleted,
                pages_updated=pages_updated,
            )
        except Exception as e:
            logger.error("wiki_remove_source_failed", source_id=source_id, error=str(e))

    # ── Core pipeline ─────────────────────────────────────────────────────────

    async def _process_source(
        self,
        *,
        user_id: str,
        source_id: str,
        source_name: str,
        raw_text: str,
        raw_category: str,
        raw_filename: str,
    ) -> None:
        self._repo.ensure_wiki_structure(user_id=user_id)

        # 1. Lưu raw text
        self._repo.write_raw(
            user_id=user_id,
            category=raw_category,
            filename=raw_filename,
            content=raw_text,
        )

        # 2. Split text thành chunks
        chunks = _split_text_for_extraction(raw_text, self._settings.wiki_chunk_size)

        # ── Phase 1: MAP — Parallel Extraction ────────────────────────────────
        semaphore_extract = asyncio.Semaphore(self._settings.wiki_max_parallel_extractions)

        async def _extract_chunk(idx: int, text: str) -> _ChunkExtraction:
            async with semaphore_extract:
                items = await self._extract_topics(text=text, source_name=source_name)
                return _ChunkExtraction(chunk_index=idx, items=items, chunk_text=text)

        # return_exceptions=True: nếu 1 chunk lỗi, các chunk khác vẫn tiếp tục
        raw_results = await asyncio.gather(
            *[_extract_chunk(i, chunk) for i, chunk in enumerate(chunks)],
            return_exceptions=True,
        )

        # Lọc kết quả thành công, log lỗi các chunk thất bại
        extractions: list[_ChunkExtraction] = []
        for i, result in enumerate(raw_results):
            if isinstance(result, Exception):
                logger.warning(
                    "wiki_extraction_chunk_failed",
                    user_id=user_id,
                    source=source_name,
                    chunk_index=i,
                    error=str(result),
                )
            else:
                extractions.append(result)

        if not extractions:
            # Tất cả chunks lỗi → fallback toàn bộ
            logger.error(
                "wiki_extraction_all_chunks_failed",
                user_id=user_id,
                source=source_name,
            )
            extractions = [
                _ChunkExtraction(
                    chunk_index=0,
                    items=[
                        {"slug": _slugify(source_name), "category": "entities", "title": source_name, "type": ""},
                        {
                            "slug": ("topic-" + _slugify(source_name))[:60],
                            "category": "topics",
                            "title": f"Chủ đề: {source_name}",
                        },
                        {"slug": _slugify(source_name), "category": "summaries", "title": f"Tóm tắt: {source_name}"},
                    ],
                    chunk_text=raw_text[: self._settings.wiki_chunk_size],
                )
            ]

        # Sort by chunk_index để đảm bảo thứ tự
        extractions = sorted(extractions, key=lambda e: e.chunk_index)

        logger.info(
            "wiki_map_phase_done",
            user_id=user_id,
            source=source_name,
            chunks=len(chunks),
            extractions=len(extractions),
            failed=len(chunks) - len(extractions),
        )

        # ── Phase 2: REDUCE — Merge & Deduplicate ─────────────────────────────
        deduped_items = _reduce_extractions(
            extractions,
            source_name,
            self._settings.wiki_max_entities_per_source,
            self._settings.wiki_max_topics_per_source,
        )

        slug_to_chunks = _build_slug_to_chunks(
            extractions,
            deduped_items,
            self._settings.wiki_synthesis_max_text_per_page,
        )

        # Count entities và topics để logging
        total_entities = sum(1 for item in deduped_items if item["category"] == "entities")
        total_topics = sum(1 for item in deduped_items if item["category"] == "topics")
        has_summary = any(item["category"] == "summaries" for item in deduped_items)

        # Build danh sách pages cần synthesize
        pages_to_synthesize: list[tuple[dict, str, str]] = []  # (item, existing_content, merged_text)
        all_processed_paths: set[str] = set()

        for item in deduped_items:
            slug = item.get("slug", "")
            category = item.get("category", "summaries")
            if not slug:
                continue

            rel_path = f"pages/{category}/{slug}.md"
            existing = self._repo.read_page(user_id=user_id, rel_path=rel_path) or ""

            # Merge tất cả chunks liên quan thành 1 text cho page này
            chunk_texts = slug_to_chunks.get(slug, [""])
            merged_text = "\n\n".join(chunk_texts) if chunk_texts else ""

            pages_to_synthesize.append((item, existing, merged_text))

        logger.info(
            "wiki_reduce_phase_done",
            user_id=user_id,
            source=source_name,
            pages_to_synthesize=len(pages_to_synthesize),
            entities=total_entities,
            topics=total_topics,
        )

        # ── Phase 3: PARALLEL SYNTHESIS ───────────────────────────────────────
        semaphore_synth = asyncio.Semaphore(self._settings.wiki_max_parallel_synthesis)

        async def _synthesize_one_page(
            item: dict, existing: str, merged_text: str
        ) -> tuple[str, str | None]:
            """Synthesize 1 page, trả về (rel_path, new_content_or_None)."""
            async with semaphore_synth:
                slug = item.get("slug", "")
                category = item.get("category", "summaries")
                title = item.get("title", slug)
                topic_type = item.get("type", "")
                rel_path = f"pages/{category}/{slug}.md"

                new_content = await self._synthesize_page(
                    user_id=user_id,
                    existing_content=existing,
                    new_text=merged_text,  # merged từ TẤT CẢ chunks liên quan
                    topic_title=title,
                    topic_type=topic_type,
                    source_name=source_name,
                    source_id=source_id,
                )
                return (rel_path, new_content)

        # Chạy synthesis song song
        synthesis_results = await asyncio.gather(
            *[_synthesize_one_page(item, existing, merged_text) for item, existing, merged_text in pages_to_synthesize]
        )

        # Ghi kết quả vào wiki + update link index + ghost stubs
        ghost_stub_tasks = []
        link_index_tasks = []

        for rel_path, new_content in synthesis_results:
            if new_content:
                async with _get_page_lock(user_id, rel_path):
                    self._repo.write_page(user_id=user_id, rel_path=rel_path, content=new_content)
                    all_processed_paths.add(rel_path)
                    logger.info("wiki_page_updated", user_id=user_id, path=rel_path)

                # Cập nhật forward links + tạo ghost stubs (batch sau)
                links = _extract_wiki_links(new_content)
                link_index_tasks.append(
                    self._update_link_index(user_id=user_id, rel_path=rel_path, new_links=links)
                )
                ghost_stub_tasks.append(
                    self._create_ghost_stubs(
                        user_id=user_id,
                        content=new_content,
                        source_id=source_id,
                        source_name=source_name,
                    )
                )

        # Batch ghost stubs + link index updates
        if link_index_tasks:
            await asyncio.gather(*link_index_tasks)
        if ghost_stub_tasks:
            await asyncio.gather(*ghost_stub_tasks)

        # ── Phase 4: FINALIZATION ─────────────────────────────────────────────
        # Update related pages
        related_updated = await self._update_related_pages(
            user_id=user_id,
            source_id=source_id,
            source_name=source_name,
            raw_text=raw_text,
            processed_paths=all_processed_paths,
        )

        # Rebuild index + link index (1 lần cuối)
        self._rebuild_index(user_id=user_id)
        self._rebuild_link_index(user_id=user_id)

        # Log
        self._repo.append_log(
            user_id=user_id,
            entry=(
                f"## [{_now_iso()}] INGEST | {raw_category} | {source_name} | "
                f"chunks={len(chunks)} entities={total_entities} topics={total_topics} "
                f"summaries={1 if has_summary else 0} related_updated={related_updated}"
            ),
        )
        logger.info(
            "wiki_process_done",
            user_id=user_id,
            source=source_name,
            chunks=len(chunks),
            entities=total_entities,
            topics=total_topics,
            summaries=1 if has_summary else 0,
            related_updated=related_updated,
        )

    # ── LLM calls ─────────────────────────────────────────────────────────────

    async def _extract_topics(self, text: str, source_name: str) -> list[dict]:
        """Gọi LLM để extract entities + topics + summary. Fallback về summary từ source_name."""
        config = get_llm_config()
        client = get_genai_client()
        prompt_template = config.prompts.wiki_topic_extract_prompt

        if not prompt_template:
            return [{"slug": _slugify(source_name), "category": "summaries", "title": source_name}]

        prompt = prompt_template.format(
            max_entities=self._settings.wiki_max_entities_per_source,
            max_topics=self._settings.wiki_max_topics_per_source,
            source_name=source_name,
            text=text,
        )

        try:

            async def _call():
                return await client.aio.models.generate_content(
                    model=config.llm.summary_model,
                    contents=prompt,
                )

            response = await _with_retry(_call)
            raw = (response.text or "").strip()

            # Parse JSON object {"entities": [...], "topics": [...], "summary": {...}}
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                if isinstance(parsed, dict):
                    entities: list[dict] = []
                    topics: list[dict] = []

                    # Entities — giữ lại "type" để dùng đúng template synthesis
                    for e in parsed.get("entities", []):
                        if isinstance(e, dict) and e.get("slug"):
                            entities.append(
                                {
                                    "slug": _slugify(e["slug"]),
                                    "category": "entities",
                                    "title": e.get("title", e["slug"]),
                                    "type": e.get("type", ""),  # model|framework|dataset|...
                                }
                            )

                    # Topics
                    for t in parsed.get("topics", []):
                        if isinstance(t, dict) and t.get("slug"):
                            topics.append(
                                {
                                    "slug": _slugify(t["slug"]),
                                    "category": "topics",
                                    "title": t.get("title", t["slug"]),
                                }
                            )

                    # Đảm bảo luôn có ít nhất 1 entity
                    if not entities:
                        entities.append(
                            {
                                "slug": _slugify(source_name),
                                "category": "entities",
                                "title": source_name,
                                "type": "",
                            }
                        )
                        logger.warning("wiki_no_entities_fallback", source=source_name)

                    # Đảm bảo luôn có ít nhất 1 topic
                    if not topics:
                        topics.append(
                            {
                                "slug": ("topic-" + _slugify(source_name))[:60],
                                "category": "topics",
                                "title": f"Chủ đề: {source_name}",
                            }
                        )
                        logger.warning("wiki_no_topics_fallback", source=source_name)

                    # Summary — luôn có đúng 1
                    s = parsed.get("summary")
                    if isinstance(s, dict) and s.get("slug"):
                        summary = {
                            "slug": _slugify(s["slug"]),
                            "category": "summaries",
                            "title": s.get("title", f"Tóm tắt: {source_name}"),
                        }
                    else:
                        summary = {
                            "slug": _slugify(source_name),
                            "category": "summaries",
                            "title": f"Tóm tắt: {source_name}",
                        }

                    return entities + topics + [summary]
        except Exception as e:
            logger.warning("wiki_extract_topics_failed", error=str(e))

        # Fallback toàn bộ: đảm bảo cả 3 categories khi LLM fail hoàn toàn
        base_slug = _slugify(source_name)
        return [
            {"slug": base_slug, "category": "entities", "title": source_name},
            {
                "slug": ("topic-" + base_slug)[:60],
                "category": "topics",
                "title": f"Chủ đề: {source_name}",
            },
            {"slug": base_slug, "category": "summaries", "title": f"Tóm tắt: {source_name}"},
        ]

    async def _synthesize_page(
        self,
        *,
        user_id: str,
        existing_content: str,
        new_text: str,
        topic_title: str,
        topic_type: str = "",
        source_name: str,
        source_id: str,
    ) -> str:
        """Gọi LLM để merge existing wiki với nội dung mới.

        Inject wiki_schema.md của user làm nguồn sự thật về quy tắc synthesis —
        thay đổi schema file là thay đổi ngay hành vi LLM, không cần restart.
        """
        config = get_llm_config()
        client = get_genai_client()
        prompt_template = config.prompts.wiki_synthesis_prompt

        if not prompt_template:
            # Fallback đơn giản không cần LLM
            return _simple_page(topic_title, topic_type, source_name, source_id, new_text)

        # Strip code fence từ existing_content (có thể còn sót từ LLM trước đó)
        clean_existing = _strip_code_fence(existing_content.strip()) if existing_content else ""

        # Dynamic schema injection: đọc wiki_schema.md của user (Single Source of Truth)
        schema = self._repo.read_schema(user_id=user_id)

        prompt = prompt_template.format(
            topic_title=topic_title,
            topic_type=topic_type or "auto",
            source_name=source_name,
            source_id=source_id,
            existing_content=clean_existing or "(trang mới, chưa có nội dung)",
            new_text=new_text,
            schema=schema,
        )

        try:

            async def _call():
                return await client.aio.models.generate_content(
                    model=config.llm.summary_model,
                    contents=prompt,
                )

            response = await _with_retry(_call)
            raw = (response.text or "").strip()
            return _strip_code_fence(raw)
        except Exception as e:
            logger.warning("wiki_synthesize_failed", topic=topic_title, error=str(e))
            return _simple_page(topic_title, topic_type, source_name, source_id, new_text)

    async def _resynthesize_without_source(
        self,
        *,
        content: str,
        removed_source: str,
        remaining_sources: list[str],
    ) -> str:
        """Re-synthesize page không có source đã bị xóa."""
        config = get_llm_config()
        client = get_genai_client()
        prompt = (
            f"Trang Wiki sau đây có tham chiếu nguồn '{removed_source}' vừa bị xóa.\n"
            f"Hãy cập nhật trang Wiki này: xóa các thông tin CHỈ đến từ nguồn '{removed_source}', "
            f"giữ nguyên thông tin từ các nguồn khác ({', '.join(remaining_sources)}).\n"
            f"Cập nhật frontmatter: bỏ '{removed_source}' khỏi sources list.\n\n"
            f"## Nội dung hiện tại:\n{content}"
        )
        try:

            async def _call():
                return await client.aio.models.generate_content(
                    model=config.llm.summary_model,
                    contents=prompt,
                )

            response = await _with_retry(_call)
            return (response.text or "").strip()
        except Exception as e:
            logger.warning("wiki_resynthesize_failed", error=str(e))
            return ""

    # ── Index rebuild (rule-based) ────────────────────────────────────────────

    def _rebuild_index(self, *, user_id: str) -> None:
        """Rebuild index.md từ tất cả pages hiện có (parse frontmatter, không cần LLM)."""
        all_pages = self._repo.list_all_pages(user_id=user_id)
        if not all_pages:
            return

        sections: dict[str, list[str]] = {"entities": [], "topics": [], "summaries": []}

        for page_info in all_pages:
            rel_path = page_info["rel_path"]
            category = page_info["category"]
            filename = page_info["filename"]
            content = self._repo.read_page(user_id=user_id, rel_path=rel_path) or ""
            if _is_stub(content):
                continue
            title = (
                _parse_frontmatter_title(content)
                or filename.replace(".md", "").replace("-", " ").title()
            )
            summary = _extract_page_summary(content)
            if summary:
                line = f"- [[{rel_path}]] — **{title}** — {summary}"
            else:
                line = f"- [[{rel_path}]] — **{title}**"
            sections.get(category, sections["summaries"]).append(line)

        lines = ["# Wiki Index\n"]
        if sections["entities"]:
            lines.append("## Entities\n")
            lines.extend(sections["entities"])
            lines.append("")
        if sections["topics"]:
            lines.append("## Topics\n")
            lines.extend(sections["topics"])
            lines.append("")
        if sections["summaries"]:
            lines.append("## Summaries\n")
            lines.extend(sections["summaries"])
            lines.append("")

        self._repo.write_index(user_id=user_id, content="\n".join(lines))

    # ── Link index management ─────────────────────────────────────────────────

    async def _update_link_index(
        self, *, user_id: str, rel_path: str, new_links: list[str]
    ) -> None:
        """Cập nhật forward links cho 1 page. Thread-safe qua user-level lock."""
        async with _get_link_index_lock(user_id):
            index = self._repo.read_link_index(user_id=user_id)
            if new_links:
                filtered = [lp for lp in dict.fromkeys(new_links) if lp != rel_path]
                if filtered:
                    index[rel_path] = filtered
                else:
                    index.pop(rel_path, None)
            else:
                index.pop(rel_path, None)
            self._repo.write_link_index(user_id=user_id, data=index)

    def _rebuild_link_index(self, *, user_id: str) -> None:
        """Rebuild toàn bộ link index từ scratch bằng cách scan tất cả pages.

        Values trong index là rel_paths (không phải slugs).
        Bỏ qua stub pages và self-links.
        Topic/summary pages được link tường minh đến tất cả entity pages
        có chung source_id trong frontmatter.
        """
        all_pages = self._repo.list_all_pages(user_id=user_id)

        # Pass 1: thu thập content + links cơ bản (rel_path → list[rel_path])
        page_contents: dict[str, str] = {}
        index: dict[str, list[str]] = {}
        for page_info in all_pages:
            rel_path = page_info["rel_path"]
            content = self._repo.read_page(user_id=user_id, rel_path=rel_path)
            if not content or _is_stub(content):
                continue
            page_contents[rel_path] = content
            links = [lp for lp in _extract_wiki_links(content) if lp != rel_path]
            if links:
                index[rel_path] = links

        # Pass 2: build source_id → entity rel_paths map
        source_to_entity_paths: dict[str, set[str]] = {}
        for rel_path, content in page_contents.items():
            if not rel_path.startswith("pages/entities/"):
                continue
            for src in _parse_frontmatter_sources(content):
                source_to_entity_paths.setdefault(src, set()).add(rel_path)

        # Pass 3: topic/summary pages → merge explicit entity rel_path links
        for rel_path, content in page_contents.items():
            category = rel_path.split("/")[1] if rel_path.count("/") >= 2 else ""
            if category not in ("topics", "summaries"):
                continue
            extra: set[str] = set()
            for src in _parse_frontmatter_sources(content):
                extra.update(source_to_entity_paths.get(src, set()))
            extra.discard(rel_path)  # no self-link
            if extra:
                existing = set(index.get(rel_path, []))
                merged = list(dict.fromkeys(index.get(rel_path, []) + sorted(extra - existing)))
                index[rel_path] = merged

        self._repo.write_link_index(user_id=user_id, data=index)

    # ── Ghost Link stubs ──────────────────────────────────────────────────────

    async def _create_ghost_stubs(
        self, *, user_id: str, content: str, source_id: str, source_name: str
    ) -> list[str]:
        """Tạo stub page cho [[rel_path]] chưa tồn tại trong wiki.

        Giúp agent biết entity đã được nhắc đến nhưng chưa có chi tiết.
        Stub có version=0 và stub=true trong frontmatter.
        """
        links = _extract_wiki_links(content)  # trả về rel_paths
        if not links:
            return []

        existing_paths = {
            page_info["rel_path"] for page_info in self._repo.list_all_pages(user_id=user_id)
        }

        stubs_created = []
        for link_rel_path in links:
            if link_rel_path in existing_paths:
                continue
            slug = _slugify(Path(link_rel_path).stem)
            stub_content = _stub_page(slug, source_id, source_name)
            async with _get_page_lock(user_id, link_rel_path):
                if not self._repo.read_page(user_id=user_id, rel_path=link_rel_path):
                    self._repo.write_page(
                        user_id=user_id, rel_path=link_rel_path, content=stub_content
                    )
                    stubs_created.append(link_rel_path)
                    logger.info("wiki_stub_created", user_id=user_id, rel_path=link_rel_path)

        return stubs_created

    # ── Smart re-ingestion ────────────────────────────────────────────────────

    def _score_related_page(
        self, rel_path: str, link_index: dict[str, list[str]], user_id: str
    ) -> tuple[int, str]:
        """Score page để ưu tiên sort:
        - backlink_count cao → hub page → ưu tiên cao
        - last_updated cũ → cần làm mới → ưu tiên cao
        Trả về tuple để sort ascending: (-backlink_count, last_updated).
        """
        backlink_count = sum(1 for links in link_index.values() if rel_path in links)
        content = self._repo.read_page(user_id=user_id, rel_path=rel_path) or ""
        last_updated = _parse_frontmatter_date(content) or "2000-01-01"
        return (-backlink_count, last_updated)

    async def _update_related_pages(
        self,
        *,
        user_id: str,
        source_id: str,
        source_name: str,
        raw_text: str,
        processed_paths: set[str],
    ) -> int:
        """Tìm và update các pages hiện có đang link đến các entities vừa được process.

        Dùng link_index.json để tra cứu hiệu quả. Sort theo hub score trước khi
        giới hạn số lượng.
        """
        link_index = self._repo.read_link_index(user_id=user_id)
        if not link_index:
            return 0

        # Tìm pages link đến ít nhất 1 entity vừa được process (dùng rel_path)
        related: list[str] = []
        for rel_path, links in link_index.items():
            if rel_path in processed_paths:
                continue
            if any(p in links for p in processed_paths):
                related.append(rel_path)

        if not related:
            return 0

        # Sort: hub pages (nhiều backlinks) trước, pages cũ trước
        related.sort(key=lambda p: self._score_related_page(p, link_index, user_id))
        related = related[: self._settings.wiki_max_related_pages_per_source]

        updated = 0
        for rel_path in related:
            existing = self._repo.read_page(user_id=user_id, rel_path=rel_path) or ""
            topic_title = _parse_frontmatter_title(existing) or rel_path
            category = rel_path.split("/")[1]  # entities|topics|summaries

            async with _get_page_lock(user_id, rel_path):
                new_content = await self._synthesize_page(
                    user_id=user_id,
                    existing_content=existing,
                    new_text=raw_text,
                    topic_title=topic_title,
                    topic_type=category,
                    source_name=source_name,
                    source_id=source_id,
                )
                if new_content:
                    self._repo.write_page(user_id=user_id, rel_path=rel_path, content=new_content)
                    await self._update_link_index(
                        user_id=user_id,
                        rel_path=rel_path,
                        new_links=_extract_wiki_links(new_content),
                    )
                    logger.info("wiki_related_page_updated", user_id=user_id, path=rel_path)
            updated += 1

        return updated


# ── Helpers ───────────────────────────────────────────────────────────────────


def _split_text_for_extraction(text: str, chunk_size: int) -> list[str]:
    """Split text thành chunks ~chunk_size chars tại paragraph/sentence boundaries.

    Ưu tiên split tại \n\n (paragraph), fallback tại .!? (sentence),
    cuối cùng fallback tại chunk_size cứng.
    Đảm bảo không bỏ sót nội dung.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:])
            break

        # Ưu tiên split tại paragraph boundary
        paragraph_pos = text.rfind("\n\n", start, end)
        # Fallback: sentence boundary
        sentence_pos = -1
        for punct in (". ", "! ", "? ", "\n"):
            pos = text.rfind(punct, start, end)
            if pos > paragraph_pos:
                sentence_pos = max(sentence_pos, pos + 1)

        if paragraph_pos > start + chunk_size // 2:
            split_at = paragraph_pos + 2  # skip \n\n
        elif sentence_pos > start + chunk_size // 2:
            split_at = sentence_pos
        else:
            split_at = end  # hard cut

        chunks.append(text[start:split_at].strip())
        start = split_at

    return [c for c in chunks if c.strip()]


def _reduce_extractions(
    extractions: list[_ChunkExtraction],
    source_name: str,
    max_entities: int,
    max_topics: int,
) -> list[dict]:
    """Merge và deduplicate extraction results từ nhiều chunks.

    - Flatten tất cả items từ extractions (sorted by chunk_index)
    - Deduplicate entities/topics by slug: "longer chunk wins" — metadata từ chunk
      dài hơn được ưu tiên (heuristic: chunk dài hơn = định nghĩa chi tiết hơn,
      thường ở Methodology thay vì Introduction)
    - Apply global limits (max_entities, max_topics)
    - Luôn tạo 1 summary từ source_name
    - Fallback entities/topics nếu empty
    """
    # Group items by (category, slug) để so sánh
    # Key: (category, slug) → list of (item, chunk_text_length)
    slug_groups: dict[tuple[str, str], list[tuple[dict, int]]] = {}

    # Sort by chunk_index để đảm bảo thứ tự ổn định
    sorted_extractions = sorted(extractions, key=lambda e: e.chunk_index)

    for extraction in sorted_extractions:
        chunk_len = len(extraction.chunk_text)
        for item in extraction.items:
            category = item.get("category", "")
            slug = item.get("slug", "")
            if not slug or category not in ("entities", "topics"):
                continue
            key = (category, slug)
            slug_groups.setdefault(key, []).append((item, chunk_len))

    # Chọn metadata: "longer chunk wins" — nếu cùng slug, lấy item từ chunk dài nhất
    best_entity_items: list[dict] = []
    best_topic_items: list[dict] = []

    for (category, slug), instances in slug_groups.items():
        # Sort by chunk length descending → "longer wins"
        instances.sort(key=lambda x: x[1], reverse=True)
        best_item = instances[0][0]  # item từ chunk dài nhất

        if category == "entities":
            best_entity_items.append(best_item)
        else:
            best_topic_items.append(best_item)

    # Apply global limits — giữ nguyên thứ tự xuất hiện (theo chunk_index của best instance)
    entities = best_entity_items[:max_entities]
    topics = best_topic_items[:max_topics]

    # Fallback: đảm bảo luôn có ít nhất 1 entity và 1 topic
    if not entities:
        entities.append(
            {
                "slug": _slugify(source_name),
                "category": "entities",
                "title": source_name,
                "type": "",
            }
        )
        logger.warning("wiki_no_entities_after_reduce", source=source_name)

    if not topics:
        topics.append(
            {
                "slug": ("topic-" + _slugify(source_name))[:60],
                "category": "topics",
                "title": f"Chủ đề: {source_name}",
            }
        )
        logger.warning("wiki_no_topics_after_reduce", source=source_name)

    # Summary: luôn có đúng 1
    summary = {
        "slug": _slugify(source_name),
        "category": "summaries",
        "title": f"Tóm tắt: {source_name}",
    }

    return entities + topics + [summary]


def _build_slug_to_chunks(
    extractions: list[_ChunkExtraction],
    deduped_items: list[dict],
    max_text_per_page: int,
) -> dict[str, list[str]]:
    """Map slug → list of chunk texts mention nó.

    - Greedily add chunks cho đến khi vượt max_text_per_page
    - Luôn include ít nhất 1 chunk
    """
    # Build set of slugs we care about
    target_slugs = {item["slug"] for item in deduped_items}

    # Map slug → list of chunk texts
    slug_to_chunks: dict[str, list[str]] = {slug: [] for slug in target_slugs}

    # Sort extractions by chunk_index
    sorted_extractions = sorted(extractions, key=lambda e: e.chunk_index)

    for extraction in sorted_extractions:
        for item in extraction.items:
            slug = item.get("slug", "")
            if slug in target_slugs:
                current_total = sum(len(t) for t in slug_to_chunks[slug])
                # Always include at least 1 chunk
                if not slug_to_chunks[slug] or current_total + len(extraction.chunk_text) <= max_text_per_page:
                    slug_to_chunks[slug].append(extraction.chunk_text)

    return slug_to_chunks


def _merge_extraction_results(all_topics: list[dict], source_name: str) -> list[dict]:
    """Merge extraction results từ nhiều chunks.

    - Entities: deduplicate by slug, giữ lại phần tử đầu tiên
    - Topics: deduplicate by slug, giữ lại phần tử đầu tiên
    - Summary: luôn giữ 1 (từ source_name, không phụ thuộc chunk)
    """
    seen_entities: set[str] = set()
    seen_topics: set[str] = set()
    entities: list[dict] = []
    topics: list[dict] = []

    for item in all_topics:
        category = item.get("category", "")
        slug = item.get("slug", "")
        if not slug:
            continue

        if category == "entities" and slug not in seen_entities:
            seen_entities.add(slug)
            entities.append(item)
        elif category == "topics" and slug not in seen_topics:
            seen_topics.add(slug)
            topics.append(item)

    # Đảm bảo luôn có ít nhất 1 entity và 1 topic
    if not entities:
        entities.append(
            {
                "slug": _slugify(source_name),
                "category": "entities",
                "title": source_name,
                "type": "",
            }
        )
        logger.warning("wiki_no_entities_after_merge", source=source_name)

    if not topics:
        topics.append(
            {
                "slug": ("topic-" + _slugify(source_name))[:60],
                "category": "topics",
                "title": f"Chủ đề: {source_name}",
            }
        )
        logger.warning("wiki_no_topics_after_merge", source=source_name)

    # Summary: luôn có đúng 1
    summary = {
        "slug": _slugify(source_name),
        "category": "summaries",
        "title": f"Tóm tắt: {source_name}",
    }

    return entities + topics + [summary]


def _strip_code_fence(text: str) -> str:
    """Bỏ code fence wrapper nếu LLM bọc output trong ```markdown``` block."""
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    # Bỏ dòng đầu (```markdown hoặc ```)
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    # Bỏ dòng cuối nếu là closing fence
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_page_summary(content: str, max_len: int = 120) -> str:
    """Extract 1-line summary from page content (first paragraph after frontmatter).

    Skips frontmatter, title header, and blockquotes.
    """
    # Strip frontmatter
    body = re.sub(r"^---\s*\n.*?\n---", "", content.strip(), flags=re.DOTALL).strip()
    # Strip title header (# ...)
    body = re.sub(r"^#\s+.*$", "", body, flags=re.MULTILINE).strip()
    # Take first non-empty, non-quote, non-header line
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith(">") and not line.startswith("#"):
            if len(line) > max_len:
                return line[:max_len] + "..."
            return line
    return ""


def _slugify(text: str) -> str:
    """Normalize text thành slug chỉ gồm [a-z0-9], tối đa 60 ký tự.

    Không dùng dấu gạch ngang để tránh trùng lặp thực thể:
    "u-net" và "unet" → cùng slug "unet",
    "anno-ddpm" và "anoddpm" → cùng slug "annoddpm".
    """
    # Bỏ dấu tiếng Việt
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    # Lowercase, bỏ tất cả ký tự không phải a-z0-9
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())[:60]


def _parse_frontmatter(content: str) -> str:
    """Extract phần nội dung YAML frontmatter (giữa 2 dấu ---). Trả về "" nếu không có."""
    # Bỏ code fence nếu LLM wrap output
    stripped = _strip_code_fence(content.strip())
    match = re.search(r"^---\s*\n(.*?)\n---", stripped, re.DOTALL)
    return match.group(1) if match else ""


def _parse_frontmatter_title(content: str) -> str:
    """Lấy title từ YAML frontmatter."""
    fm = _parse_frontmatter(content)
    if fm:
        title_match = re.search(r"^title:\s*(.+)$", fm, re.MULTILINE)
        if title_match:
            return title_match.group(1).strip().strip("\"'")
    return ""


def _parse_frontmatter_type(content: str) -> str:
    """Lấy type từ YAML frontmatter."""
    fm = _parse_frontmatter(content)
    if fm:
        type_match = re.search(r"^type:\s*(.+)$", fm, re.MULTILINE)
        if type_match:
            return type_match.group(1).strip().strip("\"'")
    return ""


def _is_stub(content: str) -> bool:
    """Trả về True nếu page là stub (stub: true trong frontmatter)."""
    fm = _parse_frontmatter(content)
    if fm:
        return bool(re.search(r"^stub:\s*true\s*$", fm, re.MULTILINE))
    return False


def _parse_frontmatter_sources(content: str) -> list[str]:
    """Lấy sources list từ YAML frontmatter.

    Hỗ trợ formats:
      sources: [id1, id2]
      sources: ["id1", "id2"]
    """
    fm = _parse_frontmatter(content)
    if not fm:
        return []
    # Dùng [^\]]* thay vì .+ để tránh vượt qua dấu ] và $ optional (không cần strict EOL)
    sources_match = re.search(r"^sources:\s*\[([^\]]*)\]", fm, re.MULTILINE)
    if sources_match:
        raw = sources_match.group(1)
        return [s.strip().strip("\"'") for s in raw.split(",") if s.strip()]
    return []


def _normalize_wiki_link(raw: str) -> str:
    """Chuẩn hóa nội dung [[...]] thành rel_path chuẩn.

    [[pages/entities/AdamW.md]]  → "pages/entities/adamw.md"  (slugify stem only)
    [[pages/topics/Foo Bar.md]]  → "pages/topics/foobar.md"
    [[adamw]]                    → "pages/entities/adamw.md"   (backward compat)
    """
    raw = raw.strip()
    if "/" in raw:
        # Đã có path prefix: chỉ slugify phần filename stem
        prefix, filename = raw.rsplit("/", 1)
        stem = filename[:-3] if filename.endswith(".md") else filename
        slug = _slugify(stem)
        return f"{prefix}/{slug}.md" if slug else ""
    else:
        # Plain slug (backward compat): mặc định category entities
        slug = _slugify(raw)
        return f"pages/entities/{slug}.md" if slug else ""


def _extract_wiki_links(content: str) -> list[str]:
    """Extract [[...]] refs từ wiki page content, trả về rel_paths đã chuẩn hóa.

    Slugify CHỈ áp dụng cho phần filename stem, không áp dụng lên toàn bộ path.
    Dedup nhưng giữ thứ tự xuất hiện đầu tiên.
    """
    seen: set[str] = set()
    result = []
    for raw in _WIKI_LINK_RE.findall(content):
        rel_path = _normalize_wiki_link(raw)
        if rel_path and rel_path not in seen:
            seen.add(rel_path)
            result.append(rel_path)
    return result


def _parse_frontmatter_date(content: str) -> str:
    """Lấy last_updated từ YAML frontmatter. Trả về "" nếu không có."""
    fm = _parse_frontmatter(content)
    if fm:
        match = re.search(r"^last_updated:\s*(.+)$", fm, re.MULTILINE)
        if match:
            return match.group(1).strip()
    return ""


def _stub_page(slug: str, source_id: str, source_name: str) -> str:
    """Tạo minimal stub page cho entity chưa có trang chi tiết."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = slug.replace("-", " ").title()
    return (
        f"---\n"
        f"title: {title}\n"
        f"tags: []\n"
        f"type: concept\n"
        f"sources: [{source_id}]\n"
        f"last_updated: {today}\n"
        f"version: 0\n"
        f"stub: true\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"> **Stub page** — Thực thể này được nhắc đến trong [{source_name}] nhưng chưa có trang chi tiết.\n"
        f"> Trang này sẽ được tự động làm giàu khi có thêm tài liệu liên quan.\n"
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _simple_page(
    topic_title: str, topic_type: str, source_name: str, source_id: str, text: str
) -> str:
    """Fallback page khi LLM không khả dụng."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    excerpt = text[:500].replace("\n", " ")
    type_line = f"type: {topic_type}\n" if topic_type else ""
    return (
        f"---\n"
        f"title: {topic_title}\n"
        f"tags: []\n"
        f"{type_line}"
        f"sources: [{source_id}]\n"
        f"last_updated: {today}\n"
        f"version: 1\n"
        f"---\n\n"
        f"# {topic_title}\n\n"
        f"## Tổng quan\n\n"
        f"Nội dung được tổng hợp từ: {source_name}\n\n"
        f"_{excerpt}..._\n"
    )
