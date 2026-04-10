"""Wiki REST API — expose wiki graph và page content cho frontend."""

from fastapi import APIRouter, HTTPException, Query

from app.core.dependencies import UserIDDep, WikiRepoDep
from app.schemas.wiki import WikiGraphEdge, WikiGraphNode, WikiGraphResponse, WikiPageResponse
from app.utils.wiki_utils import parse_frontmatter, parse_sources_count, parse_sources_list, slug_from_rel_path

router = APIRouter(prefix="/wiki", tags=["wiki"])


@router.get("/graph", response_model=WikiGraphResponse)
def get_wiki_graph(
    user_id: UserIDDep,
    wiki_repo: WikiRepoDep,
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
    all_pages = wiki_repo.list_all_pages(user_id=user_id)
    link_index = wiki_repo.read_link_index(user_id=user_id)
    filter_sources = set(source_ids)

    # Đếm backlinks: target rel_path → count (dùng rel_path để chính xác hơn slug)
    backlink_counts: dict[str, int] = {}
    for targets in link_index.values():
        for target_rel in targets:
            backlink_counts[target_rel] = backlink_counts.get(target_rel, 0) + 1

    nodes: list[WikiGraphNode] = []
    valid_keys: set[str] = set()  # key = "{category}/{slug}"

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
            node_type = category.rstrip("s")  # "topics"→"topic", "summaries"→"summary"

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

    # Edges — link_index dùng rel_path, map sang node key
    # rel_path "pages/entities/lora.md" → key "entities/lora"
    def rel_to_key(rel_path: str) -> str:
        # "pages/entities/lora.md" → "entities/lora"
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
            edges.append(WikiGraphEdge(
                id=f"{src_key}__{tgt_key}".replace("/", "_"),
                source=src_key,
                target=tgt_key,
            ))

    return WikiGraphResponse(nodes=nodes, edges=edges)


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
