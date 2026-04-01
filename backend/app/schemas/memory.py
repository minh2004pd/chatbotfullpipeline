from datetime import datetime
from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    id: str
    memory: str
    user_id: str
    score: float | None = None
    created_at: datetime | None = None


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    user_id: str = Field(..., min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


class MemorySearchResponse(BaseModel):
    memories: list[MemoryItem]
    total: int


class UserMemoryResponse(BaseModel):
    user_id: str
    memories: list[MemoryItem]
    total: int


class MemoryDeleteResponse(BaseModel):
    memory_id: str
    message: str = "Memory deleted successfully"
