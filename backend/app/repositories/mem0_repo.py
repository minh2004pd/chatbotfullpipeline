import structlog
from mem0 import Memory

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class Mem0Repository:
    def __init__(self, client: Memory):
        self.client = client
        self.settings = get_settings()

    def add_memory(self, messages: list[dict], user_id: str) -> list[dict]:
        """Store conversation messages as memories."""
        result = self.client.add(messages, user_id=user_id)
        memories = result.get("results", []) if isinstance(result, dict) else []
        logger.info("memory_added", user_id=user_id, count=len(memories))
        return memories

    def search_memory(self, query: str, user_id: str, limit: int = 10) -> list[dict]:
        """Search relevant memories for a user."""
        results = self.client.search(query, user_id=user_id, limit=limit)
        memories = results.get("results", []) if isinstance(results, dict) else results
        logger.info("memory_searched", user_id=user_id, query=query, count=len(memories))
        return memories

    def get_all_memories(self, user_id: str) -> list[dict]:
        """Get all memories for a user."""
        results = self.client.get_all(user_id=user_id)
        return results.get("results", []) if isinstance(results, dict) else results

    def delete_memory(self, memory_id: str) -> None:
        self.client.delete(memory_id)
        logger.info("memory_deleted", memory_id=memory_id)

    def delete_all_user_memories(self, user_id: str) -> None:
        self.client.delete_all(user_id=user_id)
        logger.info("all_memories_deleted", user_id=user_id)
