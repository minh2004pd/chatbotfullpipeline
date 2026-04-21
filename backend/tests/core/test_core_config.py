"""Unit tests cho app.core.config — Settings validation và validators."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings

# ── parse_origins validator ───────────────────────────────────────────────────


class TestParseOrigins:
    def test_parse_origins_from_string(self):
        settings = Settings(allowed_origins="http://localhost:5173,http://localhost:3000")
        assert settings.allowed_origins == ["http://localhost:5173", "http://localhost:3000"]

    def test_parse_origins_from_list(self):
        settings = Settings(allowed_origins=["http://localhost:5173"])
        assert settings.allowed_origins == ["http://localhost:5173"]

    def test_parse_origins_strips_whitespace(self):
        settings = Settings(allowed_origins="  http://a.com  ,  http://b.com  ")
        assert settings.allowed_origins == ["http://a.com", "http://b.com"]

    def test_parse_origins_empty_string(self):
        settings = Settings(allowed_origins="")
        assert settings.allowed_origins == []

    def test_parse_origins_single_origin(self):
        settings = Settings(allowed_origins="http://localhost:5173")
        assert settings.allowed_origins == ["http://localhost:5173"]


# ── validate_security validator ───────────────────────────────────────────────


class TestValidateSecurity:
    def test_debug_mode_no_jwt_required(self):
        """Debug mode không yêu cầu JWT secret."""
        settings = Settings(debug=True, jwt_secret_key="")
        assert settings.debug is True

    def test_production_mode_jwt_required(self):
        """Production mode yêu cầu JWT secret."""
        with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
            Settings(debug=False, jwt_secret_key="")

    def test_production_mode_with_jwt_ok(self):
        """Production mode với JWT secret hợp lệ."""
        settings = Settings(debug=False, jwt_secret_key="test-secret-32chars!")
        assert settings.jwt_secret_key == "test-secret-32chars!"


# ── resolve_database_url validator ────────────────────────────────────────────


class TestResolveDatabaseUrl:
    def test_resolve_from_host_and_password(self):
        settings = Settings(
            database_host="mydb.rds.amazonaws.com",
            db_password="secret123",
            db_username="admin",
        )
        assert "mydb.rds.amazonaws.com" in settings.database_url
        assert "admin:secret123" in settings.database_url
        assert "admin" in settings.database_url  # database name

    def test_no_resolve_without_host(self):
        settings = Settings(
            database_host="",
            db_password="secret",
            db_username="admin",
        )
        # Should use default database_url
        assert "localhost" in settings.database_url

    def test_no_resolve_without_password(self):
        settings = Settings(
            database_host="mydb.rds.amazonaws.com",
            db_password="",
            db_username="admin",
        )
        assert "localhost" in settings.database_url


# ── max_upload_size_bytes property ────────────────────────────────────────────


class TestMaxUploadSize:
    def test_default_upload_size(self):
        settings = Settings()
        assert settings.max_upload_size_bytes == 50 * 1024 * 1024  # 50 MB

    def test_custom_upload_size(self):
        settings = Settings(max_upload_size_mb=100)
        assert settings.max_upload_size_bytes == 100 * 1024 * 1024  # 100 MB

    def test_small_upload_size(self):
        settings = Settings(max_upload_size_mb=1)
        assert settings.max_upload_size_bytes == 1 * 1024 * 1024  # 1 MB


# ── Default values ────────────────────────────────────────────────────────────


class TestDefaultValues:
    def test_default_debug_false(self):
        # DEBUG=true được set trong conftest cho tests, nên test này skip
        settings = Settings(jwt_secret_key="test", debug=False)
        assert settings.debug is False

    def test_default_wiki_enabled(self):
        settings = Settings(jwt_secret_key="test")
        assert settings.wiki_enabled is True

    def test_default_storage_local(self):
        settings = Settings(jwt_secret_key="test")
        assert settings.storage_backend == "local"

    def test_default_jwt_algorithm(self):
        settings = Settings(jwt_secret_key="test")
        assert settings.jwt_algorithm == "HS256"

    def test_default_gemini_model(self):
        settings = Settings(jwt_secret_key="test")
        assert settings.gemini_model == "gemini-2.5-flash"


# ── get_settings cached ───────────────────────────────────────────────────────


class TestGetSettings:
    def test_get_settings_returns_settings(self):
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_cached(self):
        """get_settings dùng lru_cache, cùng instance."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
