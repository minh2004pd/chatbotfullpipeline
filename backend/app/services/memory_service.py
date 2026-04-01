"""Memory Service: quản lý long-term memory với mem0."""

import structlog

from app.repositories.mem0_repo import Mem0Repository
from app.schemas.memory import MemoryItem

logger = structlog.get_logger(__name__)


class MemoryService:
    def __init__(self, repo: Mem0Repository):
        self.repo = repo

    def search(self, query: str, user_id: str, limit: int = 10) -> list[MemoryItem]:
        results = self.repo.search_memory(query=query, user_id=user_id, limit=limit)
        return [
            MemoryItem(
                id=m.get("id", ""),
                memory=m.get("memory", ""),
                user_id=user_id,
                score=m.get("score"),
            )
            for m in results
        ]

    def get_all(self, user_id: str) -> list[MemoryItem]:
        results = self.repo.get_all_memories(user_id=user_id)
        return [
            MemoryItem(
                id=m.get("id", ""),
                memory=m.get("memory", ""),
                user_id=user_id,
            )
            for m in results
        ]

    def add_from_conversation(self, messages: list[dict], user_id: str) -> list[dict]:
        """Lưu conversation vào long-term memory (sau khi chat xong)."""
        return self.repo.add_memory(messages=messages, user_id=user_id)

    def delete(self, memory_id: str) -> None:
        self.repo.delete_memory(memory_id=memory_id)

    def delete_all(self, user_id: str) -> None:
        self.repo.delete_all_user_memories(user_id=user_id)
