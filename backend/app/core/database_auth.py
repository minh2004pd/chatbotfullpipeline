"""Async SQLAlchemy engine and session for PostgreSQL auth database."""

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.user import Base

logger = structlog.get_logger(__name__)

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_size=5,
            max_overflow=5,
            pool_timeout=30,
            pool_recycle=300,  # 5 minutes — tránh RDS connection stale
            pool_pre_ping=True,  # quan trọng cho RDS — test connection trước khi dùng
        )
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async database session."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create tables if they don't exist, then run migrations."""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrations: add columns that create_all can't handle
        await _run_migrations(conn)
    logger.info("postgres_tables_ready")


async def _run_migrations(conn) -> None:
    """Add columns to existing tables. Safe to re-run — IF NOT EXISTS pattern."""
    migrations = [
        # Added refresh_token_jti for token rotation
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS refresh_token_jti VARCHAR(64)",
    ]
    for sql in migrations:
        try:
            await conn.execute(text(sql))
        except Exception as e:
            logger.warning("migration_skipped", sql=sql, error=str(e))
