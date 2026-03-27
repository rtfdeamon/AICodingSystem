"""Cross-database compatible column types.

Provides UUID and JSON types that work with both PostgreSQL and SQLite.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, TypeDecorator
from sqlalchemy.engine.interfaces import Dialect


class DBUUID(TypeDecorator[uuid.UUID]):
    """Platform-independent UUID type.

    Uses PostgreSQL's UUID type when available, otherwise stores as CHAR(36).
    """

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(uuid.UUID(value))

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


def generate_uuid() -> uuid.UUID:
    """Generate a new UUID4 for use as default."""
    return uuid.uuid4()


def utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)
