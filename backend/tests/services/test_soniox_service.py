"""Unit tests cho SonioxService — token parsing, buffer, endpoint detection, keepalive."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.soniox_service import SonioxService, _SonioxSession


def _make_session(meeting_id="meet_test", user_id="u1", **kw):
    ws = AsyncMock()
    queue = asyncio.Queue()
    return _SonioxSession(
        meeting_id=meeting_id,
        user_id=user_id,
        ws=ws,
        queue=queue,
        receiver_task=MagicMock(),
        keepalive_task=MagicMock(),
        **kw,
    )


class TestSplitTranslationTokens:
    def test_separates_original_and_translation(self):
        tokens = [
            {"text": "Hello", "translation_status": "original"},
            {"text": " ", "translation_status": "original"},
            {"text": "Xin chào", "translation_status": "translation"},
        ]
        orig, trans = SonioxService._split_translation_tokens(tokens)
        assert len(orig) == 2
        assert len(trans) == 1
        assert trans[0]["text"] == "Xin chào"

    def test_none_status_treated_as_original(self):
        tokens = [
            {"text": "Bonjour", "translation_status": "none"},
        ]
        orig, trans = SonioxService._split_translation_tokens(tokens)
        assert len(orig) == 1
        assert len(trans) == 0

    def test_empty_list(self):
        orig, trans = SonioxService._split_translation_tokens([])
        assert orig == []
        assert trans == []

    def test_missing_status_defaults_to_none(self):
        tokens = [{"text": "Hello"}]
        orig, trans = SonioxService._split_translation_tokens(tokens)
        assert len(orig) == 1
        assert len(trans) == 0


class TestFilterDisplayTokens:
    def test_filters_end_token(self):
        tokens = [
            {"text": "Hello", "is_final": True},
            {"text": "<end>", "is_final": True},
        ]
        result = SonioxService._filter_display_tokens(tokens)
        assert len(result) == 1
        assert result[0]["text"] == "Hello"

    def test_filters_non_final(self):
        tokens = [
            {"text": "Hello", "is_final": False},
            {"text": "World", "is_final": True},
        ]
        result = SonioxService._filter_display_tokens(tokens)
        assert len(result) == 1
        assert result[0]["text"] == "World"

    def test_includes_fields(self):
        tokens = [
            {
                "text": "Hello",
                "is_final": True,
                "speaker": "A",
                "language": "en",
                "translation_status": "original",
            },
        ]
        result = SonioxService._filter_display_tokens(tokens)
        assert result[0]["speaker"] == "A"
        assert result[0]["language"] == "en"
        assert result[0]["translation_status"] == "original"

    def test_empty_for_all_end_tokens(self):
        tokens = [{"text": "<end>", "is_final": True}]
        assert SonioxService._filter_display_tokens(tokens) == []

    def test_empty_for_non_final_only(self):
        tokens = [{"text": "Hello", "is_final": False}]
        assert SonioxService._filter_display_tokens(tokens) == []

    def test_defaults_translation_status(self):
        tokens = [{"text": "Hi", "is_final": True}]
        result = SonioxService._filter_display_tokens(tokens)
        assert result[0]["translation_status"] == "none"


class TestFlushBuffer:
    def test_flush_creates_utterance(self):
        session = _make_session()
        session.buffer_final_tokens = [
            {"text": "Hello", "speaker": "A", "language": "en", "translation_status": "original"},
            {"text": " Xin chào", "translation_status": "translation"},
        ]
        svc = SonioxService()
        svc._flush_buffer(session)

        assert len(session.utterances) == 1
        utt = session.utterances[0]
        assert utt["text"] == "Hello"
        assert utt["translated_text"] == "Xin chào"
        assert utt["speaker"] == "speaker_A"
        assert utt["language"] == "en"
        assert utt["seq"] == 0
        assert session.seq == 1
        assert session.buffer_final_tokens == []

    def test_flush_empty_buffer_noop(self):
        session = _make_session()
        svc = SonioxService()
        svc._flush_buffer(session)
        assert len(session.utterances) == 0

    def test_flush_empty_text_noop(self):
        session = _make_session()
        session.buffer_final_tokens = [
            {"text": " ", "speaker": "A", "translation_status": "original"},
        ]
        svc = SonioxService()
        svc._flush_buffer(session)
        assert len(session.utterances) == 0
        assert session.buffer_final_tokens == []

    def test_flush_no_speaker_defaults_to_speaker_0(self):
        session = _make_session()
        session.buffer_final_tokens = [
            {"text": "Hello", "translation_status": "none"},
        ]
        svc = SonioxService()
        svc._flush_buffer(session)
        assert session.utterances[0]["speaker"] == "speaker_0"

    def test_flush_no_translation(self):
        session = _make_session()
        session.buffer_final_tokens = [
            {"text": "Hello", "speaker": "A", "translation_status": "none"},
        ]
        svc = SonioxService()
        svc._flush_buffer(session)
        assert session.utterances[0]["translated_text"] is None

    def test_flush_preserves_timestamps(self):
        session = _make_session()
        session.buffer_final_tokens = [
            {"text": "Hello", "translation_status": "none", "start_ms": 100, "end_ms": 500},
            {"text": " world", "translation_status": "none", "start_ms": 500, "end_ms": 800},
        ]
        svc = SonioxService()
        svc._flush_buffer(session)
        utt = session.utterances[0]
        assert utt["start_ms"] == 100
        assert utt["end_ms"] == 800


class TestReceiverLoopEndpointDetection:
    @pytest.mark.asyncio
    async def test_endpoint_flushes_buffer_and_emits_final(self):
        session = _make_session(meeting_id="meet_ep1")
        svc = SonioxService()

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {"text": "Hello", "is_final": True, "translation_status": "original"},
                        {"text": "<end>", "is_final": True},
                    ],
                }
            ),
            json.dumps({"finished": True}),
        ]

        class FakeWS:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if messages:
                    return messages.pop(0)
                raise StopAsyncIteration

        ws = FakeWS()

        with patch("app.services.soniox_service._sessions", {"meet_ep1": session}):
            await svc._receiver_loop("meet_ep1", ws, session.queue)

        assert len(session.utterances) == 1
        assert session.utterances[0]["text"] == "Hello"

        events = []
        while not session.queue.empty():
            events.append(session.queue.get_nowait())
        assert any(e["type"] == "final" for e in events)
        assert any(e["type"] == "end" for e in events)

    @pytest.mark.asyncio
    async def test_endpoint_filters_end_from_display(self):
        session = _make_session(meeting_id="meet_ep2")
        svc = SonioxService()

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {"text": "Test", "is_final": True, "translation_status": "original"},
                        {"text": "<end>", "is_final": True},
                    ],
                }
            ),
            json.dumps({"finished": True}),
        ]

        class FakeWS:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if messages:
                    return messages.pop(0)
                raise StopAsyncIteration

        ws = FakeWS()

        with patch("app.services.soniox_service._sessions", {"meet_ep2": session}):
            await svc._receiver_loop("meet_ep2", ws, session.queue)

        events = []
        while not session.queue.empty():
            events.append(session.queue.get_nowait())
        final_events = [e for e in events if e["type"] == "final"]
        assert len(final_events) == 1
        texts = [t["text"] for t in final_events[0]["tokens"]]
        assert "<end>" not in texts
        assert "Test" in texts


class TestReceiverLoopPartialAndFinal:
    @pytest.mark.asyncio
    async def test_partial_event(self):
        session = _make_session(meeting_id="meet_part")
        svc = SonioxService()

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {"text": "Hel", "is_final": False, "translation_status": "none"},
                    ],
                }
            ),
            json.dumps({"finished": True}),
        ]

        class FakeWS:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if messages:
                    return messages.pop(0)
                raise StopAsyncIteration

        ws = FakeWS()

        with patch("app.services.soniox_service._sessions", {"meet_part": session}):
            await svc._receiver_loop("meet_part", ws, session.queue)

        events = []
        while not session.queue.empty():
            events.append(session.queue.get_nowait())
        partials = [e for e in events if e.get("type") == "partial"]
        assert len(partials) == 1
        assert partials[0]["tokens"][0]["text"] == "Hel"

    @pytest.mark.asyncio
    async def test_final_without_endpoint(self):
        session = _make_session(meeting_id="meet_fin")
        svc = SonioxService()

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {"text": "Done", "is_final": True, "translation_status": "original"},
                    ],
                }
            ),
            json.dumps({"finished": True}),
        ]

        class FakeWS:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if messages:
                    return messages.pop(0)
                raise StopAsyncIteration

        ws = FakeWS()

        with patch("app.services.soniox_service._sessions", {"meet_fin": session}):
            await svc._receiver_loop("meet_fin", ws, session.queue)

        assert len(session.utterances) == 1
        assert session.utterances[0]["text"] == "Done"


class TestReceiverLoopError:
    @pytest.mark.asyncio
    async def test_error_code_breaks_loop(self):
        session = _make_session(meeting_id="meet_err")
        svc = SonioxService()

        messages = [json.dumps({"error_code": 408, "error_message": "Request timeout."})]

        class FakeWS:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if messages:
                    return messages.pop(0)
                raise StopAsyncIteration

        ws = FakeWS()

        with patch("app.services.soniox_service._sessions", {"meet_err": session}):
            await svc._receiver_loop("meet_err", ws, session.queue)

        events = []
        while not session.queue.empty():
            events.append(session.queue.get_nowait())
        errors = [e for e in events if e.get("type") == "error"]
        assert len(errors) == 1
        assert errors[0]["message"] == "Request timeout."


class TestReceiverLoopTranslation:
    @pytest.mark.asyncio
    async def test_translation_tokens_in_partial(self):
        session = _make_session(meeting_id="meet_trans")
        svc = SonioxService()

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "Hello",
                            "is_final": False,
                            "translation_status": "original",
                            "language": "en",
                        },
                        {
                            "text": " Xin chào",
                            "is_final": False,
                            "translation_status": "translation",
                            "language": "vi",
                        },
                    ],
                }
            ),
            json.dumps({"finished": True}),
        ]

        class FakeWS:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if messages:
                    return messages.pop(0)
                raise StopAsyncIteration

        ws = FakeWS()

        with patch("app.services.soniox_service._sessions", {"meet_trans": session}):
            await svc._receiver_loop("meet_trans", ws, session.queue)

        events = []
        while not session.queue.empty():
            events.append(session.queue.get_nowait())
        partials = [e for e in events if e.get("type") == "partial"]
        assert len(partials) == 1
        statuses = [t["translation_status"] for t in partials[0]["tokens"]]
        assert "original" in statuses
        assert "translation" in statuses


class TestIsActive:
    def test_active_session(self):
        session = _make_session(meeting_id="meet_active")
        svc = SonioxService()
        with patch("app.services.soniox_service._sessions", {"meet_active": session}):
            assert svc.is_active("meet_active") is True

    def test_stopped_session(self):
        session = _make_session(meeting_id="meet_stopped")
        session.stopped = True
        svc = SonioxService()
        with patch("app.services.soniox_service._sessions", {"meet_stopped": session}):
            assert svc.is_active("meet_stopped") is False

    def test_nonexistent_session(self):
        svc = SonioxService()
        assert svc.is_active("meet_none") is False


class TestGetSessionDurationMs:
    def test_nonexistent_returns_zero(self):
        svc = SonioxService()
        assert svc.get_session_duration_ms("none") == 0

    def test_returns_positive_duration(self):
        session = _make_session(meeting_id="meet_dur")
        svc = SonioxService()
        with patch("app.services.soniox_service._sessions", {"meet_dur": session}):
            ms = svc.get_session_duration_ms("meet_dur")
            assert ms >= 0


class TestStopSession:
    @pytest.mark.asyncio
    async def test_stop_nonexistent_returns_empty(self):
        svc = SonioxService()
        result = await svc.stop_session("none")
        assert result == []

    @pytest.mark.asyncio
    async def test_stop_already_stopped_returns_utterances(self):
        session = _make_session(meeting_id="meet_stop1")
        session.stopped = True
        session.utterances = [{"text": "Hello"}]
        svc = SonioxService()
        with patch("app.services.soniox_service._sessions", {"meet_stop1": session}):
            result = await svc.stop_session("meet_stop1")
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_stop_flushes_buffer_and_cleans_up(self):
        session = _make_session(meeting_id="meet_stop2")
        session.buffer_final_tokens = [
            {"text": "Hello", "translation_status": "none", "speaker": "A"},
        ]
        session.receiver_task = AsyncMock()
        session.keepalive_task = MagicMock()
        session.keepalive_task.cancel = MagicMock()
        svc = SonioxService()

        with patch("app.services.soniox_service._sessions", {"meet_stop2": session}):
            result = await svc.stop_session("meet_stop2")

        assert len(result) == 1
        assert result[0]["text"] == "Hello"


class TestSendAudio:
    @pytest.mark.asyncio
    async def test_send_audio_updates_timestamp(self):
        session = _make_session(meeting_id="meet_audio")
        svc = SonioxService()
        with patch("app.services.soniox_service._sessions", {"meet_audio": session}):
            await svc.send_audio("meet_audio", b"\x00\x01")
            session.ws.send.assert_awaited_once_with(b"\x00\x01")
            assert session.last_audio_sent_at > 0

    @pytest.mark.asyncio
    async def test_send_audio_stopped_raises(self):
        session = _make_session(meeting_id="meet_stopped2")
        session.stopped = True
        svc = SonioxService()
        with patch("app.services.soniox_service._sessions", {"meet_stopped2": session}):
            with pytest.raises(ValueError):
                await svc.send_audio("meet_stopped2", b"\x00")

    @pytest.mark.asyncio
    async def test_send_audio_nonexistent_raises(self):
        svc = SonioxService()
        with pytest.raises(ValueError):
            await svc.send_audio("none", b"\x00")
