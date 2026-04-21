"""Integration tests cho Redis cache ở API layer.

Verifies: cache miss → write, cache hit → return, mutation → invalidate.
Uses app.dependency_overrides to mock CacheService via get_cache_service_dep.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.cache import CacheService
from app.core.dependencies import get_cache_service_dep


def _make_cache_service():
    mock = AsyncMock(spec=CacheService)
    mock.get.return_value = None
    mock.get_json.return_value = None
    mock.stable_hash = CacheService.stable_hash
    return mock


# ── Sessions cache ──────────────────────────────────────────────────────────


class TestSessionListCache:
    @pytest.mark.asyncio
    async def test_cache_miss_populates(self, app, mock_dynamo_session_service):
        cache = _make_cache_service()
        app.dependency_overrides[get_cache_service_dep] = lambda: cache

        mock_dynamo_session_service.list_sessions_with_metadata.return_value = [
            {
                "session_id": "s1",
                "title": "Test",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "message_count": 1,
            }
        ]

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-ID": "u1", "X-Requested-With": "XMLHttpRequest"},
        ) as c:
            resp = await c.get("/api/v1/sessions")
        assert resp.status_code == 200
        cache.get_json.assert_awaited_once()
        cache.set_json.assert_awaited_once()
        set_args = cache.set_json.call_args
        assert "memrag:sessions:u1:list" in str(set_args)

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self, app, mock_dynamo_session_service):
        cache = _make_cache_service()
        cache.get_json.return_value = [
            {
                "session_id": "s1",
                "title": "Cached",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "message_count": 1,
            }
        ]
        app.dependency_overrides[get_cache_service_dep] = lambda: cache

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-ID": "u1", "X-Requested-With": "XMLHttpRequest"},
        ) as c:
            resp = await c.get("/api/v1/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["title"] == "Cached"
        mock_dynamo_session_service.list_sessions_with_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_invalidates_cache(self, app, mock_dynamo_session_service):
        cache = _make_cache_service()
        app.dependency_overrides[get_cache_service_dep] = lambda: cache

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-ID": "u1", "X-Requested-With": "XMLHttpRequest"},
        ) as c:
            resp = await c.delete("/api/v1/sessions/s1")
        assert resp.status_code == 204
        cache.delete.assert_awaited_once_with("memrag:sessions:u1:list")


# ── Documents cache ─────────────────────────────────────────────────────────


class TestDocumentListCache:
    @pytest.mark.asyncio
    async def test_cache_miss_populates(self, app, mock_qdrant_client):
        cache = _make_cache_service()
        app.dependency_overrides[get_cache_service_dep] = lambda: cache

        mock_point = MagicMock()
        mock_point.payload = {
            "document_id": "d1",
            "filename": "test.pdf",
            "user_id": "u1",
        }
        mock_qdrant_client.scroll.return_value = ([mock_point], None)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-ID": "u1", "X-Requested-With": "XMLHttpRequest"},
        ) as c:
            resp = await c.get("/api/v1/documents")
        assert resp.status_code == 200
        cache.get_json.assert_awaited_once()
        cache.set_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self, app, mock_qdrant_client):
        cache = _make_cache_service()
        cache.get_json.return_value = {
            "documents": [
                {
                    "document_id": "d1",
                    "filename": "cached.pdf",
                    "user_id": "u1",
                    "chunk_count": 5,
                    "uploaded_at": "2026-01-01T00:00:00",
                }
            ],
            "total": 1,
        }
        app.dependency_overrides[get_cache_service_dep] = lambda: cache

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-ID": "u1", "X-Requested-With": "XMLHttpRequest"},
        ) as c:
            resp = await c.get("/api/v1/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["documents"][0]["filename"] == "cached.pdf"
        mock_qdrant_client.scroll.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_invalidates_cache(self, app, mock_qdrant_client):
        cache = _make_cache_service()
        app.dependency_overrides[get_cache_service_dep] = lambda: cache

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-ID": "u1", "X-Requested-With": "XMLHttpRequest"},
        ) as c:
            resp = await c.delete("/api/v1/documents/d1")
        assert resp.status_code == 200
        cache.delete.assert_awaited_once_with("memrag:docs:u1:list")


# ── Cache disabled — graceful degradation ────────────────────────────────────


class TestCacheDisabledGraceful:
    @pytest.mark.asyncio
    async def test_sessions_work_without_cache(self, app, mock_dynamo_session_service):
        mock_dynamo_session_service.list_sessions_with_metadata.return_value = []
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-ID": "u1", "X-Requested-With": "XMLHttpRequest"},
        ) as c:
            resp = await c.get("/api/v1/sessions")
        assert resp.status_code == 200
