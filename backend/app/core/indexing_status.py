"""Module-level in-memory store để track trạng thái wiki indexing.

Lý do dùng in-memory thay vì DB:
- Status là ephemeral: chỉ cần trong quá trình indexing (~30s-2min)
- Tự động expire sau 10 phút
- Server restart → status mất → frontend timeout → treat as done (document đã index xong rồi)
"""

import time
from dataclasses import dataclass, field

_EXPIRE_SECS = 600  # auto-expire sau 10 phút

@dataclass
class _WikiEntry:
    status: str  # "processing" | "done" | "error"
    created_at: float = field(default_factory=time.monotonic)


# {user_id: {document_id: _WikiEntry}}
_store: dict[str, dict[str, _WikiEntry]] = {}


def set_wiki_status(user_id: str, document_id: str, status: str) -> None:
    """Ghi trạng thái wiki indexing cho một document."""
    if user_id not in _store:
        _store[user_id] = {}
    _store[user_id][document_id] = _WikiEntry(status=status)


def get_wiki_status(user_id: str, document_id: str) -> str | None:
    """Trả về status string hoặc None nếu không tìm thấy / đã expire."""
    _cleanup()
    entry = _store.get(user_id, {}).get(document_id)
    return entry.status if entry is not None else None


def _cleanup() -> None:
    """Xóa các entry đã expire để tránh memory leak."""
    now = time.monotonic()
    for uid in list(_store):
        for did in list(_store.get(uid, {})):
            if now - _store[uid][did].created_at > _EXPIRE_SECS:
                del _store[uid][did]
        if not _store.get(uid):
            _store.pop(uid, None)
