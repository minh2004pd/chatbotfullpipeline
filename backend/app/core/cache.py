"""Redis distributed cache layer cho MemRAG.

Key naming convention:
  memrag:wiki:{user_id}:page:{rel_path}       TTL=redis_wiki_ttl
  memrag:wiki:{user_id}:index                 TTL=redis_wiki_ttl
  memrag:wiki:{user_id}:link_index            TTL=redis_wiki_ttl
  memrag:wiki:{user_id}:schema                TTL=redis_wiki_ttl*3
  memrag:wiki:{user_id}:graph:{params_hash}   TTL=redis_graph_ttl
  memrag:auth:user:{user_id}                  TTL=redis_user_ttl
  memrag:sessions:{user_id}:list              TTL=redis_session_list_ttl
  memrag:docs:{user_id}:list                  TTL=redis_docs_list_ttl

Graceful degradation: mọi operation đều try/except — Redis down không crash app.
"""

import hashlib
import json
from functools import lru_cache

import structlog
from redis.asyncio import Redis

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


@lru_cache
def get_redis_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


class CacheService:
    def __init__(self, client: Redis, enabled: bool = True) -> None:
        self._r = client
        self._enabled = enabled

    async def get(self, key: str) -> str | None:
        if not self._enabled:
            return None
        try:
            return await self._r.get(key)
        except Exception as exc:
            logger.warning("cache_get_failed", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: str, ttl: int = 300) -> None:
        if not self._enabled:
            return
        try:
            await self._r.setex(key, ttl, value)
        except Exception as exc:
            logger.warning("cache_set_failed", key=key, error=str(exc))

    async def delete(self, *keys: str) -> None:
        if not self._enabled or not keys:
            return
        try:
            await self._r.delete(*keys)
        except Exception as exc:
            logger.warning("cache_delete_failed", keys=keys, error=str(exc))

    async def delete_pattern(self, pattern: str) -> None:
        """SCAN + DEL — production-safe (dùng SCAN thay vì KEYS *)."""
        if not self._enabled:
            return
        try:
            cursor = 0
            while True:
                cursor, keys = await self._r.scan(cursor, match=pattern, count=100)
                if keys:
                    await self._r.delete(*keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning("cache_delete_pattern_failed", pattern=pattern, error=str(exc))

    async def get_json(self, key: str) -> dict | list | None:
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set_json(self, key: str, data: dict | list, ttl: int = 300) -> None:
        await self.set(key, json.dumps(data, ensure_ascii=False), ttl=ttl)

    @staticmethod
    def stable_hash(data: dict) -> str:
        """Cross-process stable hash cho cache key params (không dùng Python hash())."""
        return hashlib.md5(
            json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:12]


@lru_cache
def get_cache_service() -> CacheService:
    settings = get_settings()
    client = get_redis_client()
    return CacheService(client=client, enabled=settings.redis_enabled)
