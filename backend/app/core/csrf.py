"""CSRF protection middleware for cookie-based auth.

Uses two complementary patterns:
1. X-Requested-With header — simple pattern, prevents <form> CSRF
2. Double Submit Cookie — X-CSRF-Token header must match csrf_token cookie

Frontend axios is configured to send both headers on all POST/PUT/DELETE requests.
In debug mode (local dev), this middleware is skipped.
"""

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import get_settings

# Safe methods that don't need CSRF protection
SAFE_METHODINGS = {"GET", "HEAD", "OPTIONS"}

# Paths that don't require CSRF (auth endpoints — no token yet)
CSRF_EXEMPT_PATHS = ["/auth/register", "/auth/login", "/auth/google/callback"]


class CSRFMiddleware(BaseHTTPMiddleware):
    """Require CSRF protection for mutating requests when using cookie auth."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()

        # Skip in debug mode (dev environment)
        if settings.debug:
            return await call_next(request)

        # Skip safe methods
        if request.method in SAFE_METHODINGS:
            return await call_next(request)

        # Skip auth endpoints (login/register don't have CSRF token yet)
        path = request.url.path or ""
        if any(path.startswith(f"/api/v1{p}") for p in CSRF_EXEMPT_PATHS):
            return await call_next(request)

        # Check for CSRF protection:
        # Option 1: X-Requested-With header present (simple pattern)
        if request.headers.get("x-requested-with"):
            return await call_next(request)

        # Option 2: Double Submit Cookie — header must match cookie
        csrf_token = request.headers.get("x-csrf-token")
        csrf_cookie = request.cookies.get("csrf_token")
        if csrf_token and csrf_cookie and csrf_token == csrf_cookie:
            return await call_next(request)

        # No CSRF protection → reject

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed.",
        )
