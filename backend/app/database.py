"""Async SQLAlchemy engine, session factory, and dependency helpers."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict[str, object] = {
    "echo": settings.LOG_LEVEL == "DEBUG",
}

if not _is_sqlite:
    _engine_kwargs.update(
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,
    )

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an ``AsyncSession`` and ensures cleanup."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Called once during application startup (lifespan).

    For SQLite: creates all tables directly.
    For PostgreSQL: ensures pgvector/pgcrypto extensions exist.
    """
    logger.info("Initialising database connection")

    if _is_sqlite:
        # Import all models so Base.metadata knows about them
        import app.models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("SQLite tables created")
    else:
        async with engine.begin() as conn:
            from sqlalchemy import text

            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        logger.info("PostgreSQL extensions verified")

    logger.info("Database ready")


async def close_db() -> None:
    """Called once during application shutdown (lifespan)."""
    logger.info("Disposing database engine")
    await engine.dispose()
