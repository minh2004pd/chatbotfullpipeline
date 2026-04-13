"""Document endpoints: upload PDF, list, delete."""

import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.dependencies import DocumentServiceDep, SettingsDep, UserIDDep, WikiServiceDep
from app.core.indexing_status import get_wiki_status, set_wiki_status
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    IndexingStatusResponse,
    WikiNormalizeResponse,
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
    wiki_service: WikiServiceDep = None,
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

    result = service.upload_pdf(file_bytes=file_bytes, filename=file.filename, user_id=user_id)

    # Fire-and-forget: tổng hợp wiki từ tài liệu vừa upload (background, không block response)
    if settings.wiki_enabled:
        set_wiki_status(user_id, result.document_id, "processing")
        full_text = service.rag.extract_text(file_bytes)
        asyncio.create_task(
            wiki_service.update_wiki_from_document(
                user_id=user_id,
                document_id=result.document_id,
                filename=file.filename,
                full_text=full_text,  # không truncate — wiki service tự chunk
            )
        )

    return result


@router.get("/{document_id}/status", response_model=IndexingStatusResponse)
async def get_indexing_status(
    document_id: str,
    user_id: UserIDDep,
    settings: SettingsDep,
) -> IndexingStatusResponse:
    """Trả về trạng thái RAG + Wiki indexing của một document.

    RAG luôn là 'done' khi upload response đã được trả về (synchronous).
    Wiki có thể là 'processing' | 'done' | 'error' | 'disabled'.
    """
    if not settings.wiki_enabled:
        wiki = "disabled"
    else:
        # None = không tìm thấy entry (server restart hoặc đã expire) → coi như done
        wiki = get_wiki_status(user_id, document_id) or "done"

    return IndexingStatusResponse(document_id=document_id, rag="done", wiki=wiki)


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
    settings: SettingsDep,
    wiki_service: WikiServiceDep,
) -> DocumentDeleteResponse:
    """Xóa tài liệu và tất cả chunks trong Qdrant."""
    service.delete_document(document_id=document_id)

    # Fire-and-forget: dọn dẹp wiki pages liên quan đến tài liệu bị xóa
    if settings.wiki_enabled:
        asyncio.create_task(
            wiki_service.remove_source_from_wiki(
                user_id=user_id,
                source_id=document_id,
            )
        )

    return DocumentDeleteResponse(document_id=document_id)


@router.post("/wiki/normalize", response_model=WikiNormalizeResponse)
async def normalize_wiki_slugs(
    user_id: UserIDDep,
    settings: SettingsDep,
    wiki_service: WikiServiceDep,
) -> WikiNormalizeResponse:
    """Migration one-time: chuẩn hóa tên file wiki về [a-z0-9].

    Rename "Adam.md" → "adam.md", merge "long-context.md" + "longcontext.md" → "longcontext.md".
    Gọi 1 lần sau khi upgrade để dọn sạch các file cũ.
    """
    if not settings.wiki_enabled:
        return WikiNormalizeResponse(renamed=0, merged=0, skipped=0)
    stats = wiki_service.normalize_page_filenames(user_id=user_id)
    return WikiNormalizeResponse(**stats)
