"""Document endpoints: upload PDF, list, delete."""

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.dependencies import DocumentServiceDep, SettingsDep, UserIDDep
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentUploadResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    user_id: UserIDDep = None,
    service: DocumentServiceDep = None,
    settings: SettingsDep = None,
) -> DocumentUploadResponse:
    """Upload PDF để ingest vào RAG."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Chỉ chấp nhận file PDF."
        )

    file_bytes = await file.read()

    if len(file_bytes) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File quá lớn. Tối đa {settings.max_upload_size_mb}MB.",
        )

    return service.upload_pdf(file_bytes=file_bytes, filename=file.filename, user_id=user_id)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    user_id: UserIDDep,
    service: DocumentServiceDep,
) -> DocumentListResponse:
    """Lấy danh sách tài liệu đã upload của user."""
    documents = service.list_documents(user_id=user_id)
    return DocumentListResponse(documents=documents, total=len(documents))


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    user_id: UserIDDep,
    service: DocumentServiceDep,
) -> DocumentDeleteResponse:
    """Xóa tài liệu và tất cả chunks trong Qdrant."""
    service.delete_document(document_id=document_id)
    return DocumentDeleteResponse(document_id=document_id)
