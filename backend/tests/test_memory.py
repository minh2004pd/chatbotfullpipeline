"""Tests cho memory endpoints."""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.usefixtures("mock_mem0_client")


@pytest.mark.asyncio
async def test_search_memory_empty(client: AsyncClient):
    response = await client.post(
        "/api/v1/memory/search",
        json={"query": "sở thích âm nhạc", "user_id": "test_user"},
    )
    assert response.status_code == 200
    assert response.json() == {"memories": [], "total": 0}


@pytest.mark.asyncio
async def test_search_memory_with_results(client: AsyncClient, mock_mem0_client):
    mock_mem0_client.search.return_value = {
        "results": [
            {"id": "mem-1", "memory": "User thích nghe nhạc jazz", "score": 0.95},
            {"id": "mem-2", "memory": "User sống ở Hà Nội", "score": 0.82},
        ]
    }
    response = await client.post(
        "/api/v1/memory/search",
        json={"query": "âm nhạc", "user_id": "test_user", "limit": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["memories"][0]["id"] == "mem-1"
    assert data["memories"][0]["memory"] == "User thích nghe nhạc jazz"


@pytest.mark.asyncio
async def test_get_user_memories(client: AsyncClient, mock_mem0_client):
    mock_mem0_client.get_all.return_value = {
        "results": [
            {"id": "mem-1", "memory": "Tên là Minh"},
            {"id": "mem-2", "memory": "Thích lập trình Python"},
        ]
    }
    response = await client.get("/api/v1/memory/user/test_user")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "test_user"
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_delete_memory(client: AsyncClient, mock_mem0_client):
    response = await client.delete("/api/v1/memory/mem-123")
    assert response.status_code == 200
    assert response.json()["memory_id"] == "mem-123"
    mock_mem0_client.delete.assert_called_once_with("mem-123")


@pytest.mark.asyncio
async def test_delete_all_memories(client: AsyncClient, mock_mem0_client):
    response = await client.delete("/api/v1/memory/user/test_user/all")
    assert response.status_code == 204
    mock_mem0_client.delete_all.assert_called_once_with(user_id="test_user")


@pytest.mark.asyncio
async def test_search_memory_empty_query_rejected(client: AsyncClient):
    response = await client.post(
        "/api/v1/memory/search",
        json={"query": "", "user_id": "test_user"},
    )
    assert response.status_code == 422
