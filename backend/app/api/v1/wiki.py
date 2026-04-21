"""Wiki REST API — expose wiki graph và page content cho frontend."""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.core.cache import CacheService
from app.core.dependencies import CacheDep, SettingsDep, UserIDDep, WikiRepoDep
from app.repositories.wiki_repo import WikiRepository
from app.schemas.wiki import WikiGraphEdge, WikiGraphNode, WikiGraphResponse, WikiPageResponse
from app.utils.wiki_utils import (
    parse_frontmatter,
    parse_sources_count,
    parse_sources_list,
    slug_from_rel_path,
)

router = APIRouter(prefix="/wiki", tags=["wiki"])


def _build_graph(
    wiki_repo: WikiRepository,
    user_id: str,
    show_stubs: bool,
    show_summaries: bool,
    filter_sources: set[str],
) -> WikiGraphResponse:
    """Sync computation — chạy trong thread pool để không block event loop."""
    all_pages = wiki_repo.list_all_pages(user_id=user_id)
    link_index = wiki_repo.read_link_index(user_id=user_id)

    backlink_counts: dict[str, int] = {}
    for targets in link_index.values():
        for target_rel in targets:
            backlink_counts[target_rel] = backlink_counts.get(target_rel, 0) + 1

    nodes: list[WikiGraphNode] = []
    valid_keys: set[str] = set()

    for page_info in all_pages:
        rel_path = page_info["rel_path"]
        category = page_info["category"]
        slug = slug_from_rel_path(rel_path)
        node_key = f"{category}/{slug}"

        if not show_summaries and category == "summaries":
            continue

        content = wiki_repo.read_page(user_id=user_id, rel_path=rel_path) or ""
        fm = parse_frontmatter(content)

        try:
            version = int(fm.get("version", "1"))
        except ValueError:
            version = 1
        is_stub = version == 0 or fm.get("stub", "").lower() == "true"

        if not show_stubs and is_stub:
            continue

        if filter_sources:
            page_sources = set(parse_sources_list(fm))
            if not page_sources.intersection(filter_sources):
                continue

        if category == "entities":
            node_type = fm.get("type", "") or "entity"
        else:
            node_type = category.rstrip("s")

        nodes.append(
            WikiGraphNode(
                key=node_key,
                id=slug,
                title=fm.get("title", slug),
                type=node_type,
                category=category,
                source_count=parse_sources_count(fm),
                backlink_count=backlink_counts.get(rel_path, 0),
                is_stub=is_stub,
            )
        )
        valid_keys.add(node_key)

    def rel_to_key(rel_path: str) -> str:
        parts = rel_path.split("/")
        if len(parts) >= 3:
            return f"{parts[1]}/{parts[2].replace('.md', '')}"
        return slug_from_rel_path(rel_path)

    seen: set[tuple[str, str]] = set()
    edges: list[WikiGraphEdge] = []

    for src_rel, targets in link_index.items():
        src_key = rel_to_key(src_rel)
        if src_key not in valid_keys:
            continue
        for target_rel in targets:
            tgt_key = rel_to_key(target_rel)
            if tgt_key not in valid_keys or src_key == tgt_key or (src_key, tgt_key) in seen:
                continue
            seen.add((src_key, tgt_key))
            edges.append(
                WikiGraphEdge(
                    id=f"{src_key}__{tgt_key}".replace("/", "_"),
                    source=src_key,
                    target=tgt_key,
                )
            )

    return WikiGraphResponse(nodes=nodes, edges=edges)


@router.get("/graph", response_model=WikiGraphResponse)
async def get_wiki_graph(
    user_id: UserIDDep,
    wiki_repo: WikiRepoDep,
    cache: CacheDep,
    settings: SettingsDep,
    show_stubs: bool = False,
    show_summaries: bool = False,
    source_ids: list[str] = Query(default=[]),
) -> WikiGraphResponse:
    """Trả về nodes + edges cho React Flow graph.

    Params:
    - show_stubs: hiện stub pages (version=0)
    - show_summaries: hiện summary pages (1 per source)
    - source_ids: lọc chỉ pages có ít nhất 1 source khớp ([] = tất cả)
    """
    params_hash = CacheService.stable_hash(
        {"stubs": show_stubs, "summaries": show_summaries, "sources": sorted(source_ids)}
    )
    cache_key = f"memrag:wiki:{user_id}:graph:{params_hash}"

    cached = await cache.get_json(cache_key)
    if cached is not None:
        return WikiGraphResponse(**cached)

    result = await asyncio.to_thread(
        _build_graph, wiki_repo, user_id, show_stubs, show_summaries, set(source_ids)
    )
    await cache.set_json(cache_key, result.model_dump(), ttl=settings.redis_graph_ttl)
    return result


@router.get("/pages/{category}/{slug}", response_model=WikiPageResponse)
def get_wiki_page(
    category: str,
    slug: str,
    user_id: UserIDDep,
    wiki_repo: WikiRepoDep,
) -> WikiPageResponse:
    """Đọc nội dung Markdown của một wiki page."""
    if category not in ("entities", "topics", "summaries"):
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")

    content = wiki_repo.read_page(user_id=user_id, rel_path=f"pages/{category}/{slug}.md")
    if content is None:
        raise HTTPException(status_code=404, detail=f"Wiki page not found: {slug}")

    return WikiPageResponse(slug=slug, category=category, content=content)
