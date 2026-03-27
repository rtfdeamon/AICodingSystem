"""Alembic environment configuration for async SQLAlchemy migrations.

This module is executed by ``alembic`` whenever a migration command is run
(``alembic revision``, ``alembic upgrade``, etc.).  It reads the database URL
from :pymod:`app.config` so there is a single source of truth.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.database import Base

# Import all models so that Base.metadata is fully populated
import app.models  # noqa: F401

# ── Alembic Config object ──────────────────────────────────────────
config = context.config

# Interpret the config file for Python logging (if present)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The MetaData object that Alembic will inspect for autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    """Return the database URL from application settings."""
    return settings.DATABASE_URL


# ── Offline mode (generate SQL script) ─────────────────────────────
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an ``Engine``.
    Calls to ``context.execute()`` emit the given string to the script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (connect to DB) ────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    """Configure the Alembic context with an existing connection and run."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations inside an async context."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine."""
    asyncio.run(run_async_migrations())


# ── Entrypoint ──────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
