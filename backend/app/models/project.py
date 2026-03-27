"""Project ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        primary_key=True,
        default=generate_uuid,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # GitHub integration
    github_repo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    github_repo_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(128), default="main")

    # Ownership
    created_by: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

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

    # Relationships
    creator: Mapped[User] = relationship(  # noqa: F821
        "User", back_populates="projects", lazy="joined"
    )
    tickets: Mapped[list[Ticket]] = relationship(  # noqa: F821
        "Ticket", back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project {self.slug}>"
