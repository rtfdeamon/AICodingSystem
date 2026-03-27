"""Deployment ORM model — tracks deployments to staging and production."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
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


class DeployEnvironment(enum.StrEnum):
    STAGING = "staging"
    PRODUCTION = "production"


class DeployType(enum.StrEnum):
    FULL = "full"
    CANARY = "canary"


class DeployStatus(enum.StrEnum):
    PENDING = "pending"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class Deployment(Base):
    __tablename__ = "deployments"

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
    environment: Mapped[DeployEnvironment] = mapped_column(
        Enum(DeployEnvironment, name="deploy_environment_enum", create_constraint=True),
        nullable=False,
    )
    deploy_type: Mapped[DeployType] = mapped_column(
        Enum(DeployType, name="deploy_type_enum", create_constraint=True),
        nullable=False,
        default=DeployType.FULL,
    )
    canary_pct: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Canary traffic percentage (1-100). Null for full deploys.",
    )
    status: Mapped[DeployStatus] = mapped_column(
        Enum(DeployStatus, name="deploy_status_enum", create_constraint=True),
        nullable=False,
        default=DeployStatus.PENDING,
    )
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    commit_sha: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    build_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    health_check: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        doc="Latest health snapshot: {error_rate, latency_p50, latency_p99}.",
    )
    rollback_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Deployment ticket={self.ticket_id} env={self.environment.value} "
            f"status={self.status.value}>"
        )
