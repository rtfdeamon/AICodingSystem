"""CodeEmbedding ORM model for storing vector-indexed code chunks."""

from __future__ import annotations

import uuid
from datetime import datetime

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    from sqlalchemy import Text as Vector  # fallback for SQLite

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow


class CodeEmbedding(Base):
    """Stores a semantic code chunk with its embedding vector.

    Each row represents a parsed chunk of source code from a project
    repository, together with its 1536-dimensional embedding for
    similarity search.
    """

    __tablename__ = "code_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        primary_key=True,
        default=generate_uuid,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    symbol_name: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # pgvector column — 1536 dimensions for text-embedding-3-small
    embedding = mapped_column(Vector(1536), nullable=False)

    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow, nullable=False
    )

    __table_args__ = (
        Index(
            "ix_code_embeddings_project_file",
            "project_id",
            "file_path",
        ),
        Index(
            "ix_code_embeddings_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CodeEmbedding {self.file_path}:{self.chunk_index} ({self.symbol_name or 'chunk'})>"
        )
