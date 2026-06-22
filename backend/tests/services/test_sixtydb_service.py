"""Unit tests cho SixtyDBService — segment→utterance mapping + transcribe_file flow."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sixtydb_service import SixtyDBError, SixtyDBService


def _settings(**overrides):
    base = {
        "sixtydb_api_key": "sk_test",
        "sixtydb_base_url": "https://api.60db.ai",
        "sixtydb_stt_path": "/stt",
        "sixtydb_default_language": "",
        "sixtydb_diarize": True,
        "sixtydb_max_upload_mb": 10,
        "sixtydb_timeout_sec": 300.0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _patch_httpx(json_payload, *, status_error=None):
    """Trả về context manager patch cho httpx.AsyncClient."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_payload
    if status_error is not None:
        mock_resp.raise_for_status.side_effect = status_error
    else:
        mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)

    return patch("app.services.sixtydb_service.httpx.AsyncClient", return_value=cm), mock_client


# ── Mapping ───────────────────────────────────────────────────────────────────


class TestSegmentMapping:
    def test_segments_become_utterances(self):
        payload = {
            "language": "en",
            "duration_sec": 12.5,
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "Hello there", "confidence": 0.95},
                {"start": 2.5, "end": 5.0, "text": "Good morning", "confidence": 0.9},
            ],
        }
        utts = SixtyDBService._segments_to_utterances(payload)
        assert len(utts) == 2
        assert utts[0]["seq"] == 0
        assert utts[0]["text"] == "Hello there"
        assert utts[0]["start_ms"] == 0
        assert utts[0]["end_ms"] == 2500
        assert utts[0]["confidence"] == 0.95
        assert utts[0]["language"] == "en"
        assert utts[0]["translated_text"] is None
        assert utts[1]["seq"] == 1

    def test_diarization_speaker_normalized(self):
        payload = {
            "segments": [
                {"start": 0, "end": 1, "text": "Hi", "speakers": [{"speaker": "1"}]},
                {"start": 1, "end": 2, "text": "Hey", "speakers": ["speaker_2"]},
                {"start": 2, "end": 3, "text": "Yo"},
            ]
        }
        utts = SixtyDBService._segments_to_utterances(payload)
        assert utts[0]["speaker"] == "speaker_1"
        assert utts[1]["speaker"] == "speaker_2"
        assert utts[2]["speaker"] == "speaker_0"

    def test_empty_segments_falls_back_to_text(self):
        payload = {"language": "vi", "text": "Xin chào", "segments": []}
        utts = SixtyDBService._segments_to_utterances(payload)
        assert len(utts) == 1
        assert utts[0]["text"] == "Xin chào"
        assert utts[0]["speaker"] == "speaker_0"
        assert utts[0]["language"] == "vi"

    def test_no_text_returns_empty(self):
        assert SixtyDBService._segments_to_utterances({"segments": []}) == []
        assert SixtyDBService._segments_to_utterances({"text": "   "}) == []

    def test_blank_segments_skipped(self):
        payload = {"segments": [{"start": 0, "end": 1, "text": "  "}]}
        assert SixtyDBService._segments_to_utterances(payload) == []

    def test_sec_to_ms_handles_bad_values(self):
        assert SixtyDBService._sec_to_ms(None) is None
        assert SixtyDBService._sec_to_ms("nope") is None
        assert SixtyDBService._sec_to_ms(1.234) == 1234


# ── transcribe_file ─────────────────────────────────────────────────────────


class TestTranscribeFile:
    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self):
        svc = SixtyDBService(settings=_settings(sixtydb_api_key=""))
        with pytest.raises(SixtyDBError, match="SIXTYDB_API_KEY"):
            await svc.transcribe_file(file_bytes=b"abc", filename="a.wav")

    @pytest.mark.asyncio
    async def test_oversize_file_raises(self):
        svc = SixtyDBService(settings=_settings(sixtydb_max_upload_mb=0))
        with pytest.raises(SixtyDBError, match="vượt quá giới hạn"):
            await svc.transcribe_file(file_bytes=b"x" * 1024, filename="a.wav")

    @pytest.mark.asyncio
    async def test_happy_path_maps_response(self):
        svc = SixtyDBService(settings=_settings())
        payload = {
            "language": "en",
            "duration_sec": 3.0,
            "segments": [{"start": 0, "end": 3, "text": "Hello world", "confidence": 0.9}],
        }
        patcher, mock_client = _patch_httpx(payload)
        with patcher:
            result = await svc.transcribe_file(
                file_bytes=b"audio-bytes", filename="meeting.mp3", content_type="audio/mpeg"
            )

        assert result["language"] == "en"
        assert result["duration_ms"] == 3000
        assert len(result["utterances"]) == 1
        assert result["utterances"][0]["text"] == "Hello world"

        # Verify request shape: multipart files + bearer auth + diarize default
        _, kwargs = mock_client.post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer sk_test"
        assert "file" in kwargs["files"]
        assert kwargs["data"]["diarize"] == "true"

    @pytest.mark.asyncio
    async def test_http_error_wrapped(self):
        import httpx

        svc = SixtyDBService(settings=_settings())
        err_resp = MagicMock()
        err_resp.status_code = 401
        err_resp.text = "unauthorized"
        status_error = httpx.HTTPStatusError("bad", request=MagicMock(), response=err_resp)

        patcher, _ = _patch_httpx({}, status_error=status_error)
        with patcher, pytest.raises(SixtyDBError, match="401"):
            await svc.transcribe_file(file_bytes=b"abc", filename="a.wav")
