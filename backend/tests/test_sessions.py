"""Tests cho /api/v1/sessions endpoints."""

import pytest
from httpx import AsyncClient

# mock_dynamo_session_service đăng ký dependency_overrides cho tất cả tests
pytestmark = pytest.mark.usefixtures("mock_dynamo_session_service")


# ---------------------------------------------------------------------------
# GET /api/v1/sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_empty(client: AsyncClient, mock_dynamo_session_service):
    mock_dynamo_session_service.list_sessions_with_metadata.return_value = []

    response = await client.get("/api/v1/sessions")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_sessions_returns_data(client: AsyncClient, mock_dynamo_session_service):
    mock_dynamo_session_service.list_sessions_with_metadata.return_value = [
        {
            "session_id": "sess-abc",
            "title": "Hỏi về Python",
            "created_at": "2024-01-02T00:00:00+00:00",
            "updated_at": "2024-01-02T00:05:00+00:00",
            "message_count": 3,
        },
        {
            "session_id": "sess-xyz",
            "title": "Hỏi về FastAPI",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:10:00+00:00",
            "message_count": 5,
        },
    ]

    response = await client.get("/api/v1/sessions")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["session_id"] == "sess-abc"
    assert data[0]["title"] == "Hỏi về Python"
    assert data[0]["message_count"] == 3
    assert data[1]["session_id"] == "sess-xyz"


@pytest.mark.asyncio
async def test_list_sessions_uses_user_id_from_header(
    client: AsyncClient, mock_dynamo_session_service
):
    """Service phải được gọi với user_id từ header X-User-ID."""
    mock_dynamo_session_service.list_sessions_with_metadata.return_value = []

    await client.get("/api/v1/sessions", headers={"X-User-ID": "alice"})

    mock_dynamo_session_service.list_sessions_with_metadata.assert_called_once_with(
        app_name="memrag", user_id="alice"
    )


# ---------------------------------------------------------------------------
# GET /api/v1/sessions/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_messages_success(client: AsyncClient, mock_dynamo_session_service):
    mock_dynamo_session_service.get_session_messages.return_value = {
        "session_id": "sess-abc",
        "title": "Hỏi về Python",
        "messages": [
            {
                "role": "user",
                "content": "Python là gì?",
                "timestamp": "2024-01-02T00:00:00+00:00",
            },
            {
                "role": "model",
                "content": "Python là ngôn ngữ lập trình...",
                "timestamp": "2024-01-02T00:00:01+00:00",
            },
        ],
    }

    response = await client.get("/api/v1/sessions/sess-abc")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "sess-abc"
    assert data["title"] == "Hỏi về Python"
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Python là gì?"
    assert data["messages"][1]["role"] == "model"


@pytest.mark.asyncio
async def test_get_session_messages_not_found(client: AsyncClient, mock_dynamo_session_service):
    mock_dynamo_session_service.get_session_messages.return_value = None

    response = await client.get("/api/v1/sessions/nonexistent-id")

    assert response.status_code == 404
    assert "không tồn tại" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_session_messages_uses_user_id(
    client: AsyncClient, mock_dynamo_session_service
):
    mock_dynamo_session_service.get_session_messages.return_value = {
        "session_id": "s1",
        "title": "Test",
        "messages": [],
    }

    await client.get("/api/v1/sessions/s1", headers={"X-User-ID": "bob"})

    mock_dynamo_session_service.get_session_messages.assert_called_once_with(
        app_name="memrag", user_id="bob", session_id="s1"
    )


# ---------------------------------------------------------------------------
# DELETE /api/v1/sessions/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_session_returns_204(client: AsyncClient, mock_dynamo_session_service):
    response = await client.delete("/api/v1/sessions/sess-abc")

    assert response.status_code == 204
    assert response.content == b""  # no body


@pytest.mark.asyncio
async def test_delete_session_calls_service(client: AsyncClient, mock_dynamo_session_service):
    await client.delete("/api/v1/sessions/sess-abc", headers={"X-User-ID": "carol"})

    mock_dynamo_session_service.delete_session.assert_called_once_with(
        app_name="memrag", user_id="carol", session_id="sess-abc"
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_user_id_header_rejected(client: AsyncClient):
    """X-User-ID quá dài bị reject."""
    response = await client.get(
        "/api/v1/sessions",
        headers={"X-User-ID": "x" * 101},
    )
    assert response.status_code == 400
