"""Transcription API — Soniox realtime transcription endpoints.

Endpoints:
  POST /transcription/start              → bắt đầu session, trả meeting_id
  POST /transcription/audio/{meeting_id} → gửi audio chunk (binary body)
  GET  /transcription/stream/{meeting_id}→ SSE stream partial/final events
  POST /transcription/stop/{meeting_id}  → dừng, lưu DB + ingest RAG
  GET  /meetings                         → list meetings của user
  GET  /meetings/{meeting_id}/transcript → full transcript
  DELETE /meetings/{meeting_id}          → xóa meeting
"""

import asyncio
import json
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.core.dependencies import UserIDDep
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.transcription import (
    MeetingListResponse,
    MeetingTranscriptResponse,
    StartTranscriptionRequest,
    StartTranscriptionResponse,
    StopTranscriptionResponse,
    UtteranceItem,
)
from app.services.soniox_service import SonioxService
from app.services.transcript_rag_service import TranscriptRAGService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/transcription", tags=["transcription"])
meetings_router = APIRouter(prefix="/meetings", tags=["meetings"])

# ── Service/repo instances (module-level singletons) ─────────────────────────
# SonioxService đã dùng module-level _sessions dict → safe với single process
_soniox = SonioxService()


def _get_meeting_repo() -> MeetingRepository:
    from app.core.config import get_settings
    from app.core.database import get_dynamodb_resource

    settings = get_settings()
    resource = get_dynamodb_resource()
    table = resource.Table(settings.meetings_table_name)
    return MeetingRepository(table)


def _get_transcript_rag() -> TranscriptRAGService:
    from app.core.database import get_qdrant_client

    return TranscriptRAGService(get_qdrant_client())


def _get_wiki_service():
    from app.core.config import get_settings
    from app.core.dependencies import get_wiki_repo
    from app.services.wiki_service import WikiService

    return WikiService(repo=get_wiki_repo(), settings=get_settings())


# ── Transcription endpoints ───────────────────────────────────────────────────


@router.post("/start", response_model=StartTranscriptionResponse)
async def start_transcription(
    req: StartTranscriptionRequest,
    user_id: UserIDDep,
):
    """Bắt đầu session transcription mới."""
    meeting_id = await _soniox.start_session(
        user_id=user_id,
        language_hints=req.language_hints,
        enable_translation=req.enable_translation,
        translation_target_language=req.translation_target_language,
        enable_speaker_diarization=req.enable_speaker_diarization,
    )

    title = req.title or f"Meeting {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
    repo = _get_meeting_repo()
    repo.create_meeting(meeting_id=meeting_id, user_id=user_id, title=title)

    logger.info("transcription_started", meeting_id=meeting_id, user_id=user_id)
    return StartTranscriptionResponse(meeting_id=meeting_id)


@router.post("/audio/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def send_audio_chunk(meeting_id: str, request: Request, user_id: UserIDDep):
    """Nhận binary PCM16 audio chunk và forward tới Soniox."""
    if not _soniox.is_active(meeting_id):
        # Session không còn active (backend restart hoặc WS đóng) — bỏ qua chunk
        return

    audio_data = await request.body()
    if not audio_data:
        return

    try:
        await _soniox.send_audio(meeting_id, audio_data)
    except Exception as e:
        logger.warning("send_audio_failed", meeting_id=meeting_id, error=str(e))


@router.get("/stream/{meeting_id}")
async def stream_transcription(meeting_id: str, user_id: UserIDDep):
    """SSE stream: gửi partial/final transcript events về frontend."""

    async def event_generator():
        async for event in _soniox.stream_events(meeting_id):
            event_type = event.get("type", "")
            if event_type == "keepalive":
                yield ": keepalive\n\n"
                continue
            data = json.dumps(event)
            yield f"data: {data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/stop/{meeting_id}", response_model=StopTranscriptionResponse)
async def stop_transcription(meeting_id: str, user_id: UserIDDep):
    """Dừng transcription session, lưu utterances vào DynamoDB, ingest vào Qdrant RAG."""
    duration_ms = _soniox.get_session_duration_ms(meeting_id)
    utterances = await _soniox.stop_session(meeting_id)  # returns [] nếu session không tồn tại

    repo = _get_meeting_repo()

    # Lưu utterances vào DynamoDB
    speakers: set[str] = set()
    for utt in utterances:
        speakers.add(utt.get("speaker", "speaker_0"))
        repo.save_utterance(
            meeting_id=meeting_id,
            user_id=user_id,
            seq=utt.get("seq", 0),
            speaker=utt.get("speaker", "speaker_0"),
            text=utt.get("text", ""),
            translated_text=utt.get("translated_text"),
            start_ms=utt.get("start_ms"),
            end_ms=utt.get("end_ms"),
        )

    # Cập nhật meeting metadata
    repo.update_meeting_status(
        meeting_id=meeting_id,
        user_id=user_id,
        status="completed",
        duration_ms=duration_ms,
        speakers=list(speakers),
        utterance_count=len(utterances),
    )

    # Ingest vào Qdrant nếu có utterances
    if utterances:
        meeting_meta = repo.get_meeting(meeting_id=meeting_id, user_id=user_id)
        title = meeting_meta.get("title", "Untitled") if meeting_meta else "Untitled"
        rag = _get_transcript_rag()
        try:
            await asyncio.to_thread(
                rag.ingest_utterances,
                meeting_id=meeting_id,
                user_id=user_id,
                title=title,
                utterances=utterances,
            )
        except Exception as e:
            logger.warning("transcript_rag_ingest_failed", meeting_id=meeting_id, error=str(e))

    # Fire-and-forget: tổng hợp wiki từ transcript vừa stop (background, không block response)
    from app.core.config import get_settings as _gs

    if utterances and _gs().wiki_enabled:
        meeting_meta_for_wiki = repo.get_meeting(meeting_id=meeting_id, user_id=user_id)
        wiki_title = (
            meeting_meta_for_wiki.get("title", "Untitled") if meeting_meta_for_wiki else "Untitled"
        )
        asyncio.create_task(
            _get_wiki_service().update_wiki_from_transcript(
                user_id=user_id,
                meeting_id=meeting_id,
                title=wiki_title,
                utterances=utterances,
            )
        )

    logger.info("transcription_stopped", meeting_id=meeting_id, utterances=len(utterances))
    return StopTranscriptionResponse(
        meeting_id=meeting_id,
        status="completed",
        utterance_count=len(utterances),
    )


# ── Meetings CRUD endpoints ───────────────────────────────────────────────────


@meetings_router.get("", response_model=MeetingListResponse)
def list_meetings(user_id: UserIDDep):
    """Lấy danh sách meetings của user."""
    repo = _get_meeting_repo()
    items = repo.list_meetings(user_id=user_id)

    meetings = []
    for item in items:
        meetings.append(
            {
                "meeting_id": item.get("meeting_id", ""),
                "title": item.get("title", "Untitled"),
                "user_id": item.get("user_id", user_id),
                "status": item.get("status", "completed"),
                "duration_ms": item.get("duration_ms"),
                "speakers": item.get("speakers", []),
                "languages": item.get("languages", []),
                "utterance_count": item.get("utterance_count", 0),
                "created_at": item.get("created_at", datetime.now(timezone.utc).isoformat()),
                "updated_at": item.get("updated_at"),
            }
        )

    return MeetingListResponse(meetings=meetings, total=len(meetings))


@meetings_router.get("/{meeting_id}/transcript", response_model=MeetingTranscriptResponse)
def get_transcript(meeting_id: str, user_id: UserIDDep):
    """Lấy full transcript của một meeting."""
    repo = _get_meeting_repo()
    meta = repo.get_meeting(meeting_id=meeting_id, user_id=user_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Meeting không tồn tại")

    utterances_raw = repo.list_utterances(meeting_id=meeting_id)
    utterances = [
        UtteranceItem(
            speaker=u.get("speaker", "speaker_0"),
            language=u.get("language"),
            text=u.get("text", ""),
            translated_text=u.get("translated_text"),
            confidence=u.get("confidence"),
            start_ms=u.get("start_ms"),
            end_ms=u.get("end_ms"),
            created_at=datetime.fromisoformat(u["created_at"]) if u.get("created_at") else None,
        )
        for u in utterances_raw
    ]

    return MeetingTranscriptResponse(
        meeting_id=meeting_id,
        title=meta.get("title", "Untitled"),
        utterances=utterances,
        total=len(utterances),
    )


@meetings_router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(meeting_id: str, user_id: UserIDDep):
    """Xóa meeting và transcript khỏi DynamoDB + Qdrant."""
    repo = _get_meeting_repo()
    meta = repo.get_meeting(meeting_id=meeting_id, user_id=user_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Meeting không tồn tại")

    repo.delete_meeting(meeting_id=meeting_id, user_id=user_id)

    # Xóa Qdrant chunks
    rag = _get_transcript_rag()
    try:
        rag.delete_meeting(meeting_id)
    except Exception as e:
        logger.warning("meeting_qdrant_delete_failed", meeting_id=meeting_id, error=str(e))

    # Fire-and-forget: dọn dẹp wiki pages liên quan đến meeting bị xóa
    from app.core.config import get_settings as _gs

    if _gs().wiki_enabled:
        asyncio.create_task(
            _get_wiki_service().remove_source_from_wiki(
                user_id=user_id,
                source_id=meeting_id,
            )
        )
