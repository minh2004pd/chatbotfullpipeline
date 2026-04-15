"""Unit tests cho app.exceptions.handlers — Global exception handlers."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.exceptions.handlers import register_exception_handlers


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def app_with_handlers():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/value-error")
    def raise_value_error():
        raise ValueError("Invalid input value")

    @app.get("/file-not-found")
    def raise_file_not_found():
        raise FileNotFoundError("File does not exist")

    @app.get("/generic-error")
    def raise_generic_error():
        raise RuntimeError("Unexpected error")

    @app.get("/success")
    def success():
        return {"status": "ok"}

    return app


@pytest.fixture
def client(app_with_handlers):
    return TestClient(app_with_handlers)


# ── ValueError handler ────────────────────────────────────────────────────────


class TestValueErrorHandler:
    def test_value_error_returns_400(self, client):
        response = client.get("/value-error")
        assert response.status_code == 400

    def test_value_error_returns_detail(self, client):
        response = client.get("/value-error")
        data = response.json()
        assert data["detail"] == "Invalid input value"

    def test_value_error_content_type(self, client):
        response = client.get("/value-error")
        assert "application/json" in response.headers["content-type"]


# ── FileNotFoundError handler ─────────────────────────────────────────────────


class TestFileNotFoundHandler:
    def test_file_not_found_returns_404(self, client):
        response = client.get("/file-not-found")
        assert response.status_code == 404

    def test_file_not_found_returns_detail(self, client):
        response = client.get("/file-not-found")
        data = response.json()
        assert data["detail"] == "File does not exist"


# ── Generic exception handler ─────────────────────────────────────────────────


class TestGenericHandler:
    def test_generic_error_returns_500(self, client):
        response = client.get("/generic-error")
        assert response.status_code == 500

    def test_generic_error_returns_generic_detail(self, client):
        response = client.get("/generic-error")
        data = response.json()
        assert data["detail"] == "Lỗi server. Vui lòng thử lại."

    def test_generic_error_does_not_expose_internal_error(self, client):
        """Generic handler không được expose lỗi nội bộ."""
        response = client.get("/generic-error")
        data = response.json()
        assert "RuntimeError" not in data["detail"]
        assert "Unexpected error" not in data["detail"]


# ── Success path ──────────────────────────────────────────────────────────────


class TestSuccessPath:
    def test_success_endpoint(self, client):
        response = client.get("/success")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ── Handler registration ──────────────────────────────────────────────────────


class TestHandlerRegistration:
    def test_register_handlers_adds_handlers(self):
        app = FastAPI()
        initial_handlers = len(app.exception_handlers)
        register_exception_handlers(app)
        # Should have added 3 handlers (ValueError, FileNotFoundError, Exception)
        assert len(app.exception_handlers) == initial_handlers + 3
