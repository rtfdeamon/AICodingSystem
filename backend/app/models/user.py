"""User ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow

if TYPE_CHECKING:
    from app.models.project import Project


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        primary_key=True,
        default=generate_uuid,
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Nullable to support OAuth-only accounts."
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="owner",
        doc="One of: owner, developer, pm_lead, ai_agent.",
    )
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # OAuth fields
    github_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    oauth_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships (back-populates defined in related models)
    projects: Mapped[list[Project]] = relationship(  # noqa: F821
        "Project", back_populates="creator", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} role={self.role}>"
