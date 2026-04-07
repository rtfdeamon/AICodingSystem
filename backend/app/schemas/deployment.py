"""Deployment schemas — request/response models for deployments."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.models.deployment import Deployment


class DeploymentResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    environment: str
    deploy_type: str
    canary_pct: int | None = None
    status: str
    initiated_by: uuid.UUID | None = None
    commit_sha: str | None = None
    build_url: str | None = None
    health_check: dict[str, Any] | None = None
    rollback_reason: str | None = None
    created_at: str
    completed_at: str | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_deployment(cls, dep: Deployment) -> DeploymentResponse:
        return cls(
            id=dep.id,
            ticket_id=dep.ticket_id,
            environment=dep.environment.value,
            deploy_type=dep.deploy_type.value,
            canary_pct=dep.canary_pct,
            status=dep.status.value,
            initiated_by=dep.initiated_by,
            commit_sha=dep.commit_sha,
            build_url=dep.build_url,
            health_check=dep.health_check,
            rollback_reason=dep.rollback_reason,
            created_at=dep.created_at.isoformat(),
            completed_at=dep.completed_at.isoformat() if dep.completed_at else None,
        )


class StagingDeployRequest(BaseModel):
    branch: str = "main"
    commit_sha: str | None = None


class ProductionDeployRequest(BaseModel):
    commit_sha: str
    canary_pct: int = Field(default=10, ge=1, le=100)


class RollbackRequest(BaseModel):
    reason: str


class PromoteRequest(BaseModel):
    new_percentage: int = Field(ge=1, le=100)


class HealthResponse(BaseModel):
    healthy: bool
    error_rate: float
    latency_p50: int
    latency_p95: int
    latency_p99: int
    uptime_pct: float
    details: dict[str, Any] | None = None
