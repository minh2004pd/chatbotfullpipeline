"""SonioxService — quản lý WebSocket session tới Soniox API (SDK v2).

Soniox v2 event format (không có `type` field):
  - tokens[].is_final = False  → partial result (in-progress)
  - tokens[].is_final = True   → final result (save as utterance)
  - finished = True            → session ended

Flow:
  1. start_session()  → mở WS, gửi config, khởi background receiver task
  2. send_audio()     → forward PCM16 bytes tới Soniox WS
  3. stream_events()  → async generator yield normalized events cho SSE
  4. stop_session()   → gửi EOF, đợi receiver, trả về utterances
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
    utterances: list[dict] = field(default_factory=list)
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    seq: int = 0
    stopped: bool = False


class SonioxService:
    async def start_session(
        self,
        *,
        user_id: str,
        language_hints: list[str] | None = None,
        enable_translation: bool = True,
        translation_target_language: str | None = None,
        enable_speaker_diarization: bool = True,
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
        }
        if language_hints:
            config["language_hints"] = language_hints
        if enable_speaker_diarization:
            config["enable_speaker_diarization"] = True
        if enable_translation:
            config["translation"] = {"type": "one_way", "target_language": target_lang}

        ws = await ws_client.connect(settings.soniox_ws_url)
        await ws.send(json.dumps(config))
        logger.info("soniox_session_started", meeting_id=meeting_id)

        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            self._receiver_loop(meeting_id, ws, queue),
            name=f"soniox-receiver-{meeting_id}",
        )
        _sessions[meeting_id] = _SonioxSession(
            meeting_id=meeting_id,
            user_id=user_id,
            ws=ws,
            queue=queue,
            receiver_task=task,
        )
        return meeting_id

    async def send_audio(self, meeting_id: str, audio_data: bytes) -> None:
        session = _sessions.get(meeting_id)
        if session is None or session.stopped:
            raise ValueError(f"Session {meeting_id} không tồn tại hoặc đã dừng")
        await session.ws.send(audio_data)

    async def stream_events(self, meeting_id: str):
        """Async generator: yield normalized events cho SSE endpoint."""
        session = _sessions.get(meeting_id)
        if session is None:
            # Session không tồn tại (backend restart?) — gửi end ngay
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
            await session.ws.send(b"")
            await asyncio.wait_for(session.receiver_task, timeout=30.0)
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning("soniox_stop_error", meeting_id=meeting_id, error=str(e))
            session.receiver_task.cancel()
        finally:
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

    async def _receiver_loop(
        self, meeting_id: str, ws: ws_client.ClientConnection, queue: asyncio.Queue
    ) -> None:
        """Parse Soniox v2 events → normalize → đưa vào queue."""
        session = _sessions.get(meeting_id)
        try:
            async for raw_msg in ws:
                if isinstance(raw_msg, bytes):
                    continue

                raw = json.loads(raw_msg)

                # Soniox v2: kiểm tra finished flag
                if raw.get("finished"):
                    await queue.put({"type": "end", "meeting_id": meeting_id})
                    break

                # Error
                if raw.get("error_code"):
                    err_msg = raw.get("error_message", "Unknown Soniox error")
                    logger.error("soniox_api_error", code=raw["error_code"], msg=err_msg)
                    await queue.put({"type": "error", "meeting_id": meeting_id, "message": err_msg})
                    break

                tokens: list[dict] = raw.get("tokens", [])
                if not tokens:
                    continue  # periodic heartbeat với tokens rỗng, bỏ qua

                # Extract translation từ Soniox response
                translated_tokens: list[dict] = raw.get("translated_tokens", [])
                translation_text = "".join(t.get("text", "") for t in translated_tokens).strip()

                has_final = any(t.get("is_final") for t in tokens)

                if has_final:
                    # Lưu utterance
                    if session:
                        utterance = self._build_utterance(meeting_id, tokens, session, translation_text)
                        session.utterances.append(utterance)
                        session.seq += 1
                    normalized = {
                        "type": "final",
                        "meeting_id": meeting_id,
                        "tokens": [
                            {
                                "text": t.get("text", ""),
                                "speaker": t.get("speaker"),
                                "is_final": True,
                            }
                            for t in tokens
                            if t.get("is_final")
                        ],
                        "translation": translation_text or None,
                    }
                else:
                    normalized = {
                        "type": "partial",
                        "meeting_id": meeting_id,
                        "tokens": [
                            {"text": t.get("text", ""), "speaker": t.get("speaker")} for t in tokens
                        ],
                        "translation": translation_text or None,
                    }

                await queue.put(normalized)

        except WsConnectionClosed:
            logger.info("soniox_ws_closed", meeting_id=meeting_id)
        except Exception as e:
            logger.error("soniox_receiver_error", meeting_id=meeting_id, error=str(e))
            await queue.put({"type": "error", "meeting_id": meeting_id, "message": str(e)})
        finally:
            await queue.put({"type": "end", "meeting_id": meeting_id})

    @staticmethod
    def _build_utterance(
        meeting_id: str, tokens: list[dict], session: "_SonioxSession", translation: str | None = None
    ) -> dict:
        final_tokens = [t for t in tokens if t.get("is_final")]
        text = "".join(t.get("text", "") for t in final_tokens).strip()
        # Soniox v2: speaker là string (ví dụ "A", "B") thay vì int
        raw_speaker = final_tokens[0].get("speaker") if final_tokens else None
        speaker = f"speaker_{raw_speaker}" if raw_speaker else "speaker_0"

        return {
            "meeting_id": meeting_id,
            "user_id": session.user_id,
            "seq": session.seq,
            "speaker": speaker,
            "text": text,
            "translated_text": translation or None,
            "start_ms": final_tokens[0].get("start_ms") if final_tokens else None,
            "end_ms": final_tokens[-1].get("end_ms") if final_tokens else None,
        }
