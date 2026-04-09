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
from datetime import datetime, timezone

import structlog

from app.core.config import Settings
from app.core.llm_config import get_llm_config
from app.repositories.wiki_repo import WikiRepository
from app.utils.gemini_utils import _with_retry, get_genai_client

logger = structlog.get_logger(__name__)

# asyncio.Lock per page path để tránh race condition khi 2 ingestions cùng update 1 trang
_page_locks: dict[str, asyncio.Lock] = {}


def _get_page_lock(user_id: str, rel_path: str) -> asyncio.Lock:
    key = f"{user_id}:{rel_path}"
    if key not in _page_locks:
        _page_locks[key] = asyncio.Lock()
    return _page_locks[key]


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
        try:
            await self._process_source(
                user_id=user_id,
                source_id=document_id,
                source_name=filename,
                raw_text=full_text,
                raw_category="documents",
                raw_filename=f"{document_id}.txt",
            )
        except Exception as e:
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
                        pages_updated += 1

            # 2. Xóa raw file (documents hoặc transcripts)
            self._repo.delete_raw(user_id=user_id, source_id=source_id)

            # 3. Luôn rebuild index và ghi log — bất kể có page nào thay đổi không
            self._rebuild_index(user_id=user_id)
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

        # 2. Extract topics
        truncated = raw_text[: self._settings.wiki_max_text_chars]
        topics = await self._extract_topics(text=truncated, source_name=source_name)
        if not topics:
            logger.warning("wiki_no_topics_extracted", source_id=source_id)
            return

        # 3. Synthesize / update pages — tách riêng entities, topics, summaries
        entities = [t for t in topics if t.get("category") == "entities"]
        topic_items = [t for t in topics if t.get("category") == "topics"]
        summary_items = [t for t in topics if t.get("category") == "summaries"]

        pages_to_process = (
            entities[: self._settings.wiki_max_entities_per_source]
            + topic_items[: self._settings.wiki_max_topics_per_source]
            + summary_items  # luôn xử lý tất cả summaries (thường chỉ 1 per source)
        )

        for topic in pages_to_process:
            slug = topic.get("slug", "")
            category = topic.get("category", "summaries")
            title = topic.get("title", slug)
            topic_type = topic.get("type", "")  # chỉ entities có type (model/method/...)
            if not slug:
                continue
            rel_path = f"pages/{category}/{slug}.md"
            async with _get_page_lock(user_id, rel_path):
                existing = self._repo.read_page(user_id=user_id, rel_path=rel_path) or ""
                new_content = await self._synthesize_page(
                    existing_content=existing,
                    new_text=truncated,
                    topic_title=title,
                    topic_type=topic_type,
                    source_name=source_name,
                    source_id=source_id,
                )
                if new_content:
                    self._repo.write_page(user_id=user_id, rel_path=rel_path, content=new_content)
                    logger.info("wiki_page_updated", user_id=user_id, path=rel_path)

        # 4. Rebuild index (rule-based)
        self._rebuild_index(user_id=user_id)

        # 5. Log
        self._repo.append_log(
            user_id=user_id,
            entry=(
                f"## [{_now_iso()}] INGEST | {raw_category} | {source_name} | "
                f"entities={len(entities)} topics={len(topic_items)} summaries={len(summary_items)}"
            ),
        )
        logger.info(
            "wiki_process_done",
            user_id=user_id,
            source=source_name,
            entities=len(entities),
            topics=len(topic_items),
            summaries=len(summary_items),
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
        existing_content: str,
        new_text: str,
        topic_title: str,
        topic_type: str = "",
        source_name: str,
        source_id: str,
    ) -> str:
        """Gọi LLM để merge existing wiki với nội dung mới."""
        config = get_llm_config()
        client = get_genai_client()
        prompt_template = config.prompts.wiki_synthesis_prompt

        if not prompt_template:
            # Fallback đơn giản không cần LLM
            return _simple_page(topic_title, topic_type, source_name, source_id, new_text)

        # Strip code fence từ existing_content (có thể còn sót từ LLM trước đó)
        clean_existing = _strip_code_fence(existing_content.strip()) if existing_content else ""

        prompt = prompt_template.format(
            topic_title=topic_title,
            topic_type=topic_type or "auto",
            source_name=source_name,
            source_id=source_id,
            existing_content=clean_existing or "(trang mới, chưa có nội dung)",
            new_text=new_text,
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
            return _simple_page(topic_title, source_name, source_id, new_text)

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
            title = (
                _parse_frontmatter_title(content)
                or filename.replace(".md", "").replace("-", " ").title()
            )
            line = f"- [[{rel_path}]] — {title}"
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


# ── Helpers ───────────────────────────────────────────────────────────────────


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


def _slugify(text: str) -> str:
    """Normalize text thành kebab-case slug, tối đa 60 ký tự."""
    # Bỏ dấu tiếng Việt
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    # Lowercase, replace non-alphanumeric bằng dấu gạch ngang
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:60]


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
