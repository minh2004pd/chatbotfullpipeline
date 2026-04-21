# Authentication System

## Overview
> Cập nhật lần cuối: 2026-04-21

MemRAG Chatbot implements a full-featured authentication system supporting:
- **Email/Password** registration and login
- **Google OAuth 2.0** with account linking
- **JWT-based** session management with refresh token rotation
- **HTTP-cookie** token delivery (httponly, secure, samesite=lax)

All authentication endpoints live under `/api/v1/auth/*`.

---

## Architecture

```
┌─────────────┐
│  Frontend   │  React SPA (cookies stored in browser)
└──────┬──────┘
       │ HTTPS
       ▼
┌─────────────────────────────────────────────┐
│  FastAPI  (/api/v1/auth/*)                  │
│  ├─ /register     → create user + JWTs      │
│  ├─ /login        → verify password + JWTs  │
│  ├─ /logout       → revoke refresh token     │
│  ├─ /refresh      → rotate tokens            │
│  ├─ /me           → get current user         │
│  ├─ /google       → get Google OAuth URL     │
│  └─ /google/callback → OAuth exchange        │
└──────────────┬──────────────────────────────┘
               │
    ┌──────────┼──────────────┐
    ▼          ▼              ▼
 PostgreSQL  JWT (stateless)  Google APIs
 (users)     (access+refresh) (OAuth STS)
```

---

## User Model

**Table:** `users` (PostgreSQL)

| Column | Type | Description |
|--------|------|-------------|
| `id` | `UUID (string)` | Primary key, auto-generated |
| `email` | `String(255)` | Unique, indexed |
| `hashed_password` | `String(255)` | bcrypt hash (nullable for OAuth-only users) |
| `display_name` | `String(255)` | User's display name |
| `avatar_url` | `String(1024)` | Profile picture URL |
| `oauth_provider` | `String(50)` | e.g. `"google"` (nullable) |
| `oauth_provider_id` | `String(255)` | Provider's user ID (nullable) |
| `refresh_token_jti` | `String(64)` | Current valid refresh token JTI (rotation) |
| `is_active` | `Boolean` | Account active flag |
| `created_at` | `DateTime` | Creation timestamp |
| `updated_at` | `DateTime` | Last update timestamp |

**Source:** `backend/app/models/user.py`

---

## Authentication Flow

### 1. Email/Password Registration

```
POST /api/v1/auth/register
Body: { "email": "user@example.com", "password": "min6chars", "display_name": "John" }
```

**Steps:**
1. Validate password length ≥ 6 characters
2. Check email uniqueness (case-insensitive)
3. Hash password with bcrypt
4. Create `User` record in PostgreSQL
5. Generate access + refresh token pair
6. Store refresh token JTI in DB
7. Set httponly cookies (`access_token`, `refresh_token`)
8. Return `TokenResponse`

### 2. Email/Password Login

```
POST /api/v1/auth/login
Body: { "email": "user@example.com", "password": "secret" }
```

**Steps:**
1. Lookup user by email
2. Verify password with bcrypt
3. Check `is_active` flag
4. Generate token pair, store refresh JTI
5. Set cookies, return `TokenResponse`

### 3. Google OAuth Flow

#### Step 1: Get Authorization URL

```
GET /api/v1/auth/google
```

Returns Google OAuth URL with scopes:
- `openid`
- `email`
- `profile`
- `https://www.googleapis.com/auth/drive.readonly`

#### Step 2: User Authorizes on Google

User is redirected to Google consent screen.

#### Step 3: Callback (GET or POST)

```
GET  /api/v1/auth/google/callback?code=<auth_code>
POST /api/v1/auth/google/callback
Body: { "code": "<auth_code>" }
```

**Steps:**
1. Exchange `code` for tokens via Google STS
2. Fetch user info from Google (`email`, `name`, `picture`, `id`)
3. **Account Linking Logic:**
   - If `oauth_provider_id` matches existing user → update profile
   - If `email` matches existing user → link OAuth to that account
   - Otherwise → create new user with OAuth credentials
4. Verify `email_verified` from Google (reject if false)
5. Generate token pair, set cookies

### 4. Token Refresh (Rotation-Based)

```
POST /api/v1/auth/refresh
```

**Refresh Token Rotation:**
- Each refresh returns a **new** access + refresh token pair
- Each refresh token has a unique `jti` (JWT ID)
- Server stores only the **current valid** `jti` in `users.refresh_token_jti`
- If a refresh token is reused (replay attack detection):
  - All tokens are invalidated
  - User must re-authenticate

**Security:** Prevents token replay attacks — if an attacker steals a refresh token, using it will invalidate the legitimate user's session.

### 5. Get Current User

```
GET /api/v1/auth/me
Cookie: access_token=<jwt>
```

Returns user profile. Requires valid `access_token` cookie.

### 6. Logout

```
POST /api/v1/auth/logout
Cookie: access_token=<jwt>
```

**Steps:**
1. Decode `access_token` to get `user_id`
2. Clear `refresh_token_jti` in DB (revokes refresh capability)
3. Delete both cookies

---

## JWT Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `JWT_SECRET_KEY` | *(required)* | HMAC secret for signing tokens |
| `JWT_ALGORITHM` | `HS256` | Signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |

**JWT Payload (Access Token):**
```json
{
  "sub": "<user_id>",
  "type": "access",
  "exp": 1712345678
}
```

**JWT Payload (Refresh Token):**
```json
{
  "sub": "<user_id>",
  "type": "refresh",
  "jti": "a1b2c3d4e5f6...",
  "exp": 1712345678
}
```

---

## Cookie Security

| Attribute | Value | Purpose |
|-----------|-------|---------|
| `httponly` | `true` | Prevents JavaScript access (XSS protection) |
| `secure` | `!DEBUG` | Only sent over HTTPS in production |
| `samesite` | `lax` | CSRF protection |
| `path` | `/` | Available across entire site |

---

## Integration with Chat API

The chat API supports **two** authentication methods:

### Method 1: `X-User-ID` Header (Legacy/Dev)

```
POST /api/v1/chat/stream
Headers: { "X-User-ID": "user-uuid-here" }
```

Used for testing and development. No JWT required.

### Method 2: JWT Cookie (Production)

```
POST /api/v1/chat/stream
Cookies: { "access_token": "<jwt>" }
```

The `access_token` is decoded to extract `user_id` (`sub` claim).

---

## Database Setup

```python
# backend/app/core/database_auth.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Uses DATABASE_URL from settings (async PostgreSQL)
engine = create_async_engine(settings.database_url)
session_factory = async_sessionmaker(engine)
```

Tables are auto-created on startup:
```python
await conn.run_sync(Base.metadata.create_all)
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Async PostgreSQL connection string |
| `JWT_SECRET_KEY` | Yes | Secret for JWT signing |
| `JWT_ALGORITHM` | No | Default: `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default: `30` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | No | Default: `7` |
| `GOOGLE_OAUTH_CLIENT_ID` | For OAuth | Google Cloud project client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | For OAuth | Google Cloud project client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | For OAuth | Callback URL (must match Google Console) |

---

## API Endpoints Summary

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| `POST` | `/api/v1/auth/register` | No | Create account |
| `POST` | `/api/v1/auth/login` | No | Email/password login |
| `POST` | `/api/v1/auth/logout` | Yes (cookie) | Revoke session |
| `POST` | `/api/v1/auth/refresh` | Yes (refresh cookie) | Rotate tokens |
| `GET` | `/api/v1/auth/me` | Yes (cookie) | Get current user |
| `GET` | `/api/v1/auth/google` | No | Get Google OAuth URL |
| `GET` | `/api/v1/auth/google/callback` | No | Google OAuth callback (redirect) |
| `POST` | `/api/v1/auth/google/callback` | No | Google OAuth callback (API) |

---

## Security Considerations

1. **Password Hashing:** bcrypt via `passlib` with automatic salt
2. **Refresh Token Rotation:** Prevents token replay attacks
3. **Email Verification:** Google OAuth requires `email_verified=true`
4. **Account Linking:** Only links accounts if Google verified the email
5. **Cookie Flags:** httponly + secure + samesite for XSS/CSRF protection
6. **Input Validation:** Email format enforced via Pydantic `EmailStr`

---

## Testing

Tests use dependency injection to mock database sessions:

```python
# backend/tests/conftest.py
from app.core.database_auth import get_db

@pytest.fixture
def mock_db():
    """Return a fake User so auth passes in debug mode."""
    # ... mock implementation
```

Override auth database in tests:
```python
app.dependency_overrides[get_db] = lambda: mock_session
```

---

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/api/v1/auth.py` | FastAPI router, endpoints |
| `backend/app/services/auth_service.py` | Business logic (register, login, OAuth, refresh) |
| `backend/app/models/user.py` | SQLAlchemy User model |
| `backend/app/core/database_auth.py` | Async DB engine, session factory |
| `backend/app/core/security.py` | JWT + bcrypt utilities |
