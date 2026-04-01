"""RAG Service: xử lý ingestion và search tài liệu."""

import structlog

from app.core.config import Settings
from app.core.storages import StorageBackend
from app.repositories.qdrant_repo import QdrantRepository
from app.utils.file_utils import extract_pdf_text, chunk_text, validate_pdf
from app.utils.gemini_utils import get_embeddings_batch, get_query_embedding

logger = structlog.get_logger(__name__)


class RAGService:
    def __init__(
        self,
        qdrant_repo: QdrantRepository,
        settings: Settings,
        storage: StorageBackend,
    ) -> None:
        self.repo = qdrant_repo
        self.settings = settings
        self.storage = storage

    def ingest_pdf(
        self, file_bytes: bytes, filename: str, user_id: str
    ) -> tuple[str, int]:
        """
        Ingest PDF vào Qdrant.

        Returns:
            (document_id, chunk_count)
        """
        if not validate_pdf(file_bytes):
            raise ValueError("File không phải định dạng PDF hợp lệ.")

        if len(file_bytes) > self.settings.max_upload_size_bytes:
            raise ValueError(
                f"File quá lớn. Tối đa {self.settings.max_upload_size_mb}MB."
            )

        document_id = _new_id()
        self.storage.save(file_bytes, user_id=user_id, document_id=document_id, filename=filename)

        text = extract_pdf_text(file_bytes)
        if not text.strip():
            raise ValueError("PDF không có nội dung text có thể đọc được.")

        chunks = chunk_text(
            text,
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )
        embeddings = get_embeddings_batch(chunks)

        chunk_count = self.repo.upsert_chunks(
            chunks=chunks,
            embeddings=embeddings,
            document_id=document_id,
            filename=filename,
            user_id=user_id,
        )

        logger.info("rag_ingest_done", document_id=document_id, chunks=chunk_count)
        return document_id, chunk_count

    def search(self, query: str, user_id: str | None = None) -> list[dict]:
        """Tìm kiếm tài liệu liên quan."""
        query_vector = get_query_embedding(query)
        return self.repo.search(
            query_vector=query_vector,
            user_id=user_id,
            top_k=self.settings.top_k_results,
        )

    def list_documents(self, user_id: str) -> list[dict]:
        return self.repo.list_documents(user_id=user_id)

    def delete_document(self, document_id: str) -> None:
        self.repo.delete_document(document_id=document_id)

    def count_chunks(self, document_id: str) -> int:
        return self.repo.count_chunks(document_id=document_id)


# ── Helpers ──────────────────────────────────────────────────


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())
