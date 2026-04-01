"""Tests cho chat endpoints."""
import base64
import pytest
from httpx import AsyncClient

# mock_runner đăng ký dependency_overrides, áp dụng cho tất cả tests trong module
pytestmark = pytest.mark.usefixtures("mock_runner")


@pytest.mark.asyncio
async def test_chat_basic(client: AsyncClient):
    response = await client.post(
        "/api/v1/chat",
        json={"message": "Xin chào!", "user_id": "test_user"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Xin chào! Tôi có thể giúp gì cho bạn?"
    assert "session_id" in data
    assert data["user_id"] == "test_user"
    assert data["citations"] == []


@pytest.mark.asyncio
async def test_chat_empty_message_rejected(client: AsyncClient):
    response = await client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_message_too_long_rejected(client: AsyncClient):
    response = await client.post("/api/v1/chat", json={"message": "a" * 10001})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_persists_session_id(client: AsyncClient):
    response = await client.post(
        "/api/v1/chat",
        json={"message": "Hello", "session_id": "my-session-42"},
    )
    assert response.status_code == 200
    assert response.json()["session_id"] == "my-session-42"


@pytest.mark.asyncio
async def test_chat_user_id_from_header(client: AsyncClient):
    response = await client.post(
        "/api/v1/chat",
        json={"message": "Hello"},
        headers={"X-User-ID": "custom_user"},
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == "custom_user"


@pytest.mark.asyncio
async def test_chat_with_image(client: AsyncClient):
    fake_image = base64.b64encode(b"fake_image_bytes").decode()
    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "Ảnh này là gì?",
            "image_base64": fake_image,
            "image_mime_type": "image/jpeg",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_stream_returns_sse(client: AsyncClient):
    response = await client.post(
        "/api/v1/chat/stream",
        json={"message": "Hello stream!"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
