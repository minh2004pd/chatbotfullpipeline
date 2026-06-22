"""SixtyDBService — batch speech-to-text qua 60db API (file upload).

Bổ sung cho SonioxService (realtime mic streaming): 60db nhận một file audio/video
đã ghi sẵn (≤10MB / 1h), trả về transcript đầy đủ với segments + speaker diarization.

Output được map về CÙNG utterance shape mà SonioxService sinh ra:
  {seq, speaker, language, text, translated_text, confidence, start_ms, end_ms}
→ tái sử dụng toàn bộ downstream pipeline (MeetingRepository → Qdrant RAG → Wiki).

60db STT API (POST {base_url}/stt, multipart/form-data, Bearer auth):
  - file       : audio/video (WAV/MP3/M4A/OGG/FLAC/WebM/MP4) ≤ 10MB
  - language   : ISO 639-1 hoặc "auto" (omit = auto-detect)
  - diarize    : bool → mỗi segment kèm `speakers` array
  - return_timestamps / include_confidence → bật metadata bổ sung
Response: {text, language, duration_sec, segments[], words[], ...}
  segment = {start, end, language, text, confidence, words[], speakers?[]}
"""

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class SixtyDBError(Exception):
    """Lỗi từ 60db API hoặc khi gọi service."""


class SixtyDBService:
    def __init__(self, settings=None) -> None:
        self._settings = settings or get_settings()

    async def transcribe_file(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        language: str | None = None,
        diarize: bool | None = None,
    ) -> dict:
        """Gửi file tới 60db /stt, trả về dict đã normalize.

        Returns:
            {
                "utterances": list[dict],   # canonical utterance shape
                "language": str | None,     # detected/specified ISO 639-1
                "duration_ms": int,
            }
        """
        settings = self._settings
        if not settings.sixtydb_api_key:
            raise SixtyDBError("SIXTYDB_API_KEY chưa được cấu hình")

        max_bytes = settings.sixtydb_max_upload_mb * 1024 * 1024
        if len(file_bytes) > max_bytes:
            raise SixtyDBError(
                f"File vượt quá giới hạn {settings.sixtydb_max_upload_mb}MB của 60db"
            )

        lang = language if language is not None else (settings.sixtydb_default_language or None)
        do_diarize = diarize if diarize is not None else settings.sixtydb_diarize

        data: dict[str, str] = {}
        if lang:
            data["language"] = lang
        if do_diarize:
            data["diarize"] = "true"
        # Bật metadata để map start_ms/end_ms/confidence chính xác hơn
        data["return_timestamps"] = "word"
        data["include_confidence"] = "true"

        files = {"file": (filename, file_bytes, content_type or "application/octet-stream")}
        url = f"{settings.sixtydb_base_url.rstrip('/')}{settings.sixtydb_stt_path}"
        headers = {"Authorization": f"Bearer {settings.sixtydb_api_key}"}

        try:
            async with httpx.AsyncClient(timeout=settings.sixtydb_timeout_sec) as client:
                resp = await client.post(url, headers=headers, data=data, files=files)
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500] if e.response is not None else ""
            logger.error("sixtydb_http_error", status=e.response.status_code, body=body)
            raise SixtyDBError(f"60db trả về lỗi {e.response.status_code}: {body}") from e
        except httpx.HTTPError as e:
            logger.error("sixtydb_request_error", error=str(e))
            raise SixtyDBError(f"Không gọi được 60db STT: {e}") from e

        utterances = self._segments_to_utterances(payload)
        duration_sec = payload.get("duration_sec") or 0
        result = {
            "utterances": utterances,
            "language": payload.get("language"),
            "duration_ms": int(float(duration_sec) * 1000),
        }
        logger.info(
            "sixtydb_transcribed",
            utterances=len(utterances),
            language=result["language"],
            duration_ms=result["duration_ms"],
        )
        return result

    # ── Mapping ────────────────────────────────────────────────────────────────

    @staticmethod
    def _segments_to_utterances(payload: dict) -> list[dict]:
        """Map 60db response.segments[] → canonical utterance dicts.

        Fallback: nếu không có `segments`, dùng top-level `text` thành 1 utterance.
        """
        segments = payload.get("segments") or []
        top_language = payload.get("language")

        if not segments:
            text = (payload.get("text") or "").strip()
            if not text:
                return []
            return [
                {
                    "seq": 0,
                    "speaker": "speaker_0",
                    "language": top_language,
                    "text": text,
                    "translated_text": None,
                    "confidence": None,
                    "start_ms": None,
                    "end_ms": None,
                }
            ]

        utterances: list[dict] = []
        seq = 0
        for seg in segments:
            text = (seg.get("text") or "").strip()
            if not text:
                continue

            utterances.append(
                {
                    "seq": seq,
                    "speaker": SixtyDBService._segment_speaker(seg),
                    "language": seg.get("language") or top_language,
                    "text": text,
                    "translated_text": None,  # 60db STT không dịch (khác Soniox)
                    "confidence": SixtyDBService._to_float(seg.get("confidence")),
                    "start_ms": SixtyDBService._sec_to_ms(seg.get("start")),
                    "end_ms": SixtyDBService._sec_to_ms(seg.get("end")),
                }
            )
            seq += 1

        return utterances

    @staticmethod
    def _segment_speaker(seg: dict) -> str:
        """Lấy speaker label từ diarization. Chuẩn hóa về 'speaker_{n}' như Soniox."""
        speakers = seg.get("speakers")
        raw = None
        if isinstance(speakers, list) and speakers:
            first = speakers[0]
            raw = first.get("speaker") if isinstance(first, dict) else first
        elif "speaker" in seg:
            raw = seg.get("speaker")

        if raw is None:
            return "speaker_0"
        raw_str = str(raw)
        return raw_str if raw_str.startswith("speaker_") else f"speaker_{raw_str}"

    @staticmethod
    def _sec_to_ms(value) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value) * 1000)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
