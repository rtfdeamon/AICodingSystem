"""Redis connection pool and dependency helpers using ``redis.asyncio``."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_pool: aioredis.Redis | None = None


async def init_redis() -> None:
    """Create the shared Redis connection pool.  Called during app startup."""
    global _pool  # noqa: PLW0603
    logger.info("Connecting to Redis at %s", settings.REDIS_URL)
    _pool = aioredis.from_url(  # type: ignore[no-untyped-call]
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    # Verify connectivity
    await _pool.ping()
    logger.info("Redis connection pool ready")


async def close_redis() -> None:
    """Gracefully close the Redis connection pool.  Called during app shutdown."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        logger.info("Closing Redis connection pool")
        await _pool.aclose()
        _pool = None


def get_redis_pool() -> aioredis.Redis:
    """Return the current Redis pool (non-async, for internal use)."""
    if _pool is None:
        raise RuntimeError("Redis pool has not been initialised. Call init_redis() first.")
    return _pool


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency that yields the shared Redis connection."""
    yield get_redis_pool()
