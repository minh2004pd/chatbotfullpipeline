"""Unit tests cho DynamoDBSessionService."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.dynamo_session_service import (
    DynamoDBSessionService,
    _decimals_to_float,
    _extract_text,
    _floats_to_decimal,
)


# ---------------------------------------------------------------------------
# Helpers fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_table():
    table = MagicMock()
    table.put_item.return_value = {}
    table.get_item.return_value = {}
    table.delete_item.return_value = {}
    table.query.return_value = {"Items": []}
    return table


@pytest.fixture
def service(mock_table):
    return DynamoDBSessionService(table=mock_table, app_name="memrag")


def _make_dynamo_item(
    session_id: str = "sess-1",
    user_id: str = "u1",
    title: str = "Test Chat",
    events: list | None = None,
    state: dict | None = None,
) -> dict:
    """Tạo DynamoDB item mẫu."""
    return {
        "pk": f"memrag#{user_id}",
        "session_id": session_id,
        "app_name": "memrag",
        "user_id": user_id,
        "title": title,
        "state": state or {"user_id": user_id, "max_context_messages": 20},
        "events": json.dumps(events or []),
        "last_update_time": Decimal("0.0"),
        "message_count": Decimal("1"),
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:01:00+00:00",
    }


def _make_raw_event(
    event_id: str = "e1",
    author: str = "user",
    text: str = "Hello?",
    timestamp: float = 1704067200.0,
) -> dict:
    """Tạo raw event dict (dạng model_dump của ADK Event)."""
    return {
        "id": event_id,
        "author": author,
        "content": {
            "role": author if author == "user" else "model",
            "parts": [{"text": text}],
        },
        "actions": {"state_delta": {}, "artifact_delta": {}},
        "timestamp": timestamp,
        "invocation_id": "inv-1",
    }


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def test_floats_to_decimal_basic():
    result = _floats_to_decimal({"score": 1.5, "name": "x"})
    assert result == {"score": Decimal("1.5"), "name": "x"}


def test_floats_to_decimal_nested():
    result = _floats_to_decimal({"a": [1.0, 2.0], "b": {"c": 3.14}})
    assert result["a"] == [Decimal("1.0"), Decimal("2.0")]
    assert result["b"]["c"] == Decimal("3.14")


def test_decimals_to_float():
    result = _decimals_to_float({"score": Decimal("1.5"), "items": [Decimal("2.0")]})
    assert result == {"score": 1.5, "items": [2.0]}


def test_extract_text_from_event():
    event = MagicMock()
    part = MagicMock()
    part.text = "  Hello world  "
    event.content = MagicMock()
    event.content.parts = [part]
    assert _extract_text(event) == "Hello world"


def test_extract_text_no_content():
    event = MagicMock()
    event.content = None
    assert _extract_text(event) is None


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


async def test_create_session_returns_session(service, mock_table):
    session = await service.create_session(
        app_name="memrag",
        user_id="u1",
        state={"user_id": "u1", "max_context_messages": 20},
    )
    assert session.app_name == "memrag"
    assert session.user_id == "u1"
    assert session.state == {"user_id": "u1", "max_context_messages": 20}
    assert session.id  # auto-generated
    assert session.events == []
    mock_table.put_item.assert_called_once()


async def test_create_session_with_explicit_id(service, mock_table):
    session = await service.create_session(
        app_name="memrag", user_id="u1", session_id="my-fixed-id"
    )
    assert session.id == "my-fixed-id"


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------


async def test_get_session_not_found_returns_none(service, mock_table):
    mock_table.get_item.return_value = {}  # không có "Item"
    result = await service.get_session(app_name="memrag", user_id="u1", session_id="s1")
    assert result is None


async def test_get_session_found_deserializes_correctly(service, mock_table):
    item = _make_dynamo_item(session_id="s1", user_id="u1", title="Hello", state={"user_id": "u1"})
    mock_table.get_item.return_value = {"Item": item}

    session = await service.get_session(app_name="memrag", user_id="u1", session_id="s1")

    assert session is not None
    assert session.id == "s1"
    assert session.user_id == "u1"
    assert session.state["user_id"] == "u1"
    assert session.events == []


async def test_get_session_with_events(service, mock_table):
    raw_events = [_make_raw_event("e1", "user", "Câu hỏi đầu tiên")]
    item = _make_dynamo_item(events=raw_events)
    mock_table.get_item.return_value = {"Item": item}

    session = await service.get_session(app_name="memrag", user_id="u1", session_id="sess-1")

    assert session is not None
    assert len(session.events) == 1
    assert session.events[0].author == "user"


async def test_get_session_applies_num_recent_events_filter(service, mock_table):
    from google.adk.sessions.base_session_service import GetSessionConfig

    raw_events = [_make_raw_event(f"e{i}", "user", f"msg {i}", float(i)) for i in range(5)]
    item = _make_dynamo_item(events=raw_events)
    mock_table.get_item.return_value = {"Item": item}

    config = GetSessionConfig(num_recent_events=2)
    session = await service.get_session(
        app_name="memrag", user_id="u1", session_id="sess-1", config=config
    )

    assert session is not None
    assert len(session.events) == 2  # chỉ giữ 2 event mới nhất


# ---------------------------------------------------------------------------
# delete_session
# ---------------------------------------------------------------------------


async def test_delete_session_calls_dynamodb(service, mock_table):
    await service.delete_session(app_name="memrag", user_id="u1", session_id="s1")
    mock_table.delete_item.assert_called_once_with(
        Key={"pk": "memrag#u1", "session_id": "s1"}
    )


# ---------------------------------------------------------------------------
# list_sessions_with_metadata
# ---------------------------------------------------------------------------


def test_list_sessions_with_metadata_empty(service, mock_table):
    mock_table.query.return_value = {"Items": []}
    result = service.list_sessions_with_metadata(app_name="memrag", user_id="u1")
    assert result == []
    mock_table.query.assert_called_once()


def test_list_sessions_sorted_newest_first(service, mock_table):
    mock_table.query.return_value = {
        "Items": [
            {
                "session_id": "s1",
                "title": "Cũ hơn",
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:01:00+00:00",
                "message_count": Decimal("1"),
            },
            {
                "session_id": "s2",
                "title": "Mới hơn",
                "created_at": "2024-01-02T00:00:00+00:00",
                "updated_at": "2024-01-02T00:01:00+00:00",
                "message_count": Decimal("3"),
            },
        ]
    }
    result = service.list_sessions_with_metadata(app_name="memrag", user_id="u1")
    assert result[0]["session_id"] == "s2"  # mới hơn → đầu tiên
    assert result[1]["session_id"] == "s1"


# ---------------------------------------------------------------------------
# get_session_messages
# ---------------------------------------------------------------------------


def test_get_session_messages_not_found(service, mock_table):
    mock_table.get_item.return_value = {}
    result = service.get_session_messages(app_name="memrag", user_id="u1", session_id="s1")
    assert result is None


def test_get_session_messages_extracts_user_and_model(service, mock_table):
    raw_events = [
        _make_raw_event("e1", "user", "Câu hỏi của tôi", 1704067200.0),
        _make_raw_event("e2", "memrag_root_agent", "Câu trả lời của AI", 1704067201.0),
    ]
    item = _make_dynamo_item(title="Câu hỏi của tôi", events=raw_events)
    mock_table.get_item.return_value = {"Item": item}

    result = service.get_session_messages(app_name="memrag", user_id="u1", session_id="sess-1")

    assert result is not None
    assert result["session_id"] == "sess-1"
    assert result["title"] == "Câu hỏi của tôi"
    assert len(result["messages"]) == 2
    assert result["messages"][0]["role"] == "user"
    assert result["messages"][0]["content"] == "Câu hỏi của tôi"
    assert result["messages"][1]["role"] == "model"
    assert result["messages"][1]["content"] == "Câu trả lời của AI"


def test_get_session_messages_skips_empty_content(service, mock_table):
    """Events không có text (tool call) bị bỏ qua."""
    raw_events = [
        _make_raw_event("e1", "user", "Hello"),
        {
            "id": "e2",
            "author": "memrag_root_agent",
            "content": {"role": "model", "parts": [{}]},  # không có text
            "actions": {"state_delta": {}, "artifact_delta": {}},
            "timestamp": 1704067201.0,
            "invocation_id": "inv-1",
        },
        _make_raw_event("e3", "memrag_root_agent", "Đây là câu trả lời thực", 1704067202.0),
    ]
    item = _make_dynamo_item(events=raw_events)
    mock_table.get_item.return_value = {"Item": item}

    result = service.get_session_messages(app_name="memrag", user_id="u1", session_id="sess-1")

    assert result is not None
    # Event e2 (no text) bị bỏ qua
    assert len(result["messages"]) == 2
    assert result["messages"][1]["content"] == "Đây là câu trả lời thực"


# ---------------------------------------------------------------------------
# append_event (smoke test — base class xử lý state management)
# ---------------------------------------------------------------------------


async def test_append_event_persists_to_dynamodb(service, mock_table):
    """append_event phải lưu session lên DynamoDB sau khi super() xử lý state."""
    from google.adk.sessions.session import Session

    session = Session(
        id="s1", app_name="memrag", user_id="u1", state={"user_id": "u1"}, events=[]
    )

    event = MagicMock()
    event.author = "user"
    event.partial = None
    event.actions = MagicMock()
    event.actions.state_delta = {}
    part = MagicMock()
    part.text = "Câu hỏi đầu tiên"
    event.content = MagicMock()
    event.content.parts = [part]

    # Lấy title hiện tại từ DynamoDB (New Chat → sẽ được cập nhật)
    mock_table.get_item.return_value = {
        "Item": _make_dynamo_item(session_id="s1", title="New Chat")
    }

    with patch(
        "google.adk.sessions.base_session_service.BaseSessionService.append_event",
        new=AsyncMock(return_value=event),
    ):
        returned_event = await service.append_event(session, event)

    assert returned_event is event
    # Phải gọi put_item để lưu session
    mock_table.put_item.assert_called_once()
    # Title phải được cập nhật từ "New Chat" → nội dung user message
    call_kwargs = mock_table.put_item.call_args[1]["Item"]
    assert call_kwargs["title"] == "Câu hỏi đầu tiên"


async def test_append_event_keeps_existing_title(service, mock_table):
    """Nếu title đã có (không phải New Chat), không ghi đè."""
    from google.adk.sessions.session import Session

    session = Session(id="s1", app_name="memrag", user_id="u1", state={}, events=[])
    event = MagicMock()
    event.author = "user"
    event.partial = None
    event.actions = MagicMock()
    event.actions.state_delta = {}
    part = MagicMock()
    part.text = "Tin nhắn thứ hai"
    event.content = MagicMock()
    event.content.parts = [part]

    mock_table.get_item.return_value = {
        "Item": _make_dynamo_item(session_id="s1", title="Tin nhắn đầu tiên")
    }

    with patch(
        "google.adk.sessions.base_session_service.BaseSessionService.append_event",
        new=AsyncMock(return_value=event),
    ):
        await service.append_event(session, event)

    call_kwargs = mock_table.put_item.call_args[1]["Item"]
    assert call_kwargs["title"] == "Tin nhắn đầu tiên"  # không đổi
