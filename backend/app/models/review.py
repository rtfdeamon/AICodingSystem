"""Review ORM model — tracks AI and human code reviews for tickets."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow


class ReviewerType(enum.StrEnum):
    USER = "user"
    AI_AGENT = "ai_agent"


class ReviewDecision(enum.StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        primary_key=True,
        default=generate_uuid,
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="Null for AI-generated reviews.",
    )
    reviewer_type: Mapped[ReviewerType] = mapped_column(
        Enum(ReviewerType, name="reviewer_type_enum", create_constraint=True),
        nullable=False,
    )
    agent_name: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Name of the AI agent if reviewer_type is ai_agent (e.g. 'claude', 'codex').",
    )
    decision: Mapped[ReviewDecision] = mapped_column(
        Enum(ReviewDecision, name="review_decision_enum", create_constraint=True),
        nullable=False,
    )
    body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Overall review summary or comment body.",
    )
    inline_comments: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
        doc="List of inline comments: [{file, line, comment, severity}].",
    )
    log_id: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("ai_logs.id", ondelete="SET NULL"),
        nullable=True,
        doc="Reference to the AI log entry that generated this review.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Review ticket={self.ticket_id} type={self.reviewer_type.value} "
            f"decision={self.decision.value}>"
        )
