"""
Pytest fixtures dùng chung.

Dùng app.dependency_overrides thay vì unittest.mock.patch —
sạch hơn, không cần biết module path của import.
"""

# MUST set env vars BEFORE importing app modules — app/main.py calls create_app() at module level
import os

os.environ["DEBUG"] = "true"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only-32chars"

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import get_mem0_client, get_qdrant_client
from app.core.database_auth import get_db
from app.core.dependencies import get_dynamo_session_service, get_runner
from app.main import create_app


@pytest.fixture
def app():
    # Clear cached settings so it re-reads from env
    get_settings.cache_clear()

    instance = create_app()

    # Mock get_db (PostgreSQL) — return a no-op async session for tests
    mock_db = AsyncMock()

    def _make_fake_user(user_id: str = "test_user"):
        """Create a fake User object for auth queries."""
        from app.models.user import User

        fake = MagicMock(spec=User)
        fake.id = user_id
        fake.is_active = True
        fake.email = f"{user_id}@test.com"
        fake.display_name = user_id
        fake.avatar_url = ""
        fake.oauth_provider = None
        fake.oauth_provider_id = None
        fake.refresh_token_jti = None
        return fake

    def mock_db_get(user_model_cls, user_id):
        """Return a fake User so auth passes in debug mode."""
        from app.models.user import User

        if user_model_cls is User:
            return _make_fake_user(user_id)
        return None

    def _make_execute_result(user=None):
        """Factory for execute() result mock."""
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=user)
        result.scalar_one = MagicMock(return_value=user)
        return result

    def mock_execute(*args, **kwargs):
        """Return empty result for execute calls (auth uses db.get now)."""
        return _make_execute_result(user=None)

    async def mock_refresh(obj):
        """Simulate SQLAlchemy refresh — assign defaults on new objects."""
        import uuid

        if hasattr(obj, "id") and obj.id is None:
            obj.id = str(uuid.uuid4())
        # Apply column defaults that would normally be set on flush
        if hasattr(obj, "avatar_url") and obj.avatar_url is None:
            obj.avatar_url = ""
        if hasattr(obj, "display_name") and obj.display_name is None:
            obj.display_name = ""

    mock_db.get = AsyncMock(side_effect=mock_db_get)
    mock_db.execute = AsyncMock(side_effect=mock_execute)
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=mock_refresh)
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    async def override_get_db():
        yield mock_db

    instance.dependency_overrides[get_db] = override_get_db

    yield instance
    # Dọn overrides sau mỗi test
    instance.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-ID": "test_user",
            "X-Requested-With": "XMLHttpRequest",  # CSRF protection
        },
    ) as ac:
        yield ac


# --- Mock Qdrant ---


@pytest.fixture
def mock_qdrant_client(app):
    client = MagicMock()
    client.get_collections.return_value = MagicMock(collections=[])
    client.search.return_value = []
    client.upsert.return_value = None
    client.scroll.return_value = ([], None)
    client.delete.return_value = None
    client.count.return_value = MagicMock(count=0)
    client.create_collection.return_value = None

    app.dependency_overrides[get_qdrant_client] = lambda: client
    return client


# --- Mock mem0 ---


@pytest.fixture
def mock_mem0_client(app):
    client = MagicMock()
    client.add.return_value = {"results": []}
    client.search.return_value = {"results": []}
    client.get_all.return_value = {"results": []}
    client.delete.return_value = None
    client.delete_all.return_value = None

    app.dependency_overrides[get_mem0_client] = lambda: client
    return client


# --- Mock DynamoDB Session Service ---


@pytest.fixture
def mock_dynamo_session_service(app):
    """Mock DynamoDBSessionService — dùng cho chat tests và session tests."""
    service = MagicMock()
    service.get_session = AsyncMock(return_value=None)
    service.create_session = AsyncMock(return_value=MagicMock(id="test-session-id"))
    service.append_event = AsyncMock(side_effect=lambda session, event: event)
    service.delete_session = AsyncMock(return_value=None)
    service.list_sessions_with_metadata = MagicMock(return_value=[])
    service.get_session_messages = MagicMock(return_value=None)

    app.dependency_overrides[get_dynamo_session_service] = lambda: service
    return service


# --- Mock ADK Runner ---


@pytest.fixture
def mock_runner(app, mock_dynamo_session_service):
    runner = MagicMock()

    async def fake_run_async(**kwargs):
        event = MagicMock()
        event.is_final_response.return_value = True
        part = MagicMock()
        part.text = "Xin chào! Tôi có thể giúp gì cho bạn?"
        part.function_response = None
        event.content = MagicMock()
        event.content.parts = [part]
        yield event

    runner.run_async = fake_run_async

    app.dependency_overrides[get_runner] = lambda: runner
    return runner, mock_dynamo_session_service


# --- Sample PDF bytes ---


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 100 700 Td "
        b"(Hello World) Tj ET\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000274 00000 n \n"
        b"0000000369 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n441\n%%EOF"
    )
