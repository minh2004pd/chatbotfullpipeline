"""Unit tests cho app.utils.wiki_utils — Wiki parsing utilities."""

import pytest

from app.utils.wiki_utils import (
    parse_frontmatter,
    parse_sources_count,
    parse_sources_list,
    slug_from_rel_path,
)


# ── parse_frontmatter ─────────────────────────────────────────────────────────


class TestParseFrontmatter:
    def test_parse_simple_frontmatter(self):
        content = """---
title: Hello World
tags: [ai, rag]
---

# Content"""
        result = parse_frontmatter(content)
        assert result == {"title": "Hello World", "tags": "[ai, rag]"}

    def test_parse_frontmatter_with_sources(self):
        content = """---
title: Document
sources: [doc-1, doc-2, meeting-3]
version: 1
last_updated: 2026-04-15
---

# Content"""
        result = parse_frontmatter(content)
        assert result["title"] == "Document"
        assert result["sources"] == "[doc-1, doc-2, meeting-3]"
        assert result["version"] == "1"
        assert result["last_updated"] == "2026-04-15"

    def test_parse_no_frontmatter(self):
        content = "# Just content, no frontmatter"
        assert parse_frontmatter(content) == {}

    def test_parse_frontmatter_partial(self):
        """Frontmatter không đóng (thiếu --- ở cuối) → trả về empty."""
        content = """---
title: Hello
tags: [ai]

# Content"""
        assert parse_frontmatter(content) == {}

    def test_parse_frontmatter_empty(self):
        """Frontmatter rỗng."""
        content = """---
---

# Content"""
        assert parse_frontmatter(content) == {}

    def test_parse_frontmatter_multiline_value(self):
        """Value chứa dấu hai chấm."""
        content = """---
title: Title: With Colon
url: http://example.com:8080/path
---

# Content"""
        result = parse_frontmatter(content)
        # partition chia ở dấu : đầu tiên, nên value giữ nguyên phần còn lại
        assert result["title"] == "Title: With Colon"
        assert result["url"] == "http://example.com:8080/path"

    def test_parse_frontmatter_strips_whitespace(self):
        content = """---
  title:   Hello World  
  tags:   [ai, rag]  
---

# Content"""
        result = parse_frontmatter(content)
        assert result["title"] == "Hello World"
        assert result["tags"] == "[ai, rag]"

    def test_parse_frontmatter_ignores_non_kv_lines(self):
        """Lines không có dấu : bị bỏ qua."""
        content = """---
title: Hello
# This is a comment
tags: [ai]
---

# Content"""
        result = parse_frontmatter(content)
        assert "title" in result
        assert "tags" in result
        # Comment line bị bỏ qua vì không có giá trị hợp lệ
        assert "# This is a comment" not in result


# ── parse_sources_list ────────────────────────────────────────────────────────


class TestParseSourcesList:
    def test_parse_sources_list_normal(self):
        fm = {"sources": "[doc-1, doc-2, meeting-3]"}
        assert parse_sources_list(fm) == ["doc-1", "doc-2", "meeting-3"]

    def test_parse_sources_list_empty(self):
        fm = {"sources": "[]"}
        assert parse_sources_list(fm) == []

    def test_parse_sources_list_single(self):
        fm = {"sources": "[doc-1]"}
        assert parse_sources_list(fm) == ["doc-1"]

    def test_parse_sources_list_missing_key(self):
        fm = {"title": "Hello"}
        assert parse_sources_list(fm) == []

    def test_parse_sources_list_empty_value(self):
        fm = {"sources": ""}
        assert parse_sources_list(fm) == []

    def test_parse_sources_list_whitespace(self):
        fm = {"sources": " [ doc-1 , doc-2 , doc-3 ] "}
        result = parse_sources_list(fm)
        # parse_sources_list strips [] and splits by comma, keeping internal spaces
        assert len(result) == 3
        assert "doc-1" in result[0]
        assert "doc-2" in result[1]
        assert "doc-3" in result[2]

    def test_parse_sources_list_with_spaces_in_ids(self):
        fm = {"sources": "[user 123, meeting 456]"}
        assert parse_sources_list(fm) == ["user 123", "meeting 456"]

    def test_parse_sources_list_extra_whitespace_between_commas(self):
        fm = {"sources": "[doc-1,  doc-2 ,doc-3,   doc-4]"}
        assert parse_sources_list(fm) == ["doc-1", "doc-2", "doc-3", "doc-4"]


# ── parse_sources_count ───────────────────────────────────────────────────────


class TestParseSourcesCount:
    def test_parse_sources_count_normal(self):
        fm = {"sources": "[doc-1, doc-2, doc-3]"}
        assert parse_sources_count(fm) == 3

    def test_parse_sources_count_empty(self):
        fm = {"sources": "[]"}
        assert parse_sources_count(fm) == 0

    def test_parse_sources_count_single(self):
        fm = {"sources": "[doc-1]"}
        assert parse_sources_count(fm) == 1

    def test_parse_sources_count_missing_key(self):
        fm = {"title": "Hello"}
        assert parse_sources_count(fm) == 0


# ── slug_from_rel_path ────────────────────────────────────────────────────────


class TestSlugFromRelPath:
    def test_slug_from_entities_path(self):
        assert slug_from_rel_path("pages/entities/lora.md") == "lora"

    def test_slug_from_topics_path(self):
        assert slug_from_rel_path("pages/topics/efficientml.md") == "efficientml"

    def test_slug_from_summaries_path(self):
        assert slug_from_rel_path("pages/summaries/document1.md") == "document1"

    def test_slug_from_filename_only(self):
        """Path không có thư mục."""
        assert slug_from_rel_path("lora.md") == "lora"

    def test_slug_from_deep_path(self):
        """Path sâu nhiều cấp."""
        assert slug_from_rel_path("wiki/user1/pages/entities/adapter.md") == "adapter"

    def test_slug_no_extension(self):
        """Filename không có .md."""
        assert slug_from_rel_path("pages/entities/lora") == "lora"

    def test_slug_with_dashes(self):
        assert slug_from_rel_path("pages/entities/u-net.md") == "u-net"

    def test_slug_with_numbers(self):
        assert slug_from_rel_path("pages/entities/gpt4o.md") == "gpt4o"

    def test_slug_empty_path(self):
        assert slug_from_rel_path("") == ""

    def test_slug_just_extension(self):
        assert slug_from_rel_path(".md") == ""
