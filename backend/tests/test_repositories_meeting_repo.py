"""Unit tests cho app.repositories.meeting_repo — Missing tests cho meeting repository."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.repositories.meeting_repo import (
    MeetingRepository,
    _from_decimal,
    _to_decimal,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_table():
    table = MagicMock()
    table.put_item.return_value = None
    table.get_item.return_value = {"Item": None}
    table.update_item.return_value = None
    table.query.return_value = {"Items": []}
    table.delete_item.return_value = None
    return table


@pytest.fixture
def repo(mock_table):
    return MeetingRepository(table=mock_table)


USER_ID = "test-user-123"
MEETING_ID = "meeting-abc-123"


# ── create_meeting ────────────────────────────────────────────────────────────


class TestCreateMeeting:
    def test_create_meeting_returns_item(self, repo):
        item = repo.create_meeting(
            meeting_id=MEETING_ID,
            user_id=USER_ID,
            title="Test Meeting",
        )
        assert item["meeting_id"] == MEETING_ID
        assert item["user_id"] == USER_ID
        assert item["title"] == "Test Meeting"
        assert item["status"] == "recording"
        assert item["utterance_count"] == 0

    def test_create_meeting_calls_put_item(self, repo):
        repo.create_meeting(meeting_id=MEETING_ID, user_id=USER_ID, title="Test")
        repo._table.put_item.assert_called_once()

    def test_create_meeting_correct_key(self, repo):
        repo.create_meeting(meeting_id=MEETING_ID, user_id=USER_ID, title="Test")
        call_kwargs = repo._table.put_item.call_args.kwargs
        item = call_kwargs["Item"]
        assert item["PK"] == f"USER#{USER_ID}"
        assert item["SK"] == f"MEETING#{MEETING_ID}"


# ── get_meeting ───────────────────────────────────────────────────────────────


class TestGetMeeting:
    def test_get_meeting_not_found(self, repo):
        repo._table.get_item.return_value = {}
        result = repo.get_meeting(meeting_id=MEETING_ID, user_id=USER_ID)
        assert result is None

    def test_get_meeting_found(self, repo):
        mock_item = {
            "PK": f"USER#{USER_ID}",
            "SK": f"MEETING#{MEETING_ID}",
            "meeting_id": MEETING_ID,
            "title": "Test Meeting",
        }
        repo._table.get_item.return_value = {"Item": mock_item}
        result = repo.get_meeting(meeting_id=MEETING_ID, user_id=USER_ID)
        assert result is not None
        assert result["meeting_id"] == MEETING_ID

    def test_get_meeting_correct_key(self, repo):
        repo.get_meeting(meeting_id=MEETING_ID, user_id=USER_ID)
        call_kwargs = repo._table.get_item.call_args.kwargs
        assert call_kwargs["Key"]["PK"] == f"USER#{USER_ID}"
        assert call_kwargs["Key"]["SK"] == f"MEETING#{MEETING_ID}"


# ── update_meeting_status ─────────────────────────────────────────────────────


class TestUpdateMeetingStatus:
    def test_update_status_basic(self, repo):
        repo.update_meeting_status(
            meeting_id=MEETING_ID,
            user_id=USER_ID,
            status="completed",
        )
        repo._table.update_item.assert_called_once()

    def test_update_status_with_all_fields(self, repo):
        repo.update_meeting_status(
            meeting_id=MEETING_ID,
            user_id=USER_ID,
            status="completed",
            duration_ms=5000,
            speakers=["Alice", "Bob"],
            languages=["en", "vi"],
            utterance_count=10,
        )
        call_kwargs = repo._table.update_item.call_args.kwargs
        expr_values = call_kwargs["ExpressionAttributeValues"]
        assert expr_values[":st"] == "completed"
        assert expr_values[":dm"] == 5000
        assert expr_values[":sp"] == ["Alice", "Bob"]
        assert expr_values[":lg"] == ["en", "vi"]
        assert expr_values[":uc"] == 10

    def test_update_status_only_required_fields(self, repo):
        repo.update_meeting_status(
            meeting_id=MEETING_ID,
            user_id=USER_ID,
            status="error",
        )
        call_kwargs = repo._table.update_item.call_args.kwargs
        set_expr = call_kwargs["UpdateExpression"]
        assert "duration_ms" not in set_expr
        assert "speakers" not in set_expr


# ── list_meetings ─────────────────────────────────────────────────────────────


class TestListMeetings:
    def test_list_meetings_empty(self, repo):
        repo._table.query.return_value = {"Items": []}
        meetings = repo.list_meetings(user_id=USER_ID)
        assert meetings == []

    def test_list_meetings_converts_decimal(self, repo):
        mock_item = {
            "PK": f"USER#{USER_ID}",
            "SK": "MEETING#meeting-1",
            "meeting_id": "meeting-1",
            "duration_ms": Decimal("5000"),
            "utterance_count": Decimal("10"),
        }
        repo._table.query.return_value = {"Items": [mock_item]}
        meetings = repo.list_meetings(user_id=USER_ID)
        assert meetings[0]["duration_ms"] == 5000
        assert meetings[0]["utterance_count"] == 10
        assert isinstance(meetings[0]["duration_ms"], int)

    def test_list_meetings_correct_query(self, repo):
        repo.list_meetings(user_id=USER_ID)
        call_kwargs = repo._table.query.call_args.kwargs
        assert call_kwargs["ExpressionAttributeValues"][":pk"] == f"USER#{USER_ID}"
        assert call_kwargs["ExpressionAttributeValues"][":sk_prefix"] == "MEETING#"


# ── delete_meeting ────────────────────────────────────────────────────────────


class TestDeleteMeeting:
    def test_delete_meeting_calls_table(self, repo):
        repo.delete_meeting(meeting_id=MEETING_ID, user_id=USER_ID)
        repo._table.delete_item.assert_called_once()

    def test_delete_meeting_correct_key(self, repo):
        repo.delete_meeting(meeting_id=MEETING_ID, user_id=USER_ID)
        call_kwargs = repo._table.delete_item.call_args.kwargs
        assert call_kwargs["Key"]["PK"] == f"USER#{USER_ID}"
        assert call_kwargs["Key"]["SK"] == f"MEETING#{MEETING_ID}"


# ── save_utterance ────────────────────────────────────────────────────────────


class TestSaveUtterance:
    def test_save_utterance_basic(self, repo):
        item = repo.save_utterance(
            meeting_id=MEETING_ID,
            user_id=USER_ID,
            seq=1,
            speaker="Alice",
            text="Hello world",
        )
        assert item["meeting_id"] == MEETING_ID
        assert item["speaker"] == "Alice"
        assert item["text"] == "Hello world"
        assert item["PK"] == f"MEETING#{MEETING_ID}"

    def test_save_utterance_with_optional_fields(self, repo):
        item = repo.save_utterance(
            meeting_id=MEETING_ID,
            user_id=USER_ID,
            seq=1,
            speaker="Alice",
            text="Hello",
            translated_text="Xin chào",
            language="en",
            confidence=0.95,
            start_ms=1000,
            end_ms=5000,
        )
        assert item["translated_text"] == "Xin chào"
        assert item["language"] == "en"
        assert item["confidence"] == Decimal("0.95")
        assert item["start_ms"] == 1000
        assert item["end_ms"] == 5000

    def test_save_utterance_without_optional_fields(self, repo):
        item = repo.save_utterance(
            meeting_id=MEETING_ID,
            user_id=USER_ID,
            seq=1,
            speaker="Alice",
            text="Hello",
        )
        assert "translated_text" not in item
        assert "language" not in item
        assert "confidence" not in item
        assert "start_ms" not in item
        assert "end_ms" not in item

    def test_save_utterance_calls_put_item(self, repo):
        repo.save_utterance(
            meeting_id=MEETING_ID,
            user_id=USER_ID,
            seq=1,
            speaker="Alice",
            text="Hello",
        )
        repo._table.put_item.assert_called_once()


# ── list_utterances ───────────────────────────────────────────────────────────


class TestListUtterances:
    def test_list_utterances_empty(self, repo):
        repo._table.query.return_value = {"Items": []}
        utterances = repo.list_utterances(meeting_id=MEETING_ID)
        assert utterances == []

    def test_list_utterances_converts_decimal(self, repo):
        mock_item = {
            "PK": f"MEETING#{MEETING_ID}",
            "SK": "UTTERANCE#0000000000001000#0001",
            "speaker": "Alice",
            "text": "Hello",
            "confidence": Decimal("0.95"),
            "start_ms": 1000,
            "end_ms": 5000,
        }
        repo._table.query.return_value = {"Items": [mock_item]}
        utterances = repo.list_utterances(meeting_id=MEETING_ID)
        assert utterances[0]["confidence"] == 0.95
        assert isinstance(utterances[0]["confidence"], float)
        assert utterances[0]["start_ms"] == 1000
        assert utterances[0]["end_ms"] == 5000

    def test_list_utterances_correct_query(self, repo):
        repo.list_utterances(meeting_id=MEETING_ID)
        call_kwargs = repo._table.query.call_args.kwargs
        assert call_kwargs["ExpressionAttributeValues"][":pk"] == f"MEETING#{MEETING_ID}"
        assert call_kwargs["ExpressionAttributeValues"][":sk_prefix"] == "UTTERANCE#"

    def test_list_utterances_handles_null_confidence(self, repo):
        mock_item = {
            "PK": f"MEETING#{MEETING_ID}",
            "SK": "UTTERANCE#0000000000001000#0001",
            "speaker": "Alice",
            "text": "Hello",
        }
        repo._table.query.return_value = {"Items": [mock_item]}
        utterances = repo.list_utterances(meeting_id=MEETING_ID)
        assert "confidence" not in utterances[0]


# ── Decimal helpers ───────────────────────────────────────────────────────────


class TestDecimalHelpers:
    def test_to_decimal_float(self):
        assert _to_decimal(0.95) == Decimal("0.95")

    def test_to_decimal_int(self):
        assert _to_decimal(100) == Decimal("100")

    def test_to_decimal_none(self):
        assert _to_decimal(None) is None

    def test_from_decimal(self):
        assert _from_decimal(Decimal("0.95")) == 0.95

    def test_from_decimal_none(self):
        assert _from_decimal(None) is None

    def test_from_decimal_int(self):
        assert _from_decimal(Decimal("100")) == 100.0
