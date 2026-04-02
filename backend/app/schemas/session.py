"""Schemas cho session management endpoints."""

from datetime import datetime

from pydantic import BaseModel


class SessionListItem(BaseModel):
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class MessageItem(BaseModel):
    role: str  # "user" | "model"
    content: str
    timestamp: datetime


class SessionMessages(BaseModel):
    session_id: str
    title: str
    messages: list[MessageItem]
