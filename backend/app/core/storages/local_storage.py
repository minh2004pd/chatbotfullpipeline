"""Local filesystem storage backend."""

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def _build_key(user_id: str, document_id: str, filename: str) -> str:
    """Key format: ``{user_id}/{document_id}/{filename}``."""
    safe_name = Path(filename).name  # prevent path traversal
    return f"{user_id}/{document_id}/{safe_name}"


class LocalStorage:
    """Lưu file trên local filesystem.

    Cấu trúc thư mục::

        {upload_dir}/
        └── {user_id}/
            └── {document_id}/
                └── {filename}
    """

    def __init__(self, upload_dir: str) -> None:
        self._root = Path(upload_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, file_bytes: bytes, user_id: str, document_id: str, filename: str) -> str:
        key = _build_key(user_id, document_id, filename)
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_bytes)
        logger.info("storage_local_saved", key=key, bytes=len(file_bytes))
        return key

    def delete(self, key: str) -> None:
        path = self._root / key
        if path.exists():
            path.unlink()
            # Dọn thư mục rỗng: {document_id}/ rồi {user_id}/
            try:
                path.parent.rmdir()
                path.parent.parent.rmdir()
            except OSError:
                pass  # còn files khác trong thư mục — bỏ qua
            logger.info("storage_local_deleted", key=key)

    def get_url(self, key: str) -> str:
        return str(self._root / key)
