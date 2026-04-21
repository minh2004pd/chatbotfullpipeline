"""Unit tests cho app.repositories.qdrant_repo — Qdrant vector DB operations."""

from unittest.mock import MagicMock

import pytest

from app.repositories.qdrant_repo import QdrantRepository

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_qdrant_client():
    client = MagicMock()
    client.upsert.return_value = None
    client.query_points.return_value = MagicMock(points=[])
    client.scroll.return_value = ([], None)
    client.delete.return_value = None
    client.count.return_value = MagicMock(count=0)
    return client


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock get_settings() để tránh đọc .env thật."""
    from unittest.mock import patch

    settings = MagicMock()
    settings.qdrant_collection_rag = "test_collection"
    with patch("app.repositories.qdrant_repo.get_settings", return_value=settings):
        yield settings


@pytest.fixture
def repo(mock_qdrant_client, mock_settings):
    return QdrantRepository(client=mock_qdrant_client)


USER_ID = "test-user-123"
DOC_ID = "doc-abc-123"
FILENAME = "test.pdf"


# ── upsert_chunks ─────────────────────────────────────────────────────────────


class TestUpsertChunks:
    def test_upsert_chunks_returns_count(self, repo):
        chunks = ["chunk1", "chunk2", "chunk3"]
        embeddings = [[0.1] * 768, [0.2] * 768, [0.3] * 768]

        count = repo.upsert_chunks(
            chunks=chunks,
            embeddings=embeddings,
            document_id=DOC_ID,
            filename=FILENAME,
            user_id=USER_ID,
        )
        assert count == 3

    def test_upsert_chunks_calls_client(self, repo):
        chunks = ["text"]
        embeddings = [[0.1] * 768]

        repo.upsert_chunks(
            chunks=chunks,
            embeddings=embeddings,
            document_id=DOC_ID,
            filename=FILENAME,
            user_id=USER_ID,
        )
        repo.client.upsert.assert_called_once()

    def test_upsert_chunks_correct_collection(self, repo):
        chunks = ["text"]
        embeddings = [[0.1] * 768]

        repo.upsert_chunks(
            chunks=chunks,
            embeddings=embeddings,
            document_id=DOC_ID,
            filename=FILENAME,
            user_id=USER_ID,
        )
        call_kwargs = repo.client.upsert.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_collection"

    def test_upsert_chunks_creates_points(self, repo):
        chunks = ["chunk1", "chunk2"]
        embeddings = [[0.1] * 768, [0.2] * 768]

        repo.upsert_chunks(
            chunks=chunks,
            embeddings=embeddings,
            document_id=DOC_ID,
            filename=FILENAME,
            user_id=USER_ID,
        )
        call_kwargs = repo.client.upsert.call_args.kwargs
        points = call_kwargs["points"]
        assert len(points) == 2

        # Check first point
        assert points[0].payload["text"] == "chunk1"
        assert points[0].payload["document_id"] == DOC_ID
        assert points[0].payload["filename"] == FILENAME
        assert points[0].payload["user_id"] == USER_ID
        assert points[0].payload["chunk_index"] == 0

        # Check second point
        assert points[1].payload["text"] == "chunk2"
        assert points[1].payload["chunk_index"] == 1

    def test_upsert_chunks_empty(self, repo):
        count = repo.upsert_chunks(
            chunks=[],
            embeddings=[],
            document_id=DOC_ID,
            filename=FILENAME,
            user_id=USER_ID,
        )
        assert count == 0
        repo.client.upsert.assert_called_once()
        call_kwargs = repo.client.upsert.call_args.kwargs
        assert call_kwargs["points"] == []

    def test_upsert_chunks_preserves_order(self, repo):
        chunks = ["first", "second", "third"]
        embeddings = [[0.1] * 768, [0.2] * 768, [0.3] * 768]

        repo.upsert_chunks(
            chunks=chunks,
            embeddings=embeddings,
            document_id=DOC_ID,
            filename=FILENAME,
            user_id=USER_ID,
        )
        call_kwargs = repo.client.upsert.call_args.kwargs
        points = call_kwargs["points"]
        assert points[0].payload["chunk_index"] == 0
        assert points[1].payload["chunk_index"] == 1
        assert points[2].payload["chunk_index"] == 2


# ── search ───────────────────────────────────────────────────────────────────


class TestSearch:
    def test_search_returns_results(self, repo):
        mock_point = MagicMock()
        mock_point.payload = {
            "text": "result text",
            "document_id": DOC_ID,
            "filename": FILENAME,
        }
        mock_point.score = 0.85
        repo.client.query_points.return_value = MagicMock(points=[mock_point])

        results = repo.search(query_vector=[0.1] * 768, user_id=USER_ID)
        assert len(results) == 1
        assert results[0]["text"] == "result text"
        assert results[0]["document_id"] == DOC_ID
        assert results[0]["filename"] == FILENAME
        assert results[0]["score"] == 0.85

    def test_search_empty_results(self, repo):
        repo.client.query_points.return_value = MagicMock(points=[])
        results = repo.search(query_vector=[0.1] * 768, user_id=USER_ID)
        assert results == []

    def test_search_with_user_filter(self, repo):
        repo.search(query_vector=[0.1] * 768, user_id=USER_ID)
        call_kwargs = repo.client.query_points.call_args.kwargs
        assert call_kwargs["query_filter"] is not None

    def test_search_without_user_filter(self, repo):
        repo.search(query_vector=[0.1] * 768, user_id=None)
        call_kwargs = repo.client.query_points.call_args.kwargs
        assert call_kwargs["query_filter"] is None

    def test_search_respects_top_k(self, repo):
        repo.search(query_vector=[0.1] * 768, user_id=USER_ID, top_k=10)
        call_kwargs = repo.client.query_points.call_args.kwargs
        assert call_kwargs["limit"] == 10

    def test_search_respects_score_threshold(self, repo):
        repo.search(
            query_vector=[0.1] * 768,
            user_id=USER_ID,
            score_threshold=0.7,
        )
        call_kwargs = repo.client.query_points.call_args.kwargs
        assert call_kwargs["score_threshold"] == 0.7

    def test_search_default_parameters(self, repo):
        repo.search(query_vector=[0.1] * 768)
        call_kwargs = repo.client.query_points.call_args.kwargs
        assert call_kwargs["limit"] == 5
        assert call_kwargs["score_threshold"] == 0.0
        assert call_kwargs["with_payload"] is True


# ── list_documents ────────────────────────────────────────────────────────────


class TestListDocuments:
    def test_list_documents_empty(self, repo):
        repo.client.scroll.return_value = ([], None)
        docs = repo.list_documents(user_id=USER_ID)
        assert docs == []

    def test_list_documents_returns_unique(self, repo):
        # Same document_id appears multiple times (multiple chunks)
        mock_point1 = MagicMock()
        mock_point1.payload = {
            "document_id": DOC_ID,
            "filename": FILENAME,
            "user_id": USER_ID,
        }
        mock_point2 = MagicMock()
        mock_point2.payload = {
            "document_id": DOC_ID,  # Same document
            "filename": FILENAME,
            "user_id": USER_ID,
        }
        repo.client.scroll.return_value = ([mock_point1, mock_point2], None)

        docs = repo.list_documents(user_id=USER_ID)
        assert len(docs) == 1  # Should be deduplicated

    def test_list_documents_multiple_documents(self, repo):
        mock_point1 = MagicMock()
        mock_point1.payload = {
            "document_id": "doc-1",
            "filename": "file1.pdf",
            "user_id": USER_ID,
        }
        mock_point2 = MagicMock()
        mock_point2.payload = {
            "document_id": "doc-2",
            "filename": "file2.pdf",
            "user_id": USER_ID,
        }
        repo.client.scroll.return_value = ([mock_point1, mock_point2], None)

        docs = repo.list_documents(user_id=USER_ID)
        assert len(docs) == 2
        assert docs[0]["document_id"] == "doc-1"
        assert docs[1]["document_id"] == "doc-2"

    def test_list_documents_filters_by_user(self, repo):
        repo.list_documents(user_id=USER_ID)
        call_kwargs = repo.client.scroll.call_args.kwargs
        assert call_kwargs["scroll_filter"] is not None
        filter_obj = call_kwargs["scroll_filter"]
        assert filter_obj.must[0].key == "user_id"
        assert filter_obj.must[0].match.value == USER_ID

    def test_list_documents_respects_limit(self, repo):
        repo.list_documents(user_id=USER_ID)
        call_kwargs = repo.client.scroll.call_args.kwargs
        assert call_kwargs["limit"] == 1000


# ── delete_document ───────────────────────────────────────────────────────────


class TestDeleteDocument:
    def test_delete_document_calls_client(self, repo):
        repo.delete_document(document_id=DOC_ID)
        repo.client.delete.assert_called_once()

    def test_delete_document_correct_collection(self, repo):
        repo.delete_document(document_id=DOC_ID)
        call_kwargs = repo.client.delete.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_collection"

    def test_delete_document_correct_filter(self, repo):
        repo.delete_document(document_id=DOC_ID)
        call_kwargs = repo.client.delete.call_args.kwargs
        selector = call_kwargs["points_selector"]
        assert selector.filter.must[0].key == "document_id"
        assert selector.filter.must[0].match.value == DOC_ID


# ── count_chunks ──────────────────────────────────────────────────────────────


class TestCountChunks:
    def test_count_chunks_returns_count(self, repo):
        repo.client.count.return_value = MagicMock(count=42)
        count = repo.count_chunks(document_id=DOC_ID)
        assert count == 42

    def test_count_chunks_zero(self, repo):
        repo.client.count.return_value = MagicMock(count=0)
        count = repo.count_chunks(document_id=DOC_ID)
        assert count == 0

    def test_count_chunks_correct_filter(self, repo):
        repo.count_chunks(document_id=DOC_ID)
        call_kwargs = repo.client.count.call_args.kwargs
        filter_obj = call_kwargs["count_filter"]
        assert filter_obj.must[0].key == "document_id"
        assert filter_obj.must[0].match.value == DOC_ID

    def test_count_chunks_exact_true(self, repo):
        repo.count_chunks(document_id=DOC_ID)
        call_kwargs = repo.client.count.call_args.kwargs
        assert call_kwargs["exact"] is True
