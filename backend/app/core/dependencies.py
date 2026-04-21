"""
FastAPI Dependency Injection wiring.

Sơ đồ dependency graph:
  get_qdrant_client() [lru_cache]
       └── get_qdrant_repo()
              └── get_rag_service()
                     └── get_document_service()

  get_mem0_client() [lru_cache]
       └── get_mem0_repo()
              └── get_memory_service()

  get_dynamo_session_service() [lru_cache]  ← DynamoDB-backed, thay InMemorySessionService
  get_runner() [lru_cache]
  get_settings() [lru_cache]
       └── get_chat_service()
"""

from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from google.adk.runners import Runner
from mem0 import Memory
from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.root_agent import get_root_agent
from app.core.cache import CacheService, get_cache_service
from app.core.config import Settings, get_settings
from app.core.database import get_dynamodb_resource, get_mem0_client, get_qdrant_client
from app.core.database_auth import get_db
from app.core.security import decode_token
from app.core.storages import StorageBackend, get_storage
from app.models.user import User

_USER_CACHE_FIELDS = (
    "id",
    "email",
    "display_name",
    "avatar_url",
    "is_active",
    "oauth_provider",
    "oauth_provider_id",
)


def _user_to_cache(user: User) -> dict:
    return {f: getattr(user, f, None) for f in _USER_CACHE_FIELDS}


def _user_from_cache(data: dict) -> User:
    u = User()
    for field in _USER_CACHE_FIELDS:
        if field in data:
            setattr(u, field, data[field])
    return u
from app.repositories.mem0_repo import Mem0Repository
from app.repositories.qdrant_repo import QdrantRepository
from app.repositories.wiki_repo import WikiRepository
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.services.dynamo_session_service import DynamoDBSessionService
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService
from app.services.wiki_service import WikiService

# --- Auth ---


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Extract user from JWT cookie.

    Auth flow (production-safe):
    1. Try JWT cookie → decode → lookup DB → return User
    2. If JWT expired → raise 401 (triggers frontend refresh interceptor)
    3. If no JWT and DEBUG=true → fall back to X-User-ID header (dev only)
    4. If no JWT and DEBUG=false → raise 401 (no anonymous access in production)
    """
    cache = get_cache_service()

    # Try JWT cookie first
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = decode_token(token)
            user_id = payload["sub"]

            cache_key = f"memrag:auth:user:{user_id}"
            cached_data = await cache.get_json(cache_key)
            if cached_data and cached_data.get("is_active"):
                return _user_from_cache(cached_data)

            user = await db.get(User, user_id)
            if user and user.is_active:
                await cache.set_json(cache_key, _user_to_cache(user), ttl=settings.redis_user_ttl)
                return user
        except jwt.ExpiredSignatureError:
            # Token expired — return 401 so frontend refresh interceptor kicks in
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
            )
        except Exception:
            pass  # JWT present but invalid — fall through to header/dev check

        # JWT present but user not found → raise 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User không tồn tại hoặc đã bị khóa. Vui lòng đăng nhập lại.",
        )

    # No JWT — check if dev mode allows X-User-ID header
    if settings.debug:
        x_user_id = request.headers.get("x-user-id")
        if x_user_id and x_user_id != "default_user":
            # Validate length
            if len(x_user_id) > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-User-ID header quá dài (tối đa 100 ký tự).",
                )
            user = await db.get(User, x_user_id)
            if user and user.is_active:
                return user

    # No valid auth → raise 401 (no pseudo-user)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Yêu cầu đăng nhập.",
    )


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User | None:
    """Optional auth — returns User if authenticated, None otherwise.

    For endpoints that work with or without login (e.g., public health checks).
    """
    try:
        return await get_current_user(request, db, settings)
    except HTTPException:
        return None


async def get_current_user_id(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> str:
    """Return user_id as string — drop-in replacement for old get_user_id.
    Raises 401 if not authenticated."""
    user = await get_current_user(request, db, settings)
    return str(user.id)


# --- Infrastructure (lru_cache singletons) ---


@lru_cache
def get_dynamo_session_service() -> DynamoDBSessionService:
    settings = get_settings()
    resource = get_dynamodb_resource()
    table = resource.Table(settings.dynamodb_table_name)
    return DynamoDBSessionService(table=table, app_name="memrag")


@lru_cache
def get_runner() -> Runner:
    return Runner(
        agent=get_root_agent(),
        app_name="memrag",
        session_service=get_dynamo_session_service(),
    )


def get_qdrant_client_dep(
    client: QdrantClient = Depends(get_qdrant_client),
) -> QdrantClient:
    return client


def get_mem0_client_dep(
    client: Memory = Depends(get_mem0_client),
) -> Memory:
    return client


def get_storage_dep(
    storage: StorageBackend = Depends(get_storage),
) -> StorageBackend:
    return storage


# --- Repositories ---


def get_qdrant_repo(
    client: QdrantClient = Depends(get_qdrant_client),
) -> QdrantRepository:
    return QdrantRepository(client)


def get_mem0_repo(
    client: Memory = Depends(get_mem0_client),
) -> Mem0Repository:
    return Mem0Repository(client)


# --- Services ---


def get_rag_service(
    qdrant_repo: QdrantRepository = Depends(get_qdrant_repo),
    settings: Settings = Depends(get_settings),
    storage: StorageBackend = Depends(get_storage),
) -> RAGService:
    return RAGService(qdrant_repo=qdrant_repo, settings=settings, storage=storage)


def get_memory_service(
    repo: Mem0Repository = Depends(get_mem0_repo),
) -> MemoryService:
    return MemoryService(repo=repo)


def get_document_service(
    rag: RAGService = Depends(get_rag_service),
) -> DocumentService:
    return DocumentService(rag=rag)


def get_chat_service(
    runner: Runner = Depends(get_runner),
    session_service: DynamoDBSessionService = Depends(get_dynamo_session_service),
    settings: Settings = Depends(get_settings),
) -> ChatService:
    return ChatService(runner=runner, session_service=session_service, settings=settings)


def get_session_service_dep(
    service: DynamoDBSessionService = Depends(get_dynamo_session_service),
) -> DynamoDBSessionService:
    return service


@lru_cache
def get_wiki_repo() -> WikiRepository:
    """Singleton WikiRepository — tự chọn local hoặc S3 backend."""
    settings = get_settings()
    cache = get_cache_service()
    if settings.storage_backend == "s3":
        import boto3

        s3_kwargs: dict = {"region_name": settings.s3_region}
        if settings.s3_endpoint_url:
            s3_kwargs["endpoint_url"] = settings.s3_endpoint_url
        if settings.s3_access_key_id:
            s3_kwargs["aws_access_key_id"] = settings.s3_access_key_id
            s3_kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
        if settings.s3_session_token:
            s3_kwargs["aws_session_token"] = settings.s3_session_token
        s3_client = boto3.client("s3", **s3_kwargs)
        return WikiRepository(
            s3_client=s3_client,
            s3_bucket=settings.s3_bucket,
            s3_prefix="wiki",
            cache=cache,
            wiki_ttl=settings.redis_wiki_ttl,
        )
    # Local filesystem
    return WikiRepository(
        base_dir=settings.wiki_base_dir,
        cache=cache,
        wiki_ttl=settings.redis_wiki_ttl,
    )


def get_wiki_service(
    settings: Settings = Depends(get_settings),
) -> WikiService:
    return WikiService(repo=get_wiki_repo(), settings=settings)


def get_cache_service_dep() -> CacheService:
    return get_cache_service()


# --- Annotated shorthands (dùng trong endpoint signatures) ---

UserIDDep = Annotated[str, Depends(get_current_user_id)]
RAGServiceDep = Annotated[RAGService, Depends(get_rag_service)]
MemoryServiceDep = Annotated[MemoryService, Depends(get_memory_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
SessionServiceDep = Annotated[DynamoDBSessionService, Depends(get_session_service_dep)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
WikiServiceDep = Annotated[WikiService, Depends(get_wiki_service)]
WikiRepoDep = Annotated[WikiRepository, Depends(get_wiki_repo)]
CacheDep = Annotated[CacheService, Depends(get_cache_service_dep)]
