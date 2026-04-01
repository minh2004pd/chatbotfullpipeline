from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    message: str = Field(default="", min_length=1, max_length=10000)
    user_id: str = Field(default="default_user", min_length=1, max_length=100)
    session_id: str | None = None
    image_base64: str | None = None  # base64 encoded image
    image_mime_type: str | None = None  # e.g. "image/jpeg"


class Citation(BaseModel):
    document_id: str
    document_name: str
    chunk_text: str
    score: float


class ChatResponse(BaseModel):
    message: str
    session_id: str
    user_id: str
    citations: list[Citation] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StreamChunk(BaseModel):
    content: str
    is_final: bool = False
    session_id: str | None = None
    citations: list[Citation] = []
