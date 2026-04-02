"""Session management endpoints."""

from fastapi import APIRouter, HTTPException, Response, status

from app.core.dependencies import SessionServiceDep, UserIDDep
from app.schemas.session import MessageItem, SessionListItem, SessionMessages

router = APIRouter(prefix="/sessions", tags=["sessions"])

APP_NAME = "memrag"


@router.get("", response_model=list[SessionListItem])
async def list_sessions(
    user_id: UserIDDep,
    service: SessionServiceDep,
) -> list[SessionListItem]:
    """Liệt kê tất cả sessions của user (sắp xếp mới nhất trước)."""
    items = service.list_sessions_with_metadata(app_name=APP_NAME, user_id=user_id)
    return [
        SessionListItem(
            session_id=item["session_id"],
            title=item.get("title", "New Chat"),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
            message_count=int(item.get("message_count", 0)),
        )
        for item in items
    ]


@router.get("/{session_id}", response_model=SessionMessages)
async def get_session_messages(
    session_id: str,
    user_id: UserIDDep,
    service: SessionServiceDep,
) -> SessionMessages:
    """Lấy lịch sử tin nhắn của một session."""
    result = service.get_session_messages(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session không tồn tại.")
    return SessionMessages(
        session_id=result["session_id"],
        title=result["title"],
        messages=[MessageItem(**m) for m in result["messages"]],
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user_id: UserIDDep,
    service: SessionServiceDep,
) -> Response:
    """Xóa một session."""
    await service.delete_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
