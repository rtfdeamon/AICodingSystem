"""AiLog ORM model — tracks every AI provider call for auditing and cost analysis."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

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
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow


class AiLogStatus(enum.StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    FALLBACK = "fallback"


class AiLog(Base):
    __tablename__ = "ai_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        primary_key=True,
        default=generate_uuid,
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="Logical agent name, e.g. 'claude', 'codex', 'gemini'.",
    )
    action_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="What the call was for, e.g. 'planning', 'coding', 'test_gen', 'security'.",
    )
    model_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Exact model identifier sent to the provider.",
    )

    # Request / response payloads (may be large; stored as text for debugging)
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Token usage and cost
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Wall-clock latency of the provider call in milliseconds.",
    )

    # Outcome
    status: Mapped[AiLogStatus] = mapped_column(
        Enum(AiLogStatus, name="ai_log_status_enum", create_constraint=True),
        nullable=False,
        default=AiLogStatus.SUCCESS,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<AiLog agent={self.agent_name} action={self.action_type} "
            f"status={self.status.value} cost=${self.cost_usd:.4f}>"
        )
