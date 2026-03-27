"""AiCodeGeneration ORM model — tracks each AI code generation attempt."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow

if TYPE_CHECKING:
    from app.models.ai_log import AiLog
    from app.models.ai_plan import AiPlan


class CodeGenStatus(enum.StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"


class AiCodeGeneration(Base):
    __tablename__ = "ai_code_generations"

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
    plan_id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        ForeignKey("ai_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subtask_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Zero-based index into the plan's subtasks array.",
    )
    agent_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Agent that generated the code for this subtask.",
    )
    branch_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Results
    files_changed: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        doc="List of {path, action, diff_summary} dicts.",
    )
    commit_sha: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    status: Mapped[CodeGenStatus] = mapped_column(
        Enum(CodeGenStatus, name="code_gen_status_enum", create_constraint=True),
        nullable=False,
        default=CodeGenStatus.IN_PROGRESS,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    lint_passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    test_passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Link to the AI call log
    log_id: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("ai_logs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        nullable=False,
    )

    # Relationships
    plan: Mapped[AiPlan] = relationship(  # noqa: F821
        "AiPlan",
        back_populates="code_generations",
        lazy="joined",
    )
    log: Mapped[AiLog | None] = relationship(  # noqa: F821
        "AiLog",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<AiCodeGeneration plan={self.plan_id} subtask={self.subtask_index} "
            f"status={self.status.value}>"
        )
