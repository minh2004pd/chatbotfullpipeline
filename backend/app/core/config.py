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
    wiki_max_text_chars: int = 16384  # truncate text trước khi gửi LLM
    wiki_max_entities_per_source: int = 10  # số entities tối đa extract per source
    wiki_max_topics_per_source: int = 3  # số topics tối đa extract per source (không tính entities)
    wiki_max_related_pages_per_source: int = (
        5  # số related pages tối đa được re-synthesize per ingest
    )

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

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
