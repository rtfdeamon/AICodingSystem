"""AI Plan endpoints — list, get, approve, reject plans for tickets."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.plan import PlanRejectRequest, PlanResponse
from app.services import plan_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/tickets/{ticket_id}/plans",
    response_model=list[PlanResponse],
)
async def list_plans(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> list[PlanResponse]:
    """List all AI plans for a ticket, newest version first."""
    plans = await plan_service.list_plans(db, ticket_id)
    return [PlanResponse.model_validate(p) for p in plans]


@router.get(
    "/tickets/{ticket_id}/plans/{plan_id}",
    response_model=PlanResponse,
)
async def get_plan(
    ticket_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> PlanResponse:
    """Get a single AI plan by ID."""
    plan = await plan_service.get_plan(db, ticket_id, plan_id)
    return PlanResponse.model_validate(plan)


@router.post(
    "/tickets/{ticket_id}/plans/{plan_id}/approve",
    response_model=PlanResponse,
)
async def approve_plan(
    ticket_id: uuid.UUID,
    plan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PlanResponse:
    """Approve a pending plan — moves the ticket to ai_coding."""
    plan = await plan_service.approve_plan(db, ticket_id, plan_id, current_user.id)
    return PlanResponse.model_validate(plan)


@router.post(
    "/tickets/{ticket_id}/plans/{plan_id}/reject",
    response_model=PlanResponse,
)
async def reject_plan(
    ticket_id: uuid.UUID,
    plan_id: uuid.UUID,
    data: PlanRejectRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PlanResponse:
    """Reject a pending plan with a comment — moves the ticket back to ai_planning."""
    plan = await plan_service.reject_plan(db, ticket_id, plan_id, current_user.id, data.comment)
    return PlanResponse.model_validate(plan)
