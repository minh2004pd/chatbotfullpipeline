"""Chat endpoints."""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.dependencies import ChatServiceDep, UserIDDep
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_id: UserIDDep,
    service: ChatServiceDep,
) -> ChatResponse:
    """Chat với AI agent. Hỗ trợ text và ảnh (base64)."""
    request.user_id = user_id
    return await service.chat(request)


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    user_id: UserIDDep,
    service: ChatServiceDep,
) -> StreamingResponse:
    """Chat với streaming response (Server-Sent Events)."""
    request.user_id = user_id

    async def generate():
        try:
            async for chunk in service.chat_stream(request):
                if isinstance(chunk, dict):
                    yield f"data: {json.dumps(chunk)}\n\n"
                else:
                    yield f"data: {json.dumps({'content': chunk, 'done': False})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'content': f'[Error: {exc}]', 'done': False})}\n\n"
        finally:
            yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
