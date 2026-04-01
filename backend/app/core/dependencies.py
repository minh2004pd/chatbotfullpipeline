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

  get_runner() [lru_cache]
  get_session_service() [lru_cache]
  get_settings() [lru_cache]
       └── get_chat_service()
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from google.adk.runners import Runner, InMemorySessionService
from mem0 import Memory
from qdrant_client import QdrantClient

from app.agents.root_agent import get_runner, get_session_service
from app.core.config import Settings, get_settings
from app.core.database import get_mem0_client, get_qdrant_client
from app.core.storages import StorageBackend, get_storage
from app.repositories.mem0_repo import Mem0Repository
from app.repositories.qdrant_repo import QdrantRepository
from app.services.chat_service import ChatService
from app.services.document_service import DocumentService
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


# --- Infrastructure (lru_cache singletons exposed as Depends) ---


def get_qdrant_client_dep(
    client: QdrantClient = Depends(get_qdrant_client),
) -> QdrantClient:
    return client


def get_mem0_client_dep(
    client: Memory = Depends(get_mem0_client),
) -> Memory:
    return client


def get_runner_dep(
    runner: Runner = Depends(get_runner),
) -> Runner:
    return runner


def get_session_service_dep(
    session_service: InMemorySessionService = Depends(get_session_service),
) -> InMemorySessionService:
    return session_service


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
    session_service: InMemorySessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> ChatService:
    return ChatService(runner=runner, session_service=session_service, settings=settings)


# --- Annotated shorthands (dùng trong endpoint signatures) ---

UserIDDep = Annotated[str, Depends(get_user_id)]
RAGServiceDep = Annotated[RAGService, Depends(get_rag_service)]
MemoryServiceDep = Annotated[MemoryService, Depends(get_memory_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
