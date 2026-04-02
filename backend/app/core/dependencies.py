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

from fastapi import Depends, Header, HTTPException, status
from google.adk.runners import Runner
from mem0 import Memory
from qdrant_client import QdrantClient

from app.agents.root_agent import get_root_agent
from app.core.config import Settings, get_settings
from app.core.database import get_dynamodb_resource, get_mem0_client, get_qdrant_client
from app.core.storages import StorageBackend, get_storage
from app.repositories.mem0_repo import Mem0Repository
from app.repositories.qdrant_repo import QdrantRepository
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
from app.services.dynamo_session_service import DynamoDBSessionService
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService

# --- Auth ---


async def get_user_id(x_user_id: str = Header(default="default_user")) -> str:
    """Lấy user_id từ header X-User-ID."""
    if not x_user_id or len(x_user_id) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header X-User-ID không hợp lệ.",
        )
    return x_user_id


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


# --- Annotated shorthands (dùng trong endpoint signatures) ---

UserIDDep = Annotated[str, Depends(get_user_id)]
RAGServiceDep = Annotated[RAGService, Depends(get_rag_service)]
MemoryServiceDep = Annotated[MemoryService, Depends(get_memory_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
SessionServiceDep = Annotated[DynamoDBSessionService, Depends(get_session_service_dep)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
