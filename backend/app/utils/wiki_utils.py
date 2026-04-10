"""Utilities cho Wiki layer — parse frontmatter, slug extraction."""

import re

_FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(content: str) -> dict[str, str]:
    """Parse YAML frontmatter từ Markdown content."""
    m = _FM_RE.match(content)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm


def parse_sources_list(fm: dict[str, str]) -> list[str]:
    """Parse sources list từ frontmatter field 'sources: [a, b, c]'."""
    inner = fm.get("sources", "[]").strip("[]").strip()
    if not inner:
        return []
    return [s.strip() for s in inner.split(",") if s.strip()]


def parse_sources_count(fm: dict[str, str]) -> int:
    """Đếm số sources từ frontmatter field 'sources: [a, b, c]'."""
    return len(parse_sources_list(fm))


def slug_from_rel_path(rel_path: str) -> str:
    """'pages/entities/lora.md' → 'lora'"""
    return rel_path.rsplit("/", 1)[-1].replace(".md", "")
