"""Unit tests cho app.core.indexing_status — Wiki status in-memory store."""

import time
from unittest.mock import patch

import pytest

from app.core import indexing_status
from app.core.indexing_status import (
    _WikiEntry,
    _cleanup,
    _store,
    get_wiki_status,
    set_wiki_status,
)


@pytest.fixture(autouse=True)
def clear_store():
    """Clear the in-memory store before/after each test."""
    indexing_status._store.clear()
    yield
    indexing_status._store.clear()


# ── set_wiki_status ───────────────────────────────────────────────────────────


class TestSetWikiStatus:
    def test_set_status_processing(self):
        set_wiki_status("user-1", "doc-1", "processing")
        assert get_wiki_status("user-1", "doc-1") == "processing"

    def test_set_status_done(self):
        set_wiki_status("user-1", "doc-1", "done")
        assert get_wiki_status("user-1", "doc-1") == "done"

    def test_set_status_error(self):
        set_wiki_status("user-1", "doc-1", "error")
        assert get_wiki_status("user-1", "doc-1") == "error"

    def test_set_status_overwrites(self):
        """Ghi đè status cũ."""
        set_wiki_status("user-1", "doc-1", "processing")
        set_wiki_status("user-1", "doc-1", "done")
        assert get_wiki_status("user-1", "doc-1") == "done"

    def test_set_status_multiple_users(self):
        """Nhiều user có document riêng."""
        set_wiki_status("user-1", "doc-1", "processing")
        set_wiki_status("user-2", "doc-1", "done")
        assert get_wiki_status("user-1", "doc-1") == "processing"
        assert get_wiki_status("user-2", "doc-1") == "done"

    def test_set_status_same_user_multiple_docs(self):
        """Cùng user, nhiều documents."""
        set_wiki_status("user-1", "doc-1", "processing")
        set_wiki_status("user-1", "doc-2", "done")
        assert get_wiki_status("user-1", "doc-1") == "processing"
        assert get_wiki_status("user-1", "doc-2") == "done"


# ── get_wiki_status ───────────────────────────────────────────────────────────


class TestGetWikiStatus:
    def test_get_nonexistent_user(self):
        assert get_wiki_status("unknown-user", "doc-1") is None

    def test_get_nonexistent_document(self):
        set_wiki_status("user-1", "doc-1", "processing")
        assert get_wiki_status("user-1", "doc-999") is None

    def test_get_after_set(self):
        set_wiki_status("user-1", "doc-1", "done")
        assert get_wiki_status("user-1", "doc-1") == "done"

    def test_get_returns_string_not_entry(self):
        """get_wiki_status trả về string, không phải _WikiEntry object."""
        set_wiki_status("user-1", "doc-1", "processing")
        status = get_wiki_status("user-1", "doc-1")
        assert isinstance(status, str)


# ── Expiry / cleanup ──────────────────────────────────────────────────────────


class TestWikiStatusExpiry:
    @patch("app.core.indexing_status.time.monotonic")
    def test_status_expires_after_10_minutes(self, mock_monotonic):
        """Status tự động expire sau 10 phút."""
        now = 1000.0
        mock_monotonic.return_value = now

        set_wiki_status("user-1", "doc-1", "processing")
        assert get_wiki_status("user-1", "doc-1") == "processing"

        # Advance time by 10 minutes + 1 second
        mock_monotonic.return_value = now + 601
        # Must call _cleanup explicitly or get_wiki_status calls it
        assert get_wiki_status("user-1", "doc-1") is None

    @patch("app.core.indexing_status.time.monotonic")
    def test_status_still_valid_before_expiry(self, mock_monotonic):
        """Status vẫn hợp lệ trước khi expire."""
        now = 1000.0
        mock_monotonic.return_value = now

        set_wiki_status("user-1", "doc-1", "processing")

        # Advance time by 5 minutes
        mock_monotonic.return_value = now + 300
        assert get_wiki_status("user-1", "doc-1") == "processing"

    @patch("app.core.indexing_status.time.monotonic")
    def test_cleanup_removes_expired_entries(self, mock_monotonic):
        """_cleanup() xóa các entry đã expire."""
        now = 1000.0
        mock_monotonic.return_value = now

        set_wiki_status("user-1", "doc-1", "processing")
        set_wiki_status("user-1", "doc-2", "done")
        set_wiki_status("user-2", "doc-1", "processing")

        # Advance time past expiry
        mock_monotonic.return_value = now + 700
        _cleanup()

        # All entries should be gone
        assert "user-1" not in indexing_status._store or not indexing_status._store.get("user-1")
        assert "user-2" not in indexing_status._store or not indexing_status._store.get("user-2")

    @patch("app.core.indexing_status.time.monotonic")
    def test_cleanup_keeps_fresh_entries(self, mock_monotonic):
        """_cleanup() giữ lại các entry chưa expire."""
        now = 1000.0
        mock_monotonic.return_value = now

        set_wiki_status("user-1", "doc-1", "processing")

        # Advance time by 5 minutes (still valid)
        mock_monotonic.return_value = now + 300
        _cleanup()

        assert get_wiki_status("user-1", "doc-1") == "processing"

    @patch("app.core.indexing_status.time.monotonic")
    def test_cleanup_removes_empty_user_entries(self, mock_monotonic):
        """_cleanup() xóa user entry khi tất cả documents đã expire."""
        now = 1000.0
        mock_monotonic.return_value = now

        set_wiki_status("user-1", "doc-1", "processing")
        set_wiki_status("user-2", "doc-1", "processing")

        # Only user-1's entry expires
        mock_monotonic.return_value = now + 700
        _cleanup()

        assert "user-1" not in indexing_status._store
        assert "user-2" in indexing_status._store

    @patch("app.core.indexing_status.time.monotonic")
    def test_get_wiki_status_triggers_cleanup(self, mock_monotonic):
        """get_wiki_status() tự động gọi _cleanup()."""
        now = 1000.0
        mock_monotonic.return_value = now

        set_wiki_status("user-1", "doc-1", "processing")

        # Advance time past expiry
        mock_monotonic.return_value = now + 700

        # get_wiki_status should trigger cleanup and return None
        assert get_wiki_status("user-1", "doc-1") is None


# ── _WikiEntry dataclass ──────────────────────────────────────────────────────


class TestWikiEntry:
    def test_wiki_entry_default_timestamp(self):
        entry = _WikiEntry(status="processing")
        assert entry.status == "processing"
        assert entry.created_at > 0

    def test_wiki_entry_custom_timestamp(self):
        entry = _WikiEntry(status="done", created_at=12345.0)
        assert entry.status == "done"
        assert entry.created_at == 12345.0
