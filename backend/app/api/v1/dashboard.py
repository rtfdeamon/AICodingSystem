"""Dashboard metrics endpoints — real implementations backed by dashboard_service."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import dashboard_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PipelineStats(BaseModel):
    """Pipeline throughput and status metrics."""

    tickets_per_column: dict[str, int] = {}
    avg_time_per_column_hours: dict[str, float] = {}
    total_tickets: int = 0


class AICostMetrics(BaseModel):
    """AI provider cost breakdown."""

    cost_by_agent: dict[str, float] = {}
    cost_by_day: dict[str, float] = {}
    total_cost: float = 0.0
    tokens_total: int = 0


class CodeQualityMetrics(BaseModel):
    """Code quality aggregate metrics."""

    lint_pass_rate: float = 0.0
    test_coverage_avg: float = 0.0
    review_pass_rate: float = 0.0
    security_vuln_count: int = 0


class DeploymentStats(BaseModel):
    """Deployment statistics."""

    deploy_count: int = 0
    rollback_rate: float = 0.0
    avg_deploy_time_ms: int = 0
    success_rate: float = 0.0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/pipeline-stats", response_model=PipelineStats)
async def pipeline_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID = Query(description="Project ID to get stats for"),
) -> PipelineStats:
    """Return pipeline throughput statistics for a project."""
    data = await dashboard_service.get_pipeline_stats(db, project_id)
    return PipelineStats(**data)


@router.get("/ai-costs", response_model=AICostMetrics)
async def ai_costs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID = Query(description="Project ID to get costs for"),
    days: int = Query(default=30, ge=1, le=365, description="Date range in days"),
) -> AICostMetrics:
    """Return AI provider cost breakdown for a project."""
    data = await dashboard_service.get_ai_costs(db, project_id, date_range_days=days)
    return AICostMetrics(**data)


@router.get("/code-quality", response_model=CodeQualityMetrics)
async def code_quality(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID = Query(description="Project ID to get quality metrics for"),
) -> CodeQualityMetrics:
    """Return code quality aggregate metrics for a project."""
    data = await dashboard_service.get_code_quality(db, project_id)
    return CodeQualityMetrics(**data)


@router.get("/deployment-stats", response_model=DeploymentStats)
async def deployment_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID = Query(description="Project ID to get deployment stats for"),
) -> DeploymentStats:
    """Return deployment statistics for a project."""
    data = await dashboard_service.get_deployment_stats(db, project_id)
    return DeploymentStats(**data)
