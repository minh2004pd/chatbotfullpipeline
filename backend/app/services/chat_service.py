"""Chat Service: orchestrate ADK agent runs."""

import uuid
from typing import AsyncIterator

import structlog
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions.base_session_service import BaseSessionService
from google.genai.types import Content, Part

from app.core.config import Settings
from app.schemas.chat import ChatRequest, ChatResponse, Citation

logger = structlog.get_logger(__name__)

APP_NAME = "memrag"


def _decode_base64(data: str) -> bytes:
    """Decode base64 với xử lý prefix và padding."""
    import base64
    import re

    # Loại bỏ prefix data:image/...;base64, nếu có
    if "," in data:
        data = data.split(",", 1)[1]

    # Loại bỏ khoảng trắng/newlines
    data = re.sub(r"\s+", "", data)

    # Thêm padding nếu thiếu
    missing_padding = len(data) % 4
    if missing_padding:
        data += "=" * (4 - missing_padding)

    return base64.b64decode(data)


def _build_user_content(request: ChatRequest) -> Content:
    """Tạo Content object từ ChatRequest (text + optional image)."""
    parts: list[Part] = []

    if request.message and request.message.strip():
        parts.append(Part.from_text(text=request.message))

    if request.image_base64 and request.image_base64.lower() != "string":
        image_bytes = _decode_base64(request.image_base64)
        mime_type = request.image_mime_type
        # Xử lý trường hợp Swagger/Client gửi default value là "string"
        if not mime_type or mime_type.lower() == "string":
            mime_type = "image/jpeg"
        parts.append(Part.from_bytes(data=image_bytes, mime_type=mime_type))

    if not parts:
        # Gemini yêu cầu ít nhất 1 part
        parts.append(Part.from_text(text=" "))

    return Content(role="user", parts=parts)


async def _ensure_session(
    session_service: BaseSessionService,
    user_id: str,
    session_id: str,
    max_context_messages: int,
) -> None:
    """Tạo session nếu chưa tồn tại."""
    existing = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if existing is None:
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
            state={
                "user_id": user_id,
                "max_context_messages": max_context_messages,
            },
        )


class ChatService:
    def __init__(
        self,
        runner: Runner,
        session_service: BaseSessionService,
        settings: Settings,
    ):
        self.runner = runner
        self.session_service = session_service
        self.settings = settings

    def _resolve_session_id(self, session_id: str | None, user_id: str) -> str:
        if not session_id or session_id.lower() == "string":
            return f"{user_id}_{uuid.uuid4().hex[:8]}"
        return session_id

    async def chat(self, request: ChatRequest) -> ChatResponse:
        session_id = self._resolve_session_id(request.session_id, request.user_id)

        await _ensure_session(
            session_service=self.session_service,
            user_id=request.user_id,
            session_id=session_id,
            max_context_messages=self.settings.max_context_messages,
        )

        user_content = _build_user_content(request)
        final_text = ""
        citations: list[Citation] = []

        async for event in self.runner.run_async(
            user_id=request.user_id,
            session_id=session_id,
            new_message=user_content,
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts or []:
                    if part.text:
                        final_text += part.text

            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "function_response") and part.function_response:
                        resp = part.function_response
                        if resp.name == "search_documents":
                            for r in (resp.response or {}).get("results", []):
                                citations.append(
                                    Citation(
                                        document_id=r.get("document_id", ""),
                                        document_name=r.get("source", ""),
                                        chunk_text=r.get("text", "")[:200],
                                        score=r.get("relevance_score", 0.0),
                                    )
                                )

        logger.info("chat_done", user_id=request.user_id, session_id=session_id)
        return ChatResponse(
            message=final_text,
            session_id=session_id,
            user_id=request.user_id,
            citations=citations,
        )

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """Stream response dưới dạng SSE chunks."""
        session_id = self._resolve_session_id(request.session_id, request.user_id)

        await _ensure_session(
            session_service=self.session_service,
            user_id=request.user_id,
            session_id=session_id,
            max_context_messages=self.settings.max_context_messages,
        )

        run_config = RunConfig(streaming_mode=StreamingMode.SSE)

        async for event in self.runner.run_async(
            user_id=request.user_id,
            session_id=session_id,
            new_message=_build_user_content(request),
            run_config=run_config,
        ):
            if event.partial and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        yield part.text
