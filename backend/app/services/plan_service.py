"""Service layer for AI Plan operations."""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_plan import AiPlan, PlanStatus
from app.models.ticket import ColumnName, Ticket

logger = logging.getLogger(__name__)


async def list_plans(db: AsyncSession, ticket_id: uuid.UUID) -> list[AiPlan]:
    """Return all plans for a ticket ordered by version descending."""
    # Verify ticket exists
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    if ticket_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found.",
        )

    result = await db.execute(
        select(AiPlan).where(AiPlan.ticket_id == ticket_id).order_by(AiPlan.version.desc())
    )
    return list(result.scalars().all())


async def get_plan(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> AiPlan:
    """Return a single plan, ensuring it belongs to the ticket."""
    result = await db.execute(
        select(AiPlan).where(
            AiPlan.id == plan_id,
            AiPlan.ticket_id == ticket_id,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found.",
        )
    return plan


async def approve_plan(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    plan_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> AiPlan:
    """Approve a plan and move the ticket to ``ai_coding``."""
    plan = await get_plan(db, ticket_id, plan_id)

    if plan.status != PlanStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Plan is already '{plan.status.value}' and cannot be approved.",
        )

    plan.status = PlanStatus.APPROVED
    plan.reviewed_by = reviewer_id
    await db.flush()
    await db.refresh(plan)

    # Move ticket to ai_coding if it is currently in plan_review
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    if ticket and ticket.column_name == ColumnName.PLAN_REVIEW:
        ticket.column_name = ColumnName.AI_CODING
        await db.flush()

    logger.info(
        "Plan %s for ticket %s approved by %s",
        plan_id,
        ticket_id,
        reviewer_id,
    )
    return plan


async def reject_plan(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    plan_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    comment: str,
) -> AiPlan:
    """Reject a plan with a review comment and move ticket back to ``ai_planning``."""
    plan = await get_plan(db, ticket_id, plan_id)

    if plan.status != PlanStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Plan is already '{plan.status.value}' and cannot be rejected.",
        )

    plan.status = PlanStatus.REJECTED
    plan.reviewed_by = reviewer_id
    plan.review_comment = comment
    await db.flush()
    await db.refresh(plan)

    # Move ticket back to ai_planning for re-plan
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    if ticket and ticket.column_name == ColumnName.PLAN_REVIEW:
        ticket.column_name = ColumnName.AI_PLANNING
        await db.flush()

    logger.info(
        "Plan %s for ticket %s rejected by %s: %s",
        plan_id,
        ticket_id,
        reviewer_id,
        comment,
    )
    return plan
