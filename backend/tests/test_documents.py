"""Tests cho document endpoints."""

import io
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient

pytestmark = pytest.mark.usefixtures("mock_qdrant_client")


@pytest.mark.asyncio
async def test_upload_pdf_success(
    client: AsyncClient, sample_pdf_bytes, mock_qdrant_client
):
    from app.core.storages import StorageBackend

    mock_storage = MagicMock(spec=StorageBackend)

    with (
        patch(
            "app.services.rag_service.extract_pdf_text",
            return_value="Nội dung PDF test",
        ),
        patch(
            "app.services.rag_service.chunk_text",
            return_value=["chunk 1", "chunk 2", "chunk 3"],
        ),
        patch(
            "app.services.rag_service.get_embeddings_batch",
            return_value=[[0.1] * 768] * 3,
        ),
        patch("app.services.rag_service._new_id", return_value="doc-123"),
        patch("app.core.storages.get_storage", return_value=mock_storage),
    ):
        response = await client.post(
            "/api/v1/documents/upload",
            files={
                "file": ("test.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["document_id"] == "doc-123"
    assert data["filename"] == "test.pdf"
    assert data["chunk_count"] == 3
    mock_qdrant_client.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_upload_non_pdf_rejected(client: AsyncClient):
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.txt", io.BytesIO(b"Not a PDF"), "text/plain")},
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_documents_empty(client: AsyncClient):
    response = await client.get("/api/v1/documents")
    assert response.status_code == 200
    assert response.json() == {"documents": [], "total": 0}


@pytest.mark.asyncio
async def test_list_documents_with_data(client: AsyncClient, mock_qdrant_client):
    mock_point = MagicMock()
    mock_point.payload = {
        "document_id": "doc-abc",
        "filename": "report.pdf",
        "user_id": "test_user",
    }
    mock_qdrant_client.scroll.return_value = ([mock_point], None)
    mock_qdrant_client.count.return_value = MagicMock(count=5)

    response = await client.get("/api/v1/documents")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["documents"][0]["document_id"] == "doc-abc"
    assert data["documents"][0]["chunk_count"] == 5


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient, mock_qdrant_client):
    response = await client.delete("/api/v1/documents/doc-123")
    assert response.status_code == 200
    assert response.json()["document_id"] == "doc-123"
    mock_qdrant_client.delete.assert_called_once()
