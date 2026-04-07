"""AI log viewing endpoints — queries real AiLog records."""

from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.ai_log import AiLog, AiLogStatus
from app.models.user import User
from app.schemas.ai_log import AILogEntry, AILogListResponse, AILogStats

logger = logging.getLogger(__name__)

router = APIRouter()


# Schemas imported from app.schemas.ai_log


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=AILogListResponse)
async def list_ai_logs(
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    agent: str | None = Query(default=None),
    ticket_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> AILogListResponse:
    """List AI interaction logs with optional filters."""
    query = select(AiLog).order_by(AiLog.created_at.desc())

    if agent:
        query = query.where(AiLog.agent_name == agent)
    if ticket_id:
        query = query.where(AiLog.ticket_id == ticket_id)
    if status_filter:
        with contextlib.suppress(ValueError):
            query = query.where(AiLog.status == AiLogStatus(status_filter))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    offset = (page - 1) * per_page
    result = await db.execute(query.offset(offset).limit(per_page))
    logs = result.scalars().all()

    items = [
        AILogEntry(
            id=str(log.id),
            ticket_id=str(log.ticket_id) if log.ticket_id else None,
            agent=log.agent_name,
            model=log.model_id,
            action=log.action_type,
            input_tokens=log.prompt_tokens,
            output_tokens=log.completion_tokens,
            cost_usd=log.cost_usd,
            duration_ms=log.latency_ms,
            status=log.status.value,
            error_message=log.error_message,
            created_at=log.created_at,
        )
        for log in logs
    ]

    return AILogListResponse(items=items, total=total, page=page, page_size=per_page)


@router.get("/stats", response_model=AILogStats)
async def ai_log_stats(
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AILogStats:
    """Return aggregated AI usage statistics."""
    result = await db.execute(select(AiLog))
    logs = result.scalars().all()

    if not logs:
        return AILogStats()

    by_agent: dict[str, int] = {}
    by_model: dict[str, int] = {}
    total_duration = 0

    for log in logs:
        by_agent[log.agent_name] = by_agent.get(log.agent_name, 0) + 1
        by_model[log.model_id] = by_model.get(log.model_id, 0) + 1
        total_duration += log.latency_ms

    return AILogStats(
        total_requests=len(logs),
        total_input_tokens=sum(entry.prompt_tokens for entry in logs),
        total_output_tokens=sum(entry.completion_tokens for entry in logs),
        total_cost_usd=sum(entry.cost_usd for entry in logs),
        average_duration_ms=total_duration / len(logs) if logs else 0,
        by_agent=by_agent,
        by_model=by_model,
    )


@router.get("/{log_id}", response_model=AILogEntry)
async def get_ai_log(
    log_id: uuid.UUID,
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AILogEntry:
    """Get a single AI log entry by id."""
    result = await db.execute(select(AiLog).where(AiLog.id == log_id))
    log = result.scalar_one_or_none()

    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI log entry not found.",
        )

    return AILogEntry(
        id=str(log.id),
        ticket_id=str(log.ticket_id) if log.ticket_id else None,
        agent=log.agent_name,
        model=log.model_id,
        action=log.action_type,
        input_tokens=log.prompt_tokens,
        output_tokens=log.completion_tokens,
        cost_usd=log.cost_usd,
        duration_ms=log.latency_ms,
        status=log.status.value,
        error_message=log.error_message,
        created_at=log.created_at,
    )
