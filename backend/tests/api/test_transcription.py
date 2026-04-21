"""Tests cho transcription API endpoints.

Dùng app.dependency_overrides để mock DynamoDB và SonioxService.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_meeting_repo():
    repo = MagicMock()
    repo.create_meeting.return_value = {
        "meeting_id": "meet_test001",
        "user_id": "test_user",
        "title": "Test Meeting",
        "status": "recording",
        "speakers": [],
        "utterance_count": 0,
        "created_at": "2026-04-06T00:00:00+00:00",
    }
    repo.get_meeting.return_value = {
        "meeting_id": "meet_test001",
        "user_id": "test_user",
        "title": "Test Meeting",
        "status": "completed",
        "speakers": ["speaker_0"],
        "utterance_count": 2,
        "created_at": "2026-04-06T00:00:00+00:00",
    }
    repo.list_meetings.return_value = [
        {
            "meeting_id": "meet_test001",
            "user_id": "test_user",
            "title": "Test Meeting",
            "status": "completed",
            "duration_ms": 60000,
            "speakers": ["speaker_0"],
            "languages": [],
            "utterance_count": 2,
            "created_at": "2026-04-06T00:00:00+00:00",
        }
    ]
    repo.list_utterances.return_value = [
        {
            "speaker": "speaker_0",
            "text": "Hello world",
            "created_at": "2026-04-06T00:00:00+00:00",
        },
        {
            "speaker": "speaker_1",
            "text": "Good morning",
            "created_at": "2026-04-06T00:00:01+00:00",
        },
    ]
    return repo


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(app):
    """Synchronous TestClient — reuses conftest app (get_db already mocked)."""
    return TestClient(app, raise_server_exceptions=True)


class TestStartTranscription:
    @patch("app.api.v1.transcription._soniox")
    @patch("app.api.v1.transcription._get_meeting_repo")
    def test_start_returns_meeting_id(self, mock_get_repo, mock_soniox, client):
        mock_soniox.start_session = AsyncMock(return_value="meet_test001")
        mock_get_repo.return_value = _mock_meeting_repo()

        resp = client.post(
            "/api/v1/transcription/start",
            json={"title": "My Meeting"},
            headers={"X-User-ID": "test_user"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["meeting_id"] == "meet_test001"
        assert data["status"] == "started"

    @patch("app.api.v1.transcription._soniox")
    @patch("app.api.v1.transcription._get_meeting_repo")
    def test_start_no_soniox_key_raises_400(self, mock_get_repo, mock_soniox, client):
        mock_soniox.start_session = AsyncMock(
            side_effect=ValueError("SONIOX_API_KEY chưa được cấu hình")
        )
        mock_get_repo.return_value = _mock_meeting_repo()

        resp = client.post(
            "/api/v1/transcription/start",
            json={},
            headers={"X-User-ID": "test_user"},
        )
        assert resp.status_code == 400


class TestStopTranscription:
    @patch("app.api.v1.transcription._soniox")
    @patch("app.api.v1.transcription._get_meeting_repo")
    @patch("app.api.v1.transcription._get_transcript_rag")
    def test_stop_saves_utterances(self, mock_get_rag, mock_get_repo, mock_soniox, client):
        mock_soniox.is_active.return_value = True
        mock_soniox.get_session_duration_ms.return_value = 60000
        mock_soniox.stop_session = AsyncMock(
            return_value=[
                {"seq": 0, "speaker": "speaker_0", "text": "Hello", "translated_text": None},
                {"seq": 1, "speaker": "speaker_1", "text": "Hi there", "translated_text": None},
            ]
        )
        repo = _mock_meeting_repo()
        mock_get_repo.return_value = repo

        rag = MagicMock()
        rag.ingest_utterances.return_value = 1
        mock_get_rag.return_value = rag

        resp = client.post(
            "/api/v1/transcription/stop/meet_test001",
            headers={"X-User-ID": "test_user"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["utterance_count"] == 2
        assert repo.save_utterance.call_count == 2

    @patch("app.api.v1.transcription._soniox")
    @patch("app.api.v1.transcription._get_meeting_repo")
    def test_stop_nonexistent_session_returns_empty(self, mock_get_repo, mock_soniox, client):
        """Session không còn trong bộ nhớ (backend restart) → trả về 200 với 0 utterances."""
        from unittest.mock import AsyncMock

        mock_soniox.is_active.return_value = False
        mock_soniox.get_session_duration_ms.return_value = 0
        mock_soniox.stop_session = AsyncMock(return_value=[])
        mock_get_repo.return_value = _mock_meeting_repo()

        resp = client.post(
            "/api/v1/transcription/stop/nonexistent",
            headers={"X-User-ID": "test_user"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["utterance_count"] == 0


class TestMeetingsCRUD:
    @patch("app.api.v1.transcription._get_meeting_repo")
    def test_list_meetings(self, mock_get_repo, client):
        mock_get_repo.return_value = _mock_meeting_repo()
        resp = client.get("/api/v1/meetings", headers={"X-User-ID": "test_user"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["meetings"][0]["meeting_id"] == "meet_test001"

    @patch("app.api.v1.transcription._get_meeting_repo")
    def test_get_transcript(self, mock_get_repo, client):
        mock_get_repo.return_value = _mock_meeting_repo()
        resp = client.get(
            "/api/v1/meetings/meet_test001/transcript",
            headers={"X-User-ID": "test_user"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["meeting_id"] == "meet_test001"
        assert len(data["utterances"]) == 2

    @patch("app.api.v1.transcription._get_meeting_repo")
    def test_get_transcript_not_found(self, mock_get_repo, client):
        repo = _mock_meeting_repo()
        repo.get_meeting.return_value = None
        mock_get_repo.return_value = repo
        resp = client.get(
            "/api/v1/meetings/nonexistent/transcript",
            headers={"X-User-ID": "test_user"},
        )
        assert resp.status_code == 404

    @patch("app.api.v1.transcription._get_meeting_repo")
    @patch("app.api.v1.transcription._get_transcript_rag")
    def test_delete_meeting(self, mock_get_rag, mock_get_repo, client):
        mock_get_repo.return_value = _mock_meeting_repo()
        mock_get_rag.return_value = MagicMock()
        resp = client.delete(
            "/api/v1/meetings/meet_test001",
            headers={"X-User-ID": "test_user"},
        )
        assert resp.status_code == 204


class TestMeetingRepository:
    """Unit tests cho MeetingRepository (không cần DynamoDB thật)."""

    def _make_repo(self):
        from app.repositories.meeting_repo import MeetingRepository

        table = MagicMock()
        table.get_item.return_value = {
            "Item": {
                "PK": "USER#u1",
                "SK": "MEETING#m1",
                "meeting_id": "m1",
                "user_id": "u1",
                "title": "Test",
                "status": "completed",
                "speakers": [],
                "utterance_count": 0,
                "created_at": "2026-04-06T00:00:00+00:00",
            }
        }
        table.query.return_value = {"Items": []}
        return MeetingRepository(table)

    def test_create_meeting(self):
        from app.repositories.meeting_repo import MeetingRepository

        table = MagicMock()
        repo = MeetingRepository(table)
        result = repo.create_meeting(meeting_id="m1", user_id="u1", title="Test")
        assert result["meeting_id"] == "m1"
        assert result["status"] == "recording"
        table.put_item.assert_called_once()

    def test_get_meeting(self):
        repo = self._make_repo()
        item = repo.get_meeting(meeting_id="m1", user_id="u1")
        assert item is not None
        assert item["meeting_id"] == "m1"

    def test_list_meetings_empty(self):
        repo = self._make_repo()
        items = repo.list_meetings(user_id="u1")
        assert items == []
