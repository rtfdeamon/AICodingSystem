"""Dashboard metrics endpoints — real implementations backed by dashboard_service."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.quality.ai_metrics import get_ai_quality_metrics
from app.quality.feedback_tracker import get_review_feedback_metrics
from app.schemas.dashboard import (
    AICostMetrics,
    CodeQualityMetrics,
    DeploymentStats,
    PipelineStats,
)
from app.services import dashboard_service

logger = logging.getLogger(__name__)

router = APIRouter()


# Schemas imported from app.schemas.dashboard


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


@router.get("/ai-quality-metrics")
async def ai_quality_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID = Query(description="Project ID"),
    days: int = Query(default=30, ge=1, le=365, description="Date range in days"),
) -> dict:
    """Return AI-specific quality metrics (regression rate, defect density, merge confidence)."""
    return await get_ai_quality_metrics(db, project_id, date_range_days=days)


@router.get("/review-feedback")
async def review_feedback(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID = Query(description="Project ID"),
    days: int = Query(default=30, ge=1, le=365, description="Date range in days"),
) -> dict:
    """Return developer feedback metrics on AI review findings."""
    return await get_review_feedback_metrics(db, project_id, date_range_days=days)
