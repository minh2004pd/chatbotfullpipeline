"""Unit tests cho app.services.document_service — Document orchestration."""

from unittest.mock import MagicMock

import pytest

from app.services.document_service import DocumentService


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_rag():
    rag = MagicMock()
    rag.ingest_pdf.return_value = ("doc-id-123", 42)
    rag.list_documents.return_value = [
        {
            "document_id": "doc-1",
            "filename": "test.pdf",
            "user_id": "user-1",
        }
    ]
    rag.count_chunks.return_value = 10
    rag.delete_document.return_value = None
    return rag


@pytest.fixture
def service(mock_rag):
    return DocumentService(rag=mock_rag)


USER_ID = "test-user-123"


# ── upload_pdf ────────────────────────────────────────────────────────────────


class TestUploadPdf:
    def test_upload_pdf_returns_response(self, service):
        response = service.upload_pdf(
            file_bytes=b"pdf content",
            filename="test.pdf",
            user_id=USER_ID,
        )
        assert response.document_id == "doc-id-123"
        assert response.filename == "test.pdf"
        assert response.user_id == USER_ID
        assert response.chunk_count == 42

    def test_upload_pdf_calls_rag(self, service):
        service.upload_pdf(
            file_bytes=b"pdf content",
            filename="test.pdf",
            user_id=USER_ID,
        )
        service.rag.ingest_pdf.assert_called_once_with(
            file_bytes=b"pdf content",
            filename="test.pdf",
            user_id=USER_ID,
        )


# ── list_documents ────────────────────────────────────────────────────────────


class TestListDocuments:
    def test_list_documents_returns_list(self, service):
        docs = service.list_documents(user_id=USER_ID)
        assert len(docs) == 1
        assert docs[0].document_id == "doc-1"
        assert docs[0].filename == "test.pdf"
        assert docs[0].chunk_count == 10

    def test_list_documents_calls_rag(self, service):
        service.list_documents(user_id=USER_ID)
        service.rag.list_documents.assert_called_once_with(user_id=USER_ID)

    def test_list_documents_empty(self, service):
        service.rag.list_documents.return_value = []
        docs = service.list_documents(user_id=USER_ID)
        assert docs == []

    def test_list_documents_counts_chunks_per_doc(self, service):
        service.rag.list_documents.return_value = [
            {"document_id": "doc-1", "filename": "a.pdf", "user_id": USER_ID},
            {"document_id": "doc-2", "filename": "b.pdf", "user_id": USER_ID},
        ]
        service.rag.count_chunks.side_effect = [10, 20]

        docs = service.list_documents(user_id=USER_ID)
        assert docs[0].chunk_count == 10
        assert docs[1].chunk_count == 20
        assert service.rag.count_chunks.call_count == 2


# ── delete_document ───────────────────────────────────────────────────────────


class TestDeleteDocument:
    def test_delete_document_calls_rag(self, service):
        service.delete_document(document_id="doc-123")
        service.rag.delete_document.assert_called_once_with(document_id="doc-123")
