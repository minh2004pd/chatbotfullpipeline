"""Pydantic schemas cho transcription / meetings."""

from datetime import datetime

from pydantic import BaseModel, Field


class TranscriptionToken(BaseModel):
    text: str
    speaker: str | None = None
    language: str | None = None
    translation_status: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None


class TranscriptionEvent(BaseModel):
    """Event stream từ Soniox → SSE về frontend."""

    type: str  # "partial" | "final" | "error" | "end"
    meeting_id: str
    tokens: list[TranscriptionToken] = []


class StartTranscriptionRequest(BaseModel):
    title: str | None = None
    language_hints: list[str] = ["vi", "en"]
    enable_translation: bool = True
    translation_target_language: str = "vi"
    enable_speaker_diarization: bool = True
    enable_language_identification: bool = False
    enable_endpoint_detection: bool = True
    max_endpoint_delay_ms: int | None = None
    context: dict | None = None


class StartTranscriptionResponse(BaseModel):
    meeting_id: str
    status: str = "started"


class StopTranscriptionResponse(BaseModel):
    meeting_id: str
    status: str = "completed"
    utterance_count: int = 0


class MeetingInfo(BaseModel):
    meeting_id: str
    title: str
    user_id: str
    status: str  # "recording" | "completed"
    duration_ms: int | None = None
    speakers: list[str] = []
    languages: list[str] = []
    utterance_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None


class MeetingListResponse(BaseModel):
    meetings: list[MeetingInfo]
    total: int


class UtteranceItem(BaseModel):
    speaker: str
    language: str | None = None
    text: str
    translated_text: str | None = None
    confidence: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    created_at: datetime | None = None


class MeetingTranscriptResponse(BaseModel):
    meeting_id: str
    title: str
    utterances: list[UtteranceItem]
    total: int


class AudioChunkRequest(BaseModel):
    """Metadata kèm audio chunk (binary body gửi riêng)."""

    meeting_id: str = Field(..., description="ID của meeting đang record")
