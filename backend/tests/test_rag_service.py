"""Tests cho RAG service và utilities — test trực tiếp service, không qua HTTP."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import get_settings
from app.core.storages import StorageBackend
from app.repositories.mem0_repo import Mem0Repository
from app.repositories.qdrant_repo import QdrantRepository
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService

# --- Fixtures ---


@pytest.fixture
def mock_qdrant_repo():
    repo = MagicMock(spec=QdrantRepository)
    repo.upsert_chunks.return_value = 2
    repo.search.return_value = []
    repo.list_documents.return_value = []
    repo.count_chunks.return_value = 0
    return repo


@pytest.fixture
def mock_mem0_repo():
    repo = MagicMock(spec=Mem0Repository)
    repo.search_memory.return_value = []
    repo.get_all_memories.return_value = []
    repo.add_memory.return_value = []
    return repo


@pytest.fixture
def mock_storage() -> MagicMock:
    storage = MagicMock(spec=StorageBackend)
    storage.save.return_value = "user1/doc-xyz/test.pdf"
    return storage


@pytest.fixture
def rag_service(mock_qdrant_repo, mock_storage):
    return RAGService(qdrant_repo=mock_qdrant_repo, settings=get_settings(), storage=mock_storage)


@pytest.fixture
def memory_service(mock_mem0_repo):
    return MemoryService(repo=mock_mem0_repo)


# --- RAGService tests ---


def test_ingest_pdf_success(rag_service, mock_qdrant_repo, mock_storage, sample_pdf_bytes):
    with (
        patch(
            "app.services.rag_service.extract_pdf_text",
            return_value="Nội dung PDF test",
        ),
        patch("app.services.rag_service.chunk_text", return_value=["chunk 1", "chunk 2"]),
        patch(
            "app.services.rag_service.get_embeddings_batch",
            return_value=[[0.1] * 768] * 2,
        ),
        patch("app.services.rag_service._new_id", return_value="doc-xyz"),
    ):
        document_id, chunk_count = rag_service.ingest_pdf(
            file_bytes=sample_pdf_bytes, filename="test.pdf", user_id="user1"
        )

    assert document_id == "doc-xyz"
    assert chunk_count == 2
    mock_storage.save.assert_called_once_with(
        sample_pdf_bytes, user_id="user1", document_id="doc-xyz", filename="test.pdf"
    )
    mock_qdrant_repo.upsert_chunks.assert_called_once()


def test_ingest_invalid_pdf_raises(rag_service):
    with pytest.raises(ValueError, match="PDF"):
        rag_service.ingest_pdf(file_bytes=b"Not a PDF", filename="fake.pdf", user_id="user1")


def test_ingest_pdf_too_large_raises(mock_qdrant_repo, mock_storage, sample_pdf_bytes):
    settings = MagicMock()
    settings.max_upload_size_bytes = 5
    settings.max_upload_size_mb = 0
    service = RAGService(qdrant_repo=mock_qdrant_repo, settings=settings, storage=mock_storage)

    with pytest.raises(ValueError, match="quá lớn"):
        service.ingest_pdf(file_bytes=sample_pdf_bytes, filename="test.pdf", user_id="user1")


def test_search_returns_results(rag_service, mock_qdrant_repo):
    mock_qdrant_repo.search.return_value = [
        {
            "text": "Nội dung liên quan",
            "document_id": "doc-1",
            "filename": "report.pdf",
            "score": 0.92,
        }
    ]
    with patch("app.services.rag_service.get_query_embedding", return_value=tuple([0.1] * 768)):
        results = rag_service.search(query="câu hỏi test", user_id="user1")

    assert len(results) == 1
    assert results[0]["score"] == 0.92
    mock_qdrant_repo.search.assert_called_once()


def test_list_documents(rag_service, mock_qdrant_repo):
    mock_qdrant_repo.list_documents.return_value = [
        {"document_id": "doc-1", "filename": "myfile.pdf", "user_id": "user1"}
    ]
    docs = rag_service.list_documents(user_id="user1")
    assert len(docs) == 1
    assert docs[0]["document_id"] == "doc-1"


def test_delete_document(rag_service, mock_qdrant_repo):
    rag_service.delete_document(document_id="doc-123")
    mock_qdrant_repo.delete_document.assert_called_once_with(document_id="doc-123")


# --- MemoryService tests ---


def test_memory_search_returns_items(memory_service, mock_mem0_repo):
    mock_mem0_repo.search_memory.return_value = [
        {"id": "m1", "memory": "User thích Python", "score": 0.9}
    ]
    results = memory_service.search(query="Python", user_id="user1", limit=5)
    assert len(results) == 1
    assert results[0].memory == "User thích Python"
    assert results[0].id == "m1"


def test_memory_search_empty(memory_service):
    results = memory_service.search(query="xyz", user_id="user1")
    assert results == []


def test_memory_delete(memory_service, mock_mem0_repo):
    memory_service.delete(memory_id="mem-99")
    mock_mem0_repo.delete_memory.assert_called_once_with(memory_id="mem-99")


def test_memory_delete_all(memory_service, mock_mem0_repo):
    memory_service.delete_all(user_id="user1")
    mock_mem0_repo.delete_all_user_memories.assert_called_once_with(user_id="user1")


# --- Utility tests ---


def test_validate_pdf_valid():
    from app.utils.file_utils import validate_pdf

    assert validate_pdf(b"%PDF-1.4 content")


def test_validate_pdf_invalid():
    from app.utils.file_utils import validate_pdf

    assert not validate_pdf(b"Not a PDF")


def test_chunk_text_splits_correctly():
    from app.utils.file_utils import chunk_text

    text = "Đây là một đoạn văn bản. " * 100
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
    assert len(chunks) > 1
