"""SonioxService — quản lý WebSocket session tới Soniox API.

Soniox v2 event format:
  - tokens[].is_final = False  → partial result (in-progress)
  - tokens[].is_final = True   → final result
  - tokens[].text = "<end>"    → endpoint detected (utterance complete)
  - finished = True            → session ended

Token translation_status:
  - "none"        → not translated (language outside translation pair)
  - "original"    → spoken text (will be followed by translation tokens)
  - "translation" → translated text

Flow:
  1. start_session()  → mở WS, gửi config, khởi background receiver task
  2. send_audio()     → forward PCM16 bytes tới Soniox WS
  3. stream_events()  → async generator yield normalized events cho SSE
  4. stop_session()   → gửi EOF, đợi receiver, flush buffer, trả về utterances
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog
import websockets.asyncio.client as ws_client
from websockets.exceptions import ConnectionClosed as WsConnectionClosed

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

_sessions: dict[str, "_SonioxSession"] = {}


@dataclass
class _SonioxSession:
    meeting_id: str
    user_id: str
    ws: ws_client.ClientConnection
    queue: asyncio.Queue
    receiver_task: asyncio.Task
    keepalive_task: asyncio.Task | None = None
    utterances: list[dict] = field(default_factory=list)
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    seq: int = 0
    stopped: bool = False

    buffer_final_tokens: list[dict] = field(default_factory=list)
    buffer_non_final_tokens: list[dict] = field(default_factory=list)
    last_audio_sent_at: float = 0.0


class SonioxService:
    async def start_session(
        self,
        *,
        user_id: str,
        language_hints: list[str] | None = None,
        enable_translation: bool = True,
        translation_target_language: str | None = None,
        enable_speaker_diarization: bool = True,
        enable_language_identification: bool = False,
        enable_endpoint_detection: bool = True,
        max_endpoint_delay_ms: int | None = None,
        context: dict | None = None,
        sample_rate: int = 16000,
    ) -> str:
        settings = get_settings()
        if not settings.soniox_api_key:
            raise ValueError("SONIOX_API_KEY chưa được cấu hình")

        meeting_id = f"meet_{uuid.uuid4().hex[:12]}"
        target_lang = translation_target_language or settings.soniox_target_lang

        config: dict = {
            "api_key": settings.soniox_api_key,
            "model": settings.soniox_model,
            "audio_format": "pcm_s16le",
            "sample_rate": sample_rate,
            "num_channels": 1,
            "enable_endpoint_detection": enable_endpoint_detection,
        }
        if language_hints:
            config["language_hints"] = language_hints
        if enable_speaker_diarization:
            config["enable_speaker_diarization"] = True
        if enable_language_identification:
            config["enable_language_identification"] = True
        if enable_translation:
            config["translation"] = {"type": "one_way", "target_language": target_lang}
        if max_endpoint_delay_ms is not None:
            config["max_endpoint_delay_ms"] = max_endpoint_delay_ms
        if context:
            config["context"] = context

        ws = await ws_client.connect(settings.soniox_ws_url)
        await ws.send(json.dumps(config))
        logger.info(
            "soniox_session_started",
            meeting_id=meeting_id,
            endpoint_detection=enable_endpoint_detection,
            translation=enable_translation,
        )

        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            self._receiver_loop(meeting_id, ws, queue),
            name=f"soniox-receiver-{meeting_id}",
        )
        keepalive_task = asyncio.create_task(
            self._keepalive_loop(meeting_id, ws),
            name=f"soniox-keepalive-{meeting_id}",
        )
        _sessions[meeting_id] = _SonioxSession(
            meeting_id=meeting_id,
            user_id=user_id,
            ws=ws,
            queue=queue,
            receiver_task=task,
            keepalive_task=keepalive_task,
            last_audio_sent_at=asyncio.get_event_loop().time(),
        )
        return meeting_id

    async def send_audio(self, meeting_id: str, audio_data: bytes) -> None:
        session = _sessions.get(meeting_id)
        if session is None or session.stopped:
            raise ValueError(f"Session {meeting_id} không tồn tại hoặc đã dừng")
        await session.ws.send(audio_data)
        session.last_audio_sent_at = asyncio.get_event_loop().time()

    async def stream_events(self, meeting_id: str):
        session = _sessions.get(meeting_id)
        if session is None:
            yield {"type": "end", "meeting_id": meeting_id}
            return

        while True:
            try:
                event = await asyncio.wait_for(session.queue.get(), timeout=25.0)
            except asyncio.TimeoutError:
                yield {"type": "keepalive", "meeting_id": meeting_id}
                continue

            yield event
            if event.get("type") in ("end", "error"):
                break

    async def stop_session(self, meeting_id: str) -> list[dict]:
        session = _sessions.get(meeting_id)
        if session is None:
            return []
        if session.stopped:
            return list(session.utterances)

        session.stopped = True
        try:
            if session.keepalive_task:
                session.keepalive_task.cancel()
            await session.ws.send(b"")
            await asyncio.wait_for(session.receiver_task, timeout=30.0)
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning("soniox_stop_error", meeting_id=meeting_id, error=str(e))
            session.receiver_task.cancel()
        finally:
            self._flush_buffer(session)
            try:
                await session.ws.close()
            except Exception:
                pass

        utterances_result = list(session.utterances)
        _sessions.pop(meeting_id, None)
        logger.info(
            "soniox_session_stopped", meeting_id=meeting_id, utterances=len(utterances_result)
        )
        return utterances_result

    def get_session_duration_ms(self, meeting_id: str) -> int:
        session = _sessions.get(meeting_id)
        if session is None:
            return 0
        return int((datetime.now(timezone.utc) - session.start_time).total_seconds() * 1000)

    def is_active(self, meeting_id: str) -> bool:
        return meeting_id in _sessions and not _sessions[meeting_id].stopped

    # ── Internal ──────────────────────────────────────────────────────────────

    def _flush_buffer(self, session: "_SonioxSession") -> None:
        if not session.buffer_final_tokens:
            return
        final_tokens = session.buffer_final_tokens
        original_tokens, translation_tokens = self._split_translation_tokens(final_tokens)
        text = "".join(t.get("text", "") for t in original_tokens).strip()
        translation_text = (
            "".join(t.get("text", "") for t in translation_tokens).strip()
            if translation_tokens
            else None
        )
        if not text:
            session.buffer_final_tokens = []
            session.buffer_non_final_tokens = []
            return
        raw_speaker = original_tokens[0].get("speaker") if original_tokens else None
        speaker = f"speaker_{raw_speaker}" if raw_speaker else "speaker_0"
        language = original_tokens[0].get("language") if original_tokens else None

        utterance = {
            "meeting_id": session.meeting_id,
            "user_id": session.user_id,
            "seq": session.seq,
            "speaker": speaker,
            "language": language,
            "text": text,
            "translated_text": translation_text,
            "start_ms": original_tokens[0].get("start_ms") if original_tokens else None,
            "end_ms": original_tokens[-1].get("end_ms") if original_tokens else None,
        }
        session.utterances.append(utterance)
        session.seq += 1
        session.buffer_final_tokens = []
        session.buffer_non_final_tokens = []

    @staticmethod
    def _split_translation_tokens(tokens: list[dict]) -> tuple[list[dict], list[dict]]:
        original = []
        translation = []
        for t in tokens:
            status = t.get("translation_status", "none")
            if status == "translation":
                translation.append(t)
            else:
                original.append(t)
        return original, translation

    @staticmethod
    def _filter_display_tokens(tokens: list[dict]) -> list[dict]:
        return [
            {
                "text": t.get("text", ""),
                "speaker": t.get("speaker"),
                "language": t.get("language"),
                "translation_status": t.get("translation_status", "none"),
            }
            for t in tokens
            if t.get("is_final") and t.get("text") != "<end>"
        ]

    async def _keepalive_loop(self, meeting_id: str, ws: ws_client.ClientConnection) -> None:
        try:
            while True:
                await asyncio.sleep(10)
                session = _sessions.get(meeting_id)
                if session is None or session.stopped:
                    break
                elapsed = asyncio.get_event_loop().time() - session.last_audio_sent_at
                if elapsed >= 10:
                    await ws.send(json.dumps({"type": "keepalive"}))
                    logger.debug("soniox_keepalive_sent", meeting_id=meeting_id)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("soniox_keepalive_error", meeting_id=meeting_id, error=str(e))

    async def _receiver_loop(
        self, meeting_id: str, ws: ws_client.ClientConnection, queue: asyncio.Queue
    ) -> None:
        session = _sessions.get(meeting_id)
        try:
            async for raw_msg in ws:
                if isinstance(raw_msg, bytes):
                    continue

                raw = json.loads(raw_msg)

                if raw.get("finished"):
                    self._flush_buffer(session)
                    await queue.put({"type": "end", "meeting_id": meeting_id})
                    break

                if raw.get("error_code"):
                    err_msg = raw.get("error_message", "Unknown Soniox error")
                    logger.error("soniox_api_error", code=raw["error_code"], msg=err_msg)
                    self._flush_buffer(session)
                    await queue.put({"type": "error", "meeting_id": meeting_id, "message": err_msg})
                    break

                tokens: list[dict] = raw.get("tokens", [])
                if not tokens:
                    continue

                has_endpoint = any(t.get("text") == "<end>" for t in tokens)

                if has_endpoint:
                    endpoint_tokens = [t for t in tokens if t.get("text") != "<end>"]
                    for t in endpoint_tokens:
                        if t.get("is_final"):
                            session.buffer_final_tokens.append(t)
                        else:
                            session.buffer_non_final_tokens.append(t)

                    self._flush_buffer(session)

                    display = self._filter_display_tokens(tokens)
                    if display:
                        normalized = {
                            "type": "final",
                            "meeting_id": meeting_id,
                            "tokens": display,
                        }
                        await queue.put(normalized)
                    continue

                has_final = any(t.get("is_final") for t in tokens)
                if has_final:
                    for t in tokens:
                        if t.get("is_final"):
                            session.buffer_final_tokens.append(t)
                        else:
                            session.buffer_non_final_tokens.append(t)

                    display = self._filter_display_tokens(tokens)
                    if display:
                        normalized = {
                            "type": "final",
                            "meeting_id": meeting_id,
                            "tokens": display,
                        }
                        await queue.put(normalized)
                else:
                    session.buffer_non_final_tokens = tokens
                    original_tokens, translation_tokens = self._split_translation_tokens(tokens)

                    normalized = {
                        "type": "partial",
                        "meeting_id": meeting_id,
                        "tokens": [
                            {
                                "text": t.get("text", ""),
                                "speaker": t.get("speaker"),
                                "language": t.get("language"),
                                "translation_status": t.get("translation_status", "none"),
                            }
                            for t in original_tokens + translation_tokens
                        ],
                    }
                    await queue.put(normalized)

        except WsConnectionClosed:
            logger.info("soniox_ws_closed", meeting_id=meeting_id)
            if session:
                self._flush_buffer(session)
        except Exception as e:
            logger.error("soniox_receiver_error", meeting_id=meeting_id, error=str(e))
            await queue.put({"type": "error", "meeting_id": meeting_id, "message": str(e)})
        finally:
            await queue.put({"type": "end", "meeting_id": meeting_id})
