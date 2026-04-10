"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import chat, documents, memory, sessions, wiki
from app.api.v1.transcription import meetings_router
from app.api.v1.transcription import router as transcription_router
from app.core.config import get_settings
from app.core.database import ensure_collections, ensure_dynamo_table, ensure_meetings_table
from app.core.logger import setup_logging
from app.exceptions.handlers import register_exception_handlers

# Khởi tạo logging
setup_logging()

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    settings = get_settings()
    logger.info("app_starting", name=settings.app_name, version=settings.app_version)

    try:
        await ensure_collections()
        logger.info("qdrant_collections_ready")
    except Exception as e:
        logger.warning("qdrant_init_failed", error=str(e))

    try:
        await ensure_dynamo_table()
    except Exception as e:
        logger.warning("dynamo_init_failed", error=str(e))

    try:
        await ensure_meetings_table()
    except Exception as e:
        logger.warning("dynamo_meetings_init_failed", error=str(e))

    yield

    logger.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Multimodal chatbot with RAG and long-term memory",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(memory.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(transcription_router, prefix="/api/v1")
    app.include_router(meetings_router, prefix="/api/v1")
    app.include_router(wiki.router, prefix="/api/v1")

    # Exception handlers
    register_exception_handlers(app)

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
