"""Unit tests cho app.repositories.mem0_repo — Memory operations."""

from unittest.mock import MagicMock

import pytest

from app.repositories.mem0_repo import Mem0Repository

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_mem0_client():
    client = MagicMock()
    client.add.return_value = {"results": []}
    client.search.return_value = {"results": []}
    client.get_all.return_value = {"results": []}
    client.delete.return_value = None
    client.delete_all.return_value = None
    return client


@pytest.fixture
def repo(mock_mem0_client):
    return Mem0Repository(client=mock_mem0_client)


USER_ID = "test-user-123"


# ── add_memory ────────────────────────────────────────────────────────────────


class TestAddMemory:
    def test_add_memory_returns_results(self, repo):
        repo.client.add.return_value = {
            "results": [
                {"id": "mem-1", "memory": "User likes Python"},
                {"id": "mem-2", "memory": "User works at Company X"},
            ]
        }
        messages = [{"role": "user", "content": "I like Python"}]
        results = repo.add_memory(messages=messages, user_id=USER_ID)
        assert len(results) == 2
        assert results[0]["id"] == "mem-1"

    def test_add_memory_empty_results(self, repo):
        repo.client.add.return_value = {"results": []}
        messages = [{"role": "user", "content": "Hello"}]
        results = repo.add_memory(messages=messages, user_id=USER_ID)
        assert results == []

    def test_add_memory_calls_client(self, repo):
        messages = [{"role": "user", "content": "Test"}]
        repo.add_memory(messages=messages, user_id=USER_ID)
        repo.client.add.assert_called_once_with(messages, user_id=USER_ID)

    def test_add_memory_handles_list_response(self, repo):
        """mem0 client có thể trả về list thay vì dict."""
        repo.client.add.return_value = [
            {"id": "mem-1", "memory": "Fact 1"},
        ]
        messages = [{"role": "user", "content": "Test"}]
        results = repo.add_memory(messages=messages, user_id=USER_ID)
        assert results == []  # List response không có "results" key

    def test_add_memory_handles_no_results_key(self, repo):
        """Response dict không có "results" key."""
        repo.client.add.return_value = {"data": []}
        messages = [{"role": "user", "content": "Test"}]
        results = repo.add_memory(messages=messages, user_id=USER_ID)
        assert results == []


# ── search_memory ─────────────────────────────────────────────────────────────


class TestSearchMemory:
    def test_search_memory_returns_results(self, repo):
        repo.client.search.return_value = {
            "results": [
                {"id": "mem-1", "memory": "Python fact", "score": 0.9},
            ]
        }
        results = repo.search_memory(query="Python", user_id=USER_ID)
        assert len(results) == 1
        assert results[0]["id"] == "mem-1"

    def test_search_memory_empty_results(self, repo):
        repo.client.search.return_value = {"results": []}
        results = repo.search_memory(query="nonexistent", user_id=USER_ID)
        assert results == []

    def test_search_memory_calls_client(self, repo):
        repo.search_memory(query="Python", user_id=USER_ID, limit=5)
        repo.client.search.assert_called_once_with("Python", user_id=USER_ID, limit=5)

    def test_search_memory_default_limit(self, repo):
        repo.search_memory(query="Python", user_id=USER_ID)
        call_args = repo.client.search.call_args
        assert call_args.kwargs["limit"] == 10

    def test_search_memory_handles_list_response(self, repo):
        """mem0 client có thể trả về list."""
        repo.client.search.return_value = [
            {"id": "mem-1", "memory": "Fact"},
        ]
        results = repo.search_memory(query="test", user_id=USER_ID)
        assert len(results) == 1
        assert results[0]["id"] == "mem-1"


# ── get_all_memories ──────────────────────────────────────────────────────────


class TestGetAllMemories:
    def test_get_all_memories_returns_results(self, repo):
        repo.client.get_all.return_value = {
            "results": [
                {"id": "mem-1", "memory": "Fact 1"},
                {"id": "mem-2", "memory": "Fact 2"},
            ]
        }
        results = repo.get_all_memories(user_id=USER_ID)
        assert len(results) == 2

    def test_get_all_memories_empty(self, repo):
        repo.client.get_all.return_value = {"results": []}
        results = repo.get_all_memories(user_id=USER_ID)
        assert results == []

    def test_get_all_memories_calls_client(self, repo):
        repo.get_all_memories(user_id=USER_ID)
        repo.client.get_all.assert_called_once_with(user_id=USER_ID)

    def test_get_all_memories_handles_list_response(self, repo):
        repo.client.get_all.return_value = [
            {"id": "mem-1", "memory": "Fact"},
        ]
        results = repo.get_all_memories(user_id=USER_ID)
        assert len(results) == 1


# ── delete_memory ─────────────────────────────────────────────────────────────


class TestDeleteMemory:
    def test_delete_memory_calls_client(self, repo):
        repo.delete_memory(memory_id="mem-123")
        repo.client.delete.assert_called_once_with("mem-123")

    def test_delete_memory_returns_none(self, repo):
        result = repo.delete_memory(memory_id="mem-123")
        assert result is None


# ── delete_all_user_memories ──────────────────────────────────────────────────


class TestDeleteAllUserMemories:
    def test_delete_all_calls_client(self, repo):
        repo.delete_all_user_memories(user_id=USER_ID)
        repo.client.delete_all.assert_called_once_with(user_id=USER_ID)

    def test_delete_all_returns_none(self, repo):
        result = repo.delete_all_user_memories(user_id=USER_ID)
        assert result is None
