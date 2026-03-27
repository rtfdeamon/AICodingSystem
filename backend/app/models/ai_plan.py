"""AiPlan ORM model — stores AI-generated implementation plans for tickets."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
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
    from app.models.ai_code_generation import AiCodeGeneration
    from app.models.ticket import Ticket
    from app.models.user import User


class PlanStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class AiPlan(Base):
    __tablename__ = "ai_plans"

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
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        doc="Incremented each time a new plan is generated for the same ticket.",
    )
    agent_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Agent that generated this plan.",
    )

    # Plan content
    plan_markdown: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Full plan in Markdown format for human review.",
    )
    subtasks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        doc="Ordered list of subtask objects with title, description, affected_files, etc.",
    )
    file_list: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        doc="Flat list of all files expected to be created or modified.",
    )

    # Review
    status: Mapped[PlanStatus] = mapped_column(
        Enum(PlanStatus, name="plan_status_enum", create_constraint=True),
        nullable=False,
        default=PlanStatus.PENDING,
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # AI call metadata
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        nullable=False,
    )

    # Relationships
    ticket: Mapped[Ticket] = relationship(  # noqa: F821
        "Ticket",
        lazy="joined",
    )
    reviewer: Mapped[User | None] = relationship(  # noqa: F821
        "User",
        lazy="joined",
    )
    code_generations: Mapped[list[AiCodeGeneration]] = relationship(  # noqa: F821
        "AiCodeGeneration",
        back_populates="plan",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AiPlan ticket={self.ticket_id} v{self.version} status={self.status.value}>"
