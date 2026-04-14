from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
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
    gemini_embedding_model: str = "gemini-embedding-001"

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

    # DynamoDB (session persistence)
    dynamodb_table_name: str = "memrag_sessions"
    dynamodb_region: str = "ap-southeast-2"
    dynamodb_endpoint_url: str = ""  # empty = real AWS; "http://localhost:8001" cho local dev
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Soniox (realtime transcription)
    soniox_api_key: str = ""
    soniox_model: str = "stt-rt-v4"
    soniox_target_lang: str = "vi"
    soniox_ws_url: str = "wss://stt-rt.soniox.com/transcribe-websocket"

    # Meetings (DynamoDB table + Qdrant collection)
    meetings_table_name: str = "memrag-meetings"
    qdrant_collection_meetings: str = "meetings"

    # Wiki
    wiki_base_dir: str = "./wiki"
    wiki_enabled: bool = True
    wiki_chunk_size: int = 16384  # chunk size cho extraction (split paper dài)
    wiki_max_entities_per_source: int = 20  # số entities tối đa extract per source
    wiki_max_topics_per_source: int = 5  # số topics tối đa extract per source (không tính entities)
    wiki_max_related_pages_per_source: int = (
        5  # số related pages tối đa được re-synthesize per ingest
    )
    wiki_max_parallel_extractions: int = 5  # concurrent _extract_topics calls
    wiki_max_parallel_synthesis: int = 5  # concurrent _synthesize_page calls
    wiki_synthesis_max_text_per_page: int = 32768  # max merged text per page (2x chunk_size)

    # PostgreSQL (auth)
    database_url: str = "postgresql+asyncpg://memrag:memrag@localhost:5432/memrag"
    database_host: str = ""  # RDS endpoint — set by Terraform in production
    db_username: str = "memrag"  # RDS master username
    db_password: str = ""  # RDS password — from SSM Parameter Store

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Google OAuth
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""

    # Context filter & summarization
    max_context_messages: int = 20  # simple truncation fallback
    summary_threshold: int = 22  # = max_context_messages + 2, đóng gap hoàn toàn
    summary_keep_recent: int = 10  # giữ N messages gần nhất sau khi tóm tắt
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k_results: int = 5
    score_threshold: float = 0.6  # loại bỏ RAG results có relevance score thấp hơn
    memory_search_limit: int = 15  # search nhiều hơn rồi rerank, trả về top-7

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        # CRITICAL: JWT secret must be set in any non-debug environment
        if not self.debug and not self.jwt_secret_key:
            raise ValueError(
                "JWT_SECRET_KEY is required in production. Set it to a random 32+ character string."
            )
        return self

    @model_validator(mode="after")
    def resolve_database_url(self) -> "Settings":
        """Build database_url from DATABASE_HOST + DB_PASSWORD in production."""
        if self.database_host and self.db_password:
            self.database_url = (
                f"postgresql+asyncpg://{self.db_username}:{self.db_password}"
                f"@{self.database_host}:5432/{self.db_username}"
            )
        return self

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
