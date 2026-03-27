"""Tests for app.redis — init_redis, close_redis, get_redis_pool, get_redis."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.redis import close_redis, get_redis, get_redis_pool, init_redis

# ---------------------------------------------------------------------------
# init_redis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_redis_creates_pool() -> None:
    """init_redis should create a Redis pool and verify connectivity."""
    mock_pool = AsyncMock()
    mock_pool.ping = AsyncMock()

    with patch("app.redis.aioredis.from_url", return_value=mock_pool):
        await init_redis()
        mock_pool.ping.assert_awaited_once()


# ---------------------------------------------------------------------------
# close_redis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_redis_closes_pool() -> None:
    """close_redis should close the pool and set it to None."""
    mock_pool = AsyncMock()
    mock_pool.aclose = AsyncMock()

    with patch("app.redis._pool", mock_pool), patch("app.redis.aioredis"):
        await close_redis()
        mock_pool.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_redis_noop_when_no_pool() -> None:
    """close_redis with no pool should be a no-op."""
    with patch("app.redis._pool", None):
        await close_redis()  # Should not raise


# ---------------------------------------------------------------------------
# get_redis_pool
# ---------------------------------------------------------------------------


def test_get_redis_pool_raises_when_not_initialized() -> None:
    """get_redis_pool should raise RuntimeError if pool is None."""
    with patch("app.redis._pool", None), pytest.raises(
        RuntimeError, match="not been initialised"
    ):
        get_redis_pool()


def test_get_redis_pool_returns_pool() -> None:
    """get_redis_pool should return the pool when initialized."""
    mock_pool = MagicMock()
    with patch("app.redis._pool", mock_pool):
        result = get_redis_pool()
        assert result is mock_pool


# ---------------------------------------------------------------------------
# get_redis (async dependency)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_redis_yields_pool() -> None:
    """get_redis should yield the Redis pool."""
    mock_pool = MagicMock()
    with patch("app.redis._pool", mock_pool):
        gen = get_redis()
        result = await gen.__anext__()
        assert result is mock_pool
