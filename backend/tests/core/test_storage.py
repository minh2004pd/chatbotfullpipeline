"""Tests cho StorageBackend implementations."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.storages import LocalStorage, S3Storage, StorageBackend, get_storage

# ── LocalStorage ─────────────────────────────────────────────


@pytest.fixture
def local_storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(upload_dir=str(tmp_path))


def test_local_storage_save(local_storage: LocalStorage, tmp_path: Path):
    key = local_storage.save(
        b"%PDF-test", user_id="user1", document_id="doc-1", filename="test.pdf"
    )
    assert key == "user1/doc-1/test.pdf"
    assert (tmp_path / key).read_bytes() == b"%PDF-test"


def test_local_storage_get_url(local_storage: LocalStorage, tmp_path: Path):
    key = local_storage.save(
        b"%PDF-test", user_id="user1", document_id="doc-1", filename="test.pdf"
    )
    url = local_storage.get_url(key)
    assert str(tmp_path) in url
    assert "user1/doc-1/test.pdf" in url


def test_local_storage_delete(local_storage: LocalStorage, tmp_path: Path):
    key = local_storage.save(
        b"%PDF-test", user_id="user1", document_id="doc-1", filename="test.pdf"
    )
    local_storage.delete(key)
    assert not (tmp_path / key).exists()
    # Thư mục doc-1/ và user1/ phải được dọn sạch
    assert not (tmp_path / "user1" / "doc-1").exists()
    assert not (tmp_path / "user1").exists()


def test_local_storage_delete_nonexistent(local_storage: LocalStorage):
    """Xóa file không tồn tại không raise exception."""
    local_storage.delete("user1/doc-99/ghost.pdf")


def test_local_storage_prevents_path_traversal(local_storage: LocalStorage, tmp_path: Path):
    """Path traversal trong filename phải bị chặn."""
    key = local_storage.save(
        b"%PDF", user_id="user1", document_id="doc-1", filename="../../etc/passwd"
    )
    assert key == "user1/doc-1/passwd"
    assert (tmp_path / key).exists()


# ── S3Storage ────────────────────────────────────────────────


@pytest.fixture
def mock_boto3_client():
    """Mock boto3 S3 client."""
    with patch("boto3.client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        mock_client.generate_presigned_url.return_value = "https://s3.example.com/presigned"
        yield mock_client


@pytest.fixture
def s3_storage(mock_boto3_client) -> S3Storage:
    return S3Storage(
        bucket="test-bucket",
        prefix="uploads",
        region="ap-southeast-1",
    )


def test_s3_storage_save(s3_storage: S3Storage, mock_boto3_client):
    key = s3_storage.save(b"%PDF-test", user_id="user1", document_id="doc-1", filename="test.pdf")
    assert key == "uploads/user1/doc-1/test.pdf"
    mock_boto3_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="uploads/user1/doc-1/test.pdf",
        Body=b"%PDF-test",
        ContentType="application/pdf",
    )


def test_s3_storage_delete(s3_storage: S3Storage, mock_boto3_client):
    s3_storage.delete("uploads/user1/doc-1/test.pdf")
    mock_boto3_client.delete_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="uploads/user1/doc-1/test.pdf",
    )


def test_s3_storage_get_url(s3_storage: S3Storage, mock_boto3_client):
    url = s3_storage.get_url("uploads/user1/doc-1/test.pdf")
    assert url == "https://s3.example.com/presigned"
    mock_boto3_client.generate_presigned_url.assert_called_once()


# ── Factory ───────────────────────────────────────────────────


def test_get_storage_returns_local_by_default():
    from app.core.config import Settings

    settings = Settings(storage_backend="local", upload_dir="/tmp/test_storage")
    with patch("app.core.config.get_settings", return_value=settings):
        get_storage.cache_clear()
        storage = get_storage()
        assert isinstance(storage, LocalStorage)
        get_storage.cache_clear()


def test_get_storage_raises_when_s3_bucket_missing():
    from app.core.config import Settings

    settings = Settings(storage_backend="s3", s3_bucket="")
    with patch("app.core.config.get_settings", return_value=settings):
        get_storage.cache_clear()
        with pytest.raises(ValueError, match="S3_BUCKET"):
            get_storage()
        get_storage.cache_clear()


def test_storage_backend_protocol_compliance(local_storage: LocalStorage):
    """LocalStorage phải implement StorageBackend Protocol."""
    assert isinstance(local_storage, StorageBackend)
