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

import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from google.adk.runners import Runner
from mem0 import Memory
from qdrant_client import QdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.root_agent import get_root_agent
from app.core.config import Settings, get_settings
from app.core.database import get_dynamodb_resource, get_mem0_client, get_qdrant_client
from app.core.database_auth import get_db
from app.core.security import decode_token
from app.core.storages import StorageBackend, get_storage
from app.models.user import User
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
) -> User:
    """Extract user from JWT cookie. Fallback to X-User-ID header (dev mode)."""
    # Try JWT cookie first
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = decode_token(token)
            user_id = payload["sub"]
            user = await db.get(User, user_id)
            if user and user.is_active:
                return user
        except Exception:
            pass  # fall through to header
        # JWT present but user not found → raise 401 (don't silently fallback to default_user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User không tồn tại hoặc đã bị khóa. Vui lòng đăng nhập lại.",
        )

    # Backward compat: X-User-ID header (dev mode / API access without auth)
    x_user_id = request.headers.get("x-user-id")
    if x_user_id and x_user_id != "default_user":
        from sqlalchemy import select as sa_select

        result = await db.execute(sa_select(User).where(User.id == x_user_id))
        user = result.scalar_one_or_none()
        if user and user.is_active:
            return user

    # No JWT, no valid X-User-ID → return pseudo-user for unauthenticated access
    pseudo_id = x_user_id if x_user_id else "default_user"
    # Validate length to prevent oversized IDs
    if len(pseudo_id) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-ID header quá dài (tối đa 100 ký tự).",
        )
    return User(
        id=pseudo_id,
        email=pseudo_id,
        display_name=pseudo_id,
    )


async def get_current_user_id(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> str:
    """Return user_id as string — drop-in replacement for old get_user_id."""
    user = await get_current_user(request, db)
    return str(user.id) if user.id else "default_user"


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
        )
    # Local filesystem
    return WikiRepository(base_dir=settings.wiki_base_dir)


def get_wiki_service(
    settings: Settings = Depends(get_settings),
) -> WikiService:
    return WikiService(repo=get_wiki_repo(), settings=settings)


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
