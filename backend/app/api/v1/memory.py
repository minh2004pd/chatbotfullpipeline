"""Memory endpoints: search, list, delete."""

from fastapi import APIRouter, status

from app.core.dependencies import MemoryServiceDep, UserIDDep
from app.schemas.memory import (
    MemoryDeleteResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    UserMemoryResponse,
)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/search", response_model=MemorySearchResponse)
async def search_memory(
    request: MemorySearchRequest,
    user_id: UserIDDep,
    service: MemoryServiceDep,
) -> MemorySearchResponse:
    """Tìm kiếm long-term memory của user theo query."""
    memories = service.search(query=request.query, user_id=user_id, limit=request.limit)
    return MemorySearchResponse(memories=memories, total=len(memories))


@router.get("", response_model=UserMemoryResponse)
async def get_user_memories(
    user_id: UserIDDep,
    service: MemoryServiceDep,
) -> UserMemoryResponse:
    """Lấy tất cả memories của authenticated user."""
    # Sử dụng authenticated user_id từ JWT/header, không dùng URL path parameter
    memories = service.get_all(user_id=user_id)
    return UserMemoryResponse(user_id=user_id, memories=memories, total=len(memories))


@router.delete("/all", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_memories(
    user_id: UserIDDep,
    service: MemoryServiceDep,
) -> None:
    """Xóa tất cả memories của authenticated user."""
    service.delete_all(user_id=user_id)


@router.delete("/{memory_id}", response_model=MemoryDeleteResponse)
async def delete_memory(
    memory_id: str,
    _auth: UserIDDep,
    service: MemoryServiceDep,
) -> MemoryDeleteResponse:
    """Xóa một memory cụ thể."""
    service.delete(memory_id=memory_id)
    return MemoryDeleteResponse(memory_id=memory_id)
