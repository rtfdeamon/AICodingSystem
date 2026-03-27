"""Deployment endpoints — staging, production, rollback, promote, and health."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.database import get_db
from app.models.deployment import (
    DeployEnvironment,
    Deployment,
    DeployStatus,
    DeployType,
)
from app.models.ticket import Ticket
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/tickets/{ticket_id}/deployments", response_model=list[DeploymentResponse])
async def list_deployments(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> list[DeploymentResponse]:
    """List all deployments for a ticket."""
    result = await db.execute(
        select(Deployment)
        .where(Deployment.ticket_id == ticket_id)
        .order_by(Deployment.created_at.desc())
    )
    deployments = result.scalars().all()
    return [DeploymentResponse.from_orm_deployment(d) for d in deployments]


@router.post(
    "/tickets/{ticket_id}/deploy/staging",
    response_model=DeploymentResponse,
    status_code=201,
)
async def deploy_to_staging(
    ticket_id: uuid.UUID,
    data: StagingDeployRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("developer", "pm_lead", "owner"))],
) -> DeploymentResponse:
    """Trigger a staging deployment for a ticket."""
    from app.ci.deployer import deploy_staging

    # Verify ticket exists
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    project_name = "default"
    if ticket.project:
        project_name = (
            ticket.project.name if hasattr(ticket.project, "name") else str(ticket.project_id)
        )

    commit_sha = data.commit_sha or "HEAD"

    # Trigger deployment
    deploy_result = await deploy_staging(
        project=project_name,
        branch=data.branch,
        commit_sha=commit_sha,
    )

    # Persist deployment record
    deployment = Deployment(
        ticket_id=ticket_id,
        environment=DeployEnvironment.STAGING,
        deploy_type=DeployType.FULL,
        status=DeployStatus(deploy_result.status),
        initiated_by=current_user.id,
        commit_sha=commit_sha,
        build_url=deploy_result.url,
    )
    if deploy_result.status == "deployed":
        deployment.completed_at = datetime.now(UTC)

    db.add(deployment)
    await db.flush()
    await db.refresh(deployment)

    logger.info(
        "Staging deploy initiated for ticket %s by user %s: %s",
        ticket_id,
        current_user.id,
        deploy_result.status,
    )

    return DeploymentResponse.from_orm_deployment(deployment)


@router.post(
    "/tickets/{ticket_id}/deploy/production",
    response_model=DeploymentResponse,
    status_code=201,
)
async def deploy_to_production(
    ticket_id: uuid.UUID,
    data: ProductionDeployRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("pm_lead"))],
) -> DeploymentResponse:
    """Trigger a production canary deployment. Requires pm_lead role only (per TZ)."""
    from app.ci.deployer import deploy_production_canary

    # Verify ticket exists
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    project_name = "default"
    if ticket.project:
        project_name = (
            ticket.project.name if hasattr(ticket.project, "name") else str(ticket.project_id)
        )

    deploy_result = await deploy_production_canary(
        project=project_name,
        commit_sha=data.commit_sha,
        percentage=data.canary_pct,
    )

    deployment = Deployment(
        ticket_id=ticket_id,
        environment=DeployEnvironment.PRODUCTION,
        deploy_type=DeployType.CANARY,
        canary_pct=data.canary_pct,
        status=DeployStatus(deploy_result.status),
        initiated_by=current_user.id,
        commit_sha=data.commit_sha,
        build_url=deploy_result.url,
    )
    if deploy_result.status == "deployed":
        deployment.completed_at = datetime.now(UTC)

    db.add(deployment)
    await db.flush()
    await db.refresh(deployment)

    logger.info(
        "Production canary deploy initiated for ticket %s by user %s: %d%% canary",
        ticket_id,
        current_user.id,
        data.canary_pct,
    )

    return DeploymentResponse.from_orm_deployment(deployment)


@router.post(
    "/deployments/{deployment_id}/rollback",
    response_model=DeploymentResponse,
)
async def rollback_deployment(
    deployment_id: uuid.UUID,
    data: RollbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DeploymentResponse:
    """Rollback a deployment."""
    from app.ci.deployer import rollback

    result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
    deployment = result.scalar_one_or_none()
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found.")

    if deployment.status in (DeployStatus.ROLLED_BACK, DeployStatus.FAILED):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot rollback deployment with status '{deployment.status.value}'.",
        )

    deploy_result = await rollback(str(deployment_id))

    deployment.status = DeployStatus(deploy_result.status)
    deployment.rollback_reason = data.reason
    deployment.completed_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(deployment)

    logger.info("Deployment %s rolled back: %s", deployment_id, data.reason)
    return DeploymentResponse.from_orm_deployment(deployment)


@router.post(
    "/deployments/{deployment_id}/promote",
    response_model=DeploymentResponse,
)
async def promote_deployment(
    deployment_id: uuid.UUID,
    data: PromoteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("pm_lead"))],
) -> DeploymentResponse:
    """Promote a canary deployment to a higher traffic percentage. PM-only."""
    from app.ci.deployer import promote_canary

    result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
    deployment = result.scalar_one_or_none()
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found.")

    if deployment.deploy_type != DeployType.CANARY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only canary deployments can be promoted.",
        )

    if deployment.status not in (DeployStatus.DEPLOYING, DeployStatus.DEPLOYED):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot promote deployment with status '{deployment.status.value}'.",
        )

    deploy_result = await promote_canary(str(deployment_id), data.new_percentage)

    deployment.canary_pct = data.new_percentage
    deployment.status = DeployStatus(deploy_result.status)
    if data.new_percentage == 100:
        deployment.completed_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(deployment)

    logger.info("Deployment %s promoted to %d%%", deployment_id, data.new_percentage)
    return DeploymentResponse.from_orm_deployment(deployment)


@router.get("/deployments/{deployment_id}/health", response_model=HealthResponse)
async def check_health(
    deployment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> HealthResponse:
    """Check health metrics for a deployment."""
    from app.ci.deployer import check_deploy_health

    result = await db.execute(select(Deployment).where(Deployment.id == deployment_id))
    deployment = result.scalar_one_or_none()
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found.")

    health = await check_deploy_health(str(deployment_id))

    # Persist the health snapshot on the deployment
    deployment.health_check = {
        "error_rate": health.error_rate,
        "latency_p50": health.latency_p50,
        "latency_p95": health.latency_p95,
        "latency_p99": health.latency_p99,
        "healthy": health.healthy,
    }
    await db.flush()

    return HealthResponse(
        healthy=health.healthy,
        error_rate=health.error_rate,
        latency_p50=health.latency_p50,
        latency_p95=health.latency_p95,
        latency_p99=health.latency_p99,
        uptime_pct=health.uptime_pct,
        details=health.details,
    )
