"""Session management endpoints."""

from fastapi import APIRouter, HTTPException, Response, status

from app.core.dependencies import CacheDep, SessionServiceDep, SettingsDep, UserIDDep
from app.schemas.session import MessageItem, SessionListItem, SessionMessages

router = APIRouter(prefix="/sessions", tags=["sessions"])

APP_NAME = "memrag"


@router.get("", response_model=list[SessionListItem])
async def list_sessions(
    user_id: UserIDDep,
    service: SessionServiceDep,
    cache: CacheDep,
    settings: SettingsDep,
) -> list[SessionListItem]:
    """Liệt kê tất cả sessions của user (sắp xếp mới nhất trước)."""
    cache_key = f"memrag:sessions:{user_id}:list"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return [SessionListItem(**item) for item in cached]

    items = service.list_sessions_with_metadata(app_name=APP_NAME, user_id=user_id)
    result = [
        SessionListItem(
            session_id=item["session_id"],
            title=item.get("title", "New Chat"),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
            message_count=int(item.get("message_count", 0)),
        )
        for item in items
    ]
    await cache.set_json(
        cache_key, [r.model_dump(mode="json") for r in result], ttl=settings.redis_session_list_ttl
    )
    return result


@router.get("/{session_id}", response_model=SessionMessages)
async def get_session_messages(
    session_id: str,
    user_id: UserIDDep,
    service: SessionServiceDep,
) -> SessionMessages:
    """Lấy lịch sử tin nhắn của một session."""
    result = service.get_session_messages(app_name=APP_NAME, user_id=user_id, session_id=session_id)
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
    cache: CacheDep,
) -> Response:
    """Xóa một session."""
    await service.delete_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    await cache.delete(f"memrag:sessions:{user_id}:list")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
