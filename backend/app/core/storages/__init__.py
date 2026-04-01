"""
Storage package — public API.

Usage:
    from app.core.storages import StorageBackend, get_storage

Để thêm backend mới, tạo file `{name}_storage.py` rồi đăng ký trong `get_storage()`.
"""

from functools import lru_cache

import structlog

from app.core.storages.base_storage import StorageBackend
from app.core.storages.local_storage import LocalStorage
from app.core.storages.s3_storage import S3Storage

logger = structlog.get_logger(__name__)

__all__ = ["StorageBackend", "LocalStorage", "S3Storage", "get_storage"]


@lru_cache
def get_storage() -> StorageBackend:
    """Khởi tạo và cache storage backend theo settings."""
    from app.core.config import get_settings  # tránh circular import

    settings = get_settings()
    backend = settings.storage_backend.lower()

    if backend == "s3":
        if not settings.s3_bucket:
            raise ValueError("S3_BUCKET phải được cấu hình khi STORAGE_BACKEND=s3.")
        storage: StorageBackend = S3Storage(
            bucket=settings.s3_bucket,
            prefix=settings.s3_prefix,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            session_token=settings.s3_session_token,
            endpoint_url=settings.s3_endpoint_url,
            presigned_url_expiry=settings.s3_presigned_url_expiry,
        )
        logger.info("storage_backend_initialized", backend="s3", bucket=settings.s3_bucket)
    else:
        storage = LocalStorage(upload_dir=settings.upload_dir)
        logger.info("storage_backend_initialized", backend="local", dir=settings.upload_dir)

    return storage
