from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    user_id: str
    display_name: str | None = None
    preferences: dict = Field(default_factory=dict)
    memory_count: int = 0
    document_count: int = 0
