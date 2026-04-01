"""
StorageBackend Protocol — interface chung cho tất cả storage backends.

Để thêm backend mới:
1. Tạo file `{name}_storage.py` trong folder này
2. Implement `StorageBackend` Protocol
3. Đăng ký trong `factory.py`
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Interface chung cho tất cả storage backends."""

    def save(self, file_bytes: bytes, user_id: str, document_id: str, filename: str) -> str:
        """Lưu file và trả về storage key.

        Key format: ``{user_id}/{document_id}/{filename}``
        — dễ list tất cả files của một user, hoặc xóa theo document.
        """
        ...

    def delete(self, key: str) -> None:
        """Xóa file theo key."""
        ...

    def get_url(self, key: str) -> str:
        """Trả về URL / path có thể truy cập file."""
        ...
