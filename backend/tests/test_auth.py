"""Tests for auth endpoints: register, login, logout, refresh, me, google."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.user import User

pytestmark = pytest.mark.usefixtures("mock_qdrant_client", "mock_mem0_client")


def _make_fake_user(
    user_id: str = "test_user",
    email: str = "test@test.com",
    display_name: str = "Test",
    hashed_password: str | None = None,
    refresh_token_jti: str | None = None,
) -> MagicMock:
    fake = MagicMock(spec=User)
    fake.id = user_id
    fake.email = email
    fake.display_name = display_name
    fake.avatar_url = ""
    fake.oauth_provider = None
    fake.oauth_provider_id = None
    fake.hashed_password = hashed_password
    fake.refresh_token_jti = refresh_token_jti
    fake.is_active = True
    return fake


def _make_execute_result(user=None):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=user)
    result.scalar_one = MagicMock(return_value=user)
    return result


# ── Register ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_success(client, app):
    """Register returns 201 with tokens in cookies."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@test.com", "password": "secret123", "display_name": "New User"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "new@test.com"
    assert data["display_name"] == "New User"
    # Cookies should be set
    assert "access_token" in resp.cookies


@pytest.mark.asyncio
async def test_register_short_password(client, app):
    """Register with password < 6 chars returns 400."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@test.com", "password": "12345", "display_name": "User"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_duplicate_email(client, app):
    """Register with existing email returns 409."""
    from app.core.database_auth import get_db

    fake_user = _make_fake_user(email="exists@test.com")

    async def override_get_db_with_user():
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_execute_result(user=fake_user))
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        yield db

    app.dependency_overrides[get_db] = override_get_db_with_user

    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "exists@test.com", "password": "secret123"},
    )
    assert resp.status_code == 409


# ── Login ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_success(client, app):
    """Login with correct credentials returns 200 with tokens."""
    from app.core.database_auth import get_db

    hashed = hash_password("secret123")
    fake_user = _make_fake_user(email="user@test.com", hashed_password=hashed)

    async def override_get_db_login():
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_execute_result(user=fake_user))
        db.get = AsyncMock(return_value=fake_user)
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        yield db

    app.dependency_overrides[get_db] = override_get_db_login

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "user@test.com"
    assert "access_token" in resp.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(client, app):
    """Login with wrong password returns 401."""
    from app.core.database_auth import get_db

    hashed = hash_password("correct_password")
    fake_user = _make_fake_user(email="user@test.com", hashed_password=hashed)

    async def override_get_db_login():
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_execute_result(user=fake_user))
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        yield db

    app.dependency_overrides[get_db] = override_get_db_login

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@test.com", "password": "wrong_password"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client, app):
    """Login with non-existent email returns 401."""
    from app.core.database_auth import get_db

    async def override_get_db_empty():
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_execute_result(user=None))
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        yield db

    app.dependency_overrides[get_db] = override_get_db_empty

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.com", "password": "secret123"},
    )
    assert resp.status_code == 401


# ── /me ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_authenticated(client, app):
    """GET /me with valid JWT cookie returns user info."""
    from app.core.database_auth import get_db

    fake_user = _make_fake_user(user_id="abc-123", email="me@test.com")
    token = create_access_token("abc-123")

    async def override_get_db_me():
        db = AsyncMock()
        db.get = AsyncMock(return_value=fake_user)
        db.execute = AsyncMock(return_value=_make_execute_result(user=fake_user))
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        yield db

    app.dependency_overrides[get_db] = override_get_db_me

    resp = await client.get(
        "/api/v1/auth/me",
        cookies={"access_token": token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "me@test.com"


@pytest.mark.asyncio
async def test_me_unauthenticated(client):
    """GET /me without token returns 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


# ── Logout ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_logout(client, app):
    """POST /logout clears cookies."""
    from app.core.database_auth import get_db

    fake_user = _make_fake_user(user_id="abc-123")
    token = create_access_token("abc-123")

    async def override_get_db_logout():
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_make_execute_result(user=fake_user))
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        yield db

    app.dependency_overrides[get_db] = override_get_db_logout

    resp = await client.post(
        "/api/v1/auth/logout",
        cookies={"access_token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Đã đăng xuất."


# ── Refresh ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_success(client, app):
    """POST /refresh with valid refresh token returns new token pair."""
    from app.core.database_auth import get_db

    # Create a refresh token and extract its jti
    refresh = create_refresh_token("abc-123")
    from app.core.security import decode_token

    payload = decode_token(refresh)
    jti = payload["jti"]

    fake_user = _make_fake_user(user_id="abc-123", refresh_token_jti=jti)

    async def override_get_db_refresh():
        db = AsyncMock()
        db.get = AsyncMock(return_value=fake_user)
        db.execute = AsyncMock(return_value=_make_execute_result(user=fake_user))
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        yield db

    app.dependency_overrides[get_db] = override_get_db_refresh

    resp = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": refresh},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "abc-123"


@pytest.mark.asyncio
async def test_refresh_no_token(client):
    """POST /refresh without refresh token returns 401."""
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_reuse_detected(client, app):
    """POST /refresh with reused (wrong jti) refresh token returns 401."""
    from app.core.database_auth import get_db

    refresh = create_refresh_token("abc-123")

    # User's stored jti doesn't match → reuse detected
    fake_user = _make_fake_user(user_id="abc-123", refresh_token_jti="different-jti")

    async def override_get_db_refresh():
        db = AsyncMock()
        db.get = AsyncMock(return_value=fake_user)
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        yield db

    app.dependency_overrides[get_db] = override_get_db_refresh

    resp = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": refresh},
    )
    assert resp.status_code == 401
    assert "đã được sử dụng" in resp.json()["detail"]


# ── Google OAuth ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_auth_url(client, app):
    """GET /auth/google returns auth URL when configured."""
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.google_oauth_client_id:
        pytest.skip("Google OAuth not configured")

    resp = await client.get("/api/v1/auth/google")
    assert resp.status_code == 200
    assert "accounts.google.com" in resp.json()["url"]


@pytest.mark.asyncio
async def test_google_auth_url_not_configured(client, app):
    """GET /auth/google returns 501 when not configured."""
    from app.core.config import get_settings

    # Override settings to have empty client_id
    original = get_settings()
    original.google_oauth_client_id = ""

    resp = await client.get("/api/v1/auth/google")
    assert resp.status_code == 501

    # Restore
    original.google_oauth_client_id = get_settings().google_oauth_client_id
