"""Authentication API — register, login, logout, refresh, Google OAuth."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database_auth import get_db
from app.core.security import decode_token
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    message: str
    user_id: str
    email: str
    display_name: str
    avatar_url: str = ""


class GoogleUrlResponse(BaseModel):
    url: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    avatar_url: str
    oauth_provider: str | None = None


class GoogleCallbackRequest(BaseModel):
    code: str


# ── Helpers ────────────────────────────────────────────────────────────


def _set_token_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        path="/",
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        path="/",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
    )


def _clear_token_cookies(response: Response) -> None:
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")


def _get_current_user_id_from_cookie(request: Request) -> str | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_token(token)
        return payload["sub"]
    except Exception:
        return None


# ── Endpoints ──────────────────────────────────────────────────────────


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    if len(body.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu phải có ít nhất 6 ký tự.",
        )
    auth_service = AuthService()
    token_pair = await auth_service.register(
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        db=db,
    )
    _set_token_cookies(response, token_pair.access_token, token_pair.refresh_token)
    return TokenResponse(
        message="Đăng ký thành công.",
        user_id=str(token_pair.user.id),
        email=token_pair.user.email,
        display_name=token_pair.user.display_name,
        avatar_url=token_pair.user.avatar_url,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    auth_service = AuthService()
    token_pair = await auth_service.login(email=body.email, password=body.password, db=db)
    _set_token_cookies(response, token_pair.access_token, token_pair.refresh_token)
    return TokenResponse(
        message="Đăng nhập thành công.",
        user_id=str(token_pair.user.id),
        email=token_pair.user.email,
        display_name=token_pair.user.display_name,
        avatar_url=token_pair.user.avatar_url,
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    _clear_token_cookies(response)
    return {"message": "Đã đăng xuất."}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không tìm thấy refresh token.",
        )

    auth_service = AuthService()
    token_pair = await auth_service.refresh_tokens(refresh_token=refresh_token, db=db)
    _set_token_cookies(response, token_pair.access_token, token_pair.refresh_token)
    return TokenResponse(
        message="Token đã được làm mới.",
        user_id=str(token_pair.user.id),
        email=token_pair.user.email,
        display_name=token_pair.user.display_name,
        avatar_url=token_pair.user.avatar_url,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(request: Request, db: AsyncSession = Depends(get_db)) -> UserResponse:
    user_id = _get_current_user_id_from_cookie(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa xác thực.",
        )

    from app.models.user import User
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User không tồn tại hoặc đã bị vô hiệu hóa.",
        )

    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        oauth_provider=user.oauth_provider,
    )


@router.get("/google", response_model=GoogleUrlResponse)
async def google_auth() -> GoogleUrlResponse:
    settings = get_settings()
    if not settings.google_oauth_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth chưa được cấu hình.",
        )
    auth_service = AuthService()
    state = secrets.token_urlsafe(32)
    url = auth_service.get_google_auth_url(state)
    return GoogleUrlResponse(url=url)


# ── Endpoints ──────────────────────────────────────────────────────────

# GET callback: supports browser redirect from Google OAuth
@router.get("/google/callback", response_model=TokenResponse)
async def google_callback_get(
    response: Response,
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    auth_service = AuthService()
    token_pair = await auth_service.authenticate_google(code=code, db=db)
    _set_token_cookies(response, token_pair.access_token, token_pair.refresh_token)
    return TokenResponse(
        message="Đăng nhập Google thành công.",
        user_id=str(token_pair.user.id),
        email=token_pair.user.email,
        display_name=token_pair.user.display_name,
        avatar_url=token_pair.user.avatar_url,
    )


# POST callback: supports frontend calling with code in body
@router.post("/google/callback", response_model=TokenResponse)
async def google_callback(
    body: GoogleCallbackRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    auth_service = AuthService()
    token_pair = await auth_service.authenticate_google(code=body.code, db=db)
    _set_token_cookies(response, token_pair.access_token, token_pair.refresh_token)
    return TokenResponse(
        message="Đăng nhập Google thành công.",
        user_id=str(token_pair.user.id),
        email=token_pair.user.email,
        display_name=token_pair.user.display_name,
        avatar_url=token_pair.user.avatar_url,
    )
