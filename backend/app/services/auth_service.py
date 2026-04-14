"""Authentication service — register, login, Google OAuth, token refresh."""

from dataclasses import dataclass

import httpx
import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User

logger = structlog.get_logger(__name__)


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    user: User


GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


class AuthService:
    async def register(
        self, email: str, password: str, display_name: str, db: AsyncSession
    ) -> TokenPair:
        email = email.strip().lower()
        display_name = display_name.strip() or email.split("@")[0]

        # Check unique email
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email đã được đăng ký.",
            )

        user = User(
            email=email,
            hashed_password=hash_password(password),
            display_name=display_name,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

        logger.info("user_registered", user_id=user.id, email=email)
        return self._make_token_pair(user)

    async def login(self, email: str, password: str, db: AsyncSession) -> TokenPair:
        email = email.strip().lower()

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if (
            not user
            or not user.hashed_password
            or not verify_password(password, user.hashed_password)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email hoặc mật khẩu không đúng.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tài khoản đã bị vô hiệu hóa.",
            )

        logger.info("user_login", user_id=user.id, email=email)
        return self._make_token_pair(user)

    async def authenticate_google(self, code: str, db: AsyncSession) -> TokenPair:
        settings = get_settings()

        async with httpx.AsyncClient() as client:
            # Exchange code for tokens
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                    "redirect_uri": settings.google_oauth_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                error_detail = token_resp.json().get("error_description", token_resp.text)
                logger.warning(
                    "google_token_exchange_failed",
                    status=token_resp.status_code,
                    error=error_detail,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Google OAuth thất bại: {error_detail}",
                )
            token_data = token_resp.json()

            id_token = token_data.get("id_token")
            if not id_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Không nhận được id_token từ Google.",
                )

            # Decode id_token (Google JWT, RS256 — use Google certs)
            # For simplicity, use the access_token to call userinfo
            access_token = token_data.get("access_token")
            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_resp.raise_for_status()
            userinfo = userinfo_resp.json()

        google_id = userinfo.get("id")
        email = userinfo.get("email", "").lower()
        name = userinfo.get("name", "")
        picture = userinfo.get("picture", "")
        email_verified = userinfo.get("email_verified", False)

        if not email or not google_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Không lấy được thông tin từ Google.",
            )

        # SECURITY: Only link accounts if Google verified the email
        if not email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email chưa được xác minh bởi Google.",
            )

        # Upsert user
        result = await db.execute(
            select(User).where(
                User.oauth_provider == "google",
                User.oauth_provider_id == google_id,
            )
        )
        user = result.scalar_one_or_none()

        if user:
            # Update profile if changed
            if name and name != user.display_name:
                user.display_name = name
            if picture and picture != user.avatar_url:
                user.avatar_url = picture
        else:
            # Check if email already exists (link accounts)
            result = await db.execute(select(User).where(User.email == email))
            existing = result.scalar_one_or_none()
            if existing:
                existing.oauth_provider = "google"
                existing.oauth_provider_id = google_id
                user = existing
            else:
                user = User(
                    email=email,
                    display_name=name or email.split("@")[0],
                    avatar_url=picture,
                    oauth_provider="google",
                    oauth_provider_id=google_id,
                )
                db.add(user)

        await db.flush()
        await db.refresh(user)

        logger.info("user_google_login", user_id=user.id, email=email)
        return self._make_token_pair(user)

    async def refresh_tokens(self, refresh_token: str, db: AsyncSession) -> TokenPair:
        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token không hợp lệ.",
            )

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token không phải refresh token.",
            )

        # Refresh token rotation: verify jti matches stored jti
        token_jti = payload.get("jti")
        user_id = payload["sub"]
        user = await db.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User không tồn tại hoặc đã bị vô hiệu hóa.",
            )

        if not user.refresh_token_jti or user.refresh_token_jti != token_jti:
            # Token reuse detected — invalidate all tokens
            user.refresh_token_jti = None
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token đã được sử dụng. Vui lòng đăng nhập lại.",
            )

        logger.info("token_refreshed", user_id=user.id)
        return self._make_token_pair(user)

    def _make_token_pair(self, user: User) -> TokenPair:
        """Create token pair and store refresh token jti for rotation."""
        access = create_access_token(user.id)
        refresh = create_refresh_token(user.id)

        # Extract jti from the new refresh token and store it
        refresh_payload = decode_token(refresh)
        user.refresh_token_jti = refresh_payload["jti"]

        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            user=user,
        )

    def get_google_auth_url(self, state: str) -> str:
        settings = get_settings()
        params = {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile https://www.googleapis.com/auth/drive.readonly",
            "access_type": "offline",
            "prompt": "select_account",
            "state": state,
        }
        from urllib.parse import urlencode

        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
