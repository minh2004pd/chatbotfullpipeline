from functools import lru_cache
from typing import Literal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "MemRAG Chatbot"
    app_version: str = "0.1.0"
    debug: bool = False
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Google Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "models/embedding-001"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection_rag: str = "rag_documents"
    qdrant_collection_mem0: str = "mem0_memories"

    # mem0
    mem0_user_collection: str = "mem0_memories"

    # Storage
    storage_backend: Literal["local", "s3"] = "local"
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50

    # S3 (used when storage_backend = "s3")
    s3_bucket: str = ""
    s3_region: str = "ap-southeast-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_session_token: str = ""  # bắt buộc với temporary credentials (ASIA... keys từ STS/SSO)
    s3_endpoint_url: str = ""  # optional: MinIO / custom S3
    s3_prefix: str = "uploads"
    s3_presigned_url_expiry: int = 3600  # seconds

    # Context filter
    max_context_messages: int = 20
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k_results: int = 5

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
