from datetime import datetime

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    user_id: str
    chunk_count: int
    message: str = "Document ingested successfully"
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    user_id: str
    chunk_count: int
    uploaded_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]
    total: int


class DocumentDeleteResponse(BaseModel):
    document_id: str
    message: str = "Document deleted successfully"


class IndexingStatusResponse(BaseModel):
    document_id: str
    rag: str  # luôn là "done" (RAG là synchronous, xong trước khi response trả về)
    wiki: str  # "processing" | "done" | "error" | "disabled"


class WikiNormalizeResponse(BaseModel):
    renamed: int
    merged: int
    skipped: int
    message: str = "Wiki slug normalization complete"
