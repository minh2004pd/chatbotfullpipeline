"""Document Service: orchestrate PDF upload flow."""

from datetime import datetime

import structlog

from app.schemas.document import DocumentInfo, DocumentUploadResponse
from app.services.rag_service import RAGService

logger = structlog.get_logger(__name__)


class DocumentService:
    def __init__(self, rag: RAGService):
        self.rag = rag

    def upload_pdf(self, file_bytes: bytes, filename: str, user_id: str) -> DocumentUploadResponse:
        document_id, chunk_count = self.rag.ingest_pdf(
            file_bytes=file_bytes,
            filename=filename,
            user_id=user_id,
        )
        return DocumentUploadResponse(
            document_id=document_id,
            filename=filename,
            user_id=user_id,
            chunk_count=chunk_count,
        )

    def list_documents(self, user_id: str) -> list[DocumentInfo]:
        docs = self.rag.list_documents(user_id=user_id)
        return [
            DocumentInfo(
                document_id=d["document_id"],
                filename=d["filename"],
                user_id=d["user_id"],
                chunk_count=self.rag.count_chunks(d["document_id"]),
                uploaded_at=d.get("uploaded_at", datetime.utcnow()),
            )
            for d in docs
        ]

    def delete_document(self, document_id: str) -> None:
        self.rag.delete_document(document_id=document_id)
