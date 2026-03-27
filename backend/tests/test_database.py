"""Tests for app.database — engine, session factory, init_db, close_db, get_db."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, close_db, get_db, init_db

# ---------------------------------------------------------------------------
# get_db — yields session and commits / rollbacks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_db_yields_session(db_session: AsyncSession) -> None:
    """get_db should yield an AsyncSession instance."""
    assert isinstance(db_session, AsyncSession)


@pytest.mark.asyncio
async def test_get_db_commit_on_success() -> None:
    """get_db should commit on successful iteration."""
    mock_session = AsyncMock(spec=AsyncSession)

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("app.database.async_session_factory", mock_factory):
        gen = get_db()
        session = await gen.__anext__()
        assert session is mock_session
        # Simulate successful end
        import contextlib

        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()
        mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_db_rollback_on_error() -> None:
    """get_db should rollback when an exception occurs."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.commit.side_effect = RuntimeError("commit failed")

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("app.database.async_session_factory", mock_factory):
        gen = get_db()
        _session = await gen.__anext__()
        with pytest.raises(RuntimeError, match="commit failed"):
            await gen.__anext__()
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# init_db — SQLite path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_db_sqlite() -> None:
    """init_db with SQLite should create all tables."""
    mock_conn = AsyncMock()
    mock_begin = AsyncMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_begin.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.database._is_sqlite", True),
        patch("app.database.engine") as mock_engine,
    ):
        mock_engine.begin.return_value = mock_begin
        await init_db()
        mock_conn.run_sync.assert_awaited_once_with(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_init_db_postgres() -> None:
    """init_db with PostgreSQL should create extensions."""
    mock_conn = AsyncMock()
    mock_begin = AsyncMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_begin.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.database._is_sqlite", False),
        patch("app.database.engine") as mock_engine,
    ):
        mock_engine.begin.return_value = mock_begin
        await init_db()
        # Should execute extension creation statements
        assert mock_conn.execute.await_count == 2


# ---------------------------------------------------------------------------
# close_db
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_db() -> None:
    """close_db should dispose the engine."""
    with patch("app.database.engine") as mock_engine:
        mock_engine.dispose = AsyncMock()
        await close_db()
        mock_engine.dispose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


def test_base_is_declarative_base() -> None:
    """Base should be a DeclarativeBase subclass."""
    from sqlalchemy.orm import DeclarativeBase

    assert issubclass(Base, DeclarativeBase)
