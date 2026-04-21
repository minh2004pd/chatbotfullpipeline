"""Unit tests cho CacheService — Redis cache layer."""

import json
from unittest.mock import AsyncMock

import pytest

from app.core.cache import CacheService


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def cache(mock_redis):
    return CacheService(client=mock_redis, enabled=True)


@pytest.fixture
def disabled_cache(mock_redis):
    return CacheService(client=mock_redis, enabled=False)


class TestGetSet:
    @pytest.mark.asyncio
    async def test_get_hit(self, cache, mock_redis):
        mock_redis.get.return_value = "hello"
        result = await cache.get("key1")
        assert result == "hello"
        mock_redis.get.assert_awaited_once_with("key1")

    @pytest.mark.asyncio
    async def test_get_miss(self, cache, mock_redis):
        mock_redis.get.return_value = None
        assert await cache.get("missing") is None

    @pytest.mark.asyncio
    async def test_get_redis_down_returns_none(self, cache, mock_redis):
        mock_redis.get.side_effect = ConnectionError("refused")
        assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_get_disabled_returns_none(self, disabled_cache, mock_redis):
        assert await disabled_cache.get("key1") is None
        mock_redis.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, cache, mock_redis):
        await cache.set("key1", "val", ttl=600)
        mock_redis.setex.assert_awaited_once_with("key1", 600, "val")

    @pytest.mark.asyncio
    async def test_set_redis_down_no_crash(self, cache, mock_redis):
        mock_redis.setex.side_effect = ConnectionError("refused")
        await cache.set("key1", "val")

    @pytest.mark.asyncio
    async def test_set_disabled_noop(self, disabled_cache, mock_redis):
        await disabled_cache.set("key1", "val")
        mock_redis.setex.assert_not_awaited()


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_single_key(self, cache, mock_redis):
        await cache.delete("key1")
        mock_redis.delete.assert_awaited_once_with("key1")

    @pytest.mark.asyncio
    async def test_delete_multiple_keys(self, cache, mock_redis):
        await cache.delete("k1", "k2", "k3")
        mock_redis.delete.assert_awaited_once_with("k1", "k2", "k3")

    @pytest.mark.asyncio
    async def test_delete_empty_noop(self, cache, mock_redis):
        await cache.delete()
        mock_redis.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_redis_down_no_crash(self, cache, mock_redis):
        mock_redis.delete.side_effect = ConnectionError("refused")
        await cache.delete("key1")

    @pytest.mark.asyncio
    async def test_delete_disabled_noop(self, disabled_cache, mock_redis):
        await disabled_cache.delete("key1")
        mock_redis.delete.assert_not_awaited()


class TestDeletePattern:
    @pytest.mark.asyncio
    async def test_delete_pattern_scans_and_deletes(self, cache, mock_redis):
        mock_redis.scan.side_effect = [
            (1, ["key1", "key2"]),
            (0, ["key3"]),
        ]
        await cache.delete_pattern("prefix:*")
        assert mock_redis.scan.call_count == 2
        assert mock_redis.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_pattern_no_matches(self, cache, mock_redis):
        mock_redis.scan.return_value = (0, [])
        await cache.delete_pattern("none:*")
        mock_redis.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_pattern_redis_down_no_crash(self, cache, mock_redis):
        mock_redis.scan.side_effect = ConnectionError("refused")
        await cache.delete_pattern("prefix:*")


class TestGetSetJson:
    @pytest.mark.asyncio
    async def test_get_json_hit(self, cache, mock_redis):
        mock_redis.get.return_value = json.dumps({"a": 1})
        result = await cache.get_json("key1")
        assert result == {"a": 1}

    @pytest.mark.asyncio
    async def test_get_json_miss(self, cache, mock_redis):
        mock_redis.get.return_value = None
        assert await cache.get_json("key1") is None

    @pytest.mark.asyncio
    async def test_get_json_invalid_json_returns_none(self, cache, mock_redis):
        mock_redis.get.return_value = "not json{"
        assert await cache.get_json("key1") is None

    @pytest.mark.asyncio
    async def test_get_json_list(self, cache, mock_redis):
        mock_redis.get.return_value = json.dumps([1, 2, 3])
        result = await cache.get_json("key1")
        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_set_json(self, cache, mock_redis):
        await cache.set_json("key1", {"b": 2}, ttl=120)
        mock_redis.setex.assert_awaited_once()
        args = mock_redis.setex.call_args
        assert args[0][0] == "key1"
        assert args[0][1] == 120
        assert json.loads(args[0][2]) == {"b": 2}

    @pytest.mark.asyncio
    async def test_set_json_preserves_unicode(self, cache, mock_redis):
        await cache.set_json("key1", {"text": "Xin chào"})
        stored = mock_redis.setex.call_args[0][2]
        assert "chào" in stored


class TestStableHash:
    def test_deterministic(self):
        data = {"stubs": False, "sources": ["a", "b"]}
        h1 = CacheService.stable_hash(data)
        h2 = CacheService.stable_hash(data)
        assert h1 == h2

    def test_key_order_irrelevant(self):
        h1 = CacheService.stable_hash({"a": 1, "b": 2})
        h2 = CacheService.stable_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_data_different_hash(self):
        h1 = CacheService.stable_hash({"a": 1})
        h2 = CacheService.stable_hash({"a": 2})
        assert h1 != h2

    def test_length_12(self):
        h = CacheService.stable_hash({"x": "y"})
        assert len(h) == 12

    def test_cross_process_stable(self):
        import hashlib

        data = {"stubs": False, "summaries": True, "sources": ["a", "b"]}
        expected = hashlib.md5(
            json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:12]
        assert CacheService.stable_hash(data) == expected
