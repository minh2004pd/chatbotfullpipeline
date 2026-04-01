"""
Pytest fixtures dùng chung.

Dùng app.dependency_overrides thay vì unittest.mock.patch —
sạch hơn, không cần biết module path của import.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.core.database import get_qdrant_client, get_mem0_client
from app.agents.root_agent import get_runner, get_session_service


@pytest.fixture
def app():
    instance = create_app()
    yield instance
    # Dọn overrides sau mỗi test
    instance.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-User-ID": "test_user"},
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


# --- Mock ADK Runner ---


@pytest.fixture
def mock_runner(app):
    runner = MagicMock()
    session_service = MagicMock()
    session_service.get_session = AsyncMock(return_value=None)
    session_service.create_session = AsyncMock(return_value=MagicMock())

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
    app.dependency_overrides[get_session_service] = lambda: session_service
    return runner, session_service


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
