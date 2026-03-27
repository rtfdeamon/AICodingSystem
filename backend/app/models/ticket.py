"""Ticket ORM model representing a work item on the Kanban board."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow

if TYPE_CHECKING:
    from app.models.comment import Comment
    from app.models.project import Project
    from app.models.ticket_history import TicketHistory
    from app.models.user import User


class Priority(enum.StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class ColumnName(enum.StrEnum):
    BACKLOG = "backlog"
    AI_PLANNING = "ai_planning"
    PLAN_REVIEW = "plan_review"
    AI_CODING = "ai_coding"
    CODE_REVIEW = "code_review"
    STAGING = "staging"
    STAGING_VERIFICATION = "staging_verification"
    PRODUCTION = "production"


class Ticket(Base):
    __tablename__ = "tickets"

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
    ticket_number: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="Auto-incremented per project."
    )

    # Content
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Board state
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="priority_enum", create_constraint=True),
        server_default=Priority.P2.value,
        default=Priority.P2,
        nullable=False,
    )
    column_name: Mapped[ColumnName] = mapped_column(
        Enum(ColumnName, name="column_name_enum", create_constraint=True),
        server_default=ColumnName.BACKLOG.value,
        default=ColumnName.BACKLOG,
        nullable=False,
        index=True,
    )

    # Assignment
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Estimation & organisation
    story_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    labels: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=list)

    # Git integration
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Retry tracking (AI pipeline)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0, doc="Sort order within a column.")

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
    project: Mapped[Project] = relationship(  # noqa: F821
        "Project", back_populates="tickets", lazy="joined"
    )
    assignee: Mapped[User | None] = relationship(  # noqa: F821
        "User", foreign_keys=[assignee_id], lazy="joined"
    )
    reporter: Mapped[User | None] = relationship(  # noqa: F821
        "User", foreign_keys=[reporter_id], lazy="joined"
    )
    history: Mapped[list[TicketHistory]] = relationship(  # noqa: F821
        "TicketHistory", back_populates="ticket", lazy="selectin", cascade="all, delete-orphan"
    )
    comments: Mapped[list[Comment]] = relationship(  # noqa: F821
        "Comment", back_populates="ticket", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Ticket #{self.ticket_number} '{self.title[:40]}'>"
