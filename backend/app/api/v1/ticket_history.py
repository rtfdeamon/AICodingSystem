"""Ticket history endpoint — audit trail for ticket state changes."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.ticket_history import TicketHistory
from app.models.user import User

router = APIRouter()


class TicketHistoryResponse(BaseModel):
    """Response schema for a ticket history entry."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    ticket_id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_type: str = "user"
    from_column: str | None = None
    to_column: str | None = None
    action: str
    details: dict[str, Any] | None = None
    created_at: str = Field(default="")

    @classmethod
    def from_orm_instance(cls, obj: TicketHistory) -> TicketHistoryResponse:
        return cls(
            id=obj.id,
            ticket_id=obj.ticket_id,
            actor_id=obj.actor_id,
            actor_type=obj.actor_type,
            from_column=obj.from_column,
            to_column=obj.to_column,
            action=obj.action,
            details=obj.details,
            created_at=obj.created_at.isoformat() if obj.created_at else "",
        )


@router.get(
    "/tickets/{ticket_id}/history",
    response_model=list[TicketHistoryResponse],
)
async def list_ticket_history(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> list[TicketHistoryResponse]:
    """List audit-trail entries for a ticket, newest first."""
    offset = (page - 1) * per_page
    stmt = (
        select(TicketHistory)
        .where(TicketHistory.ticket_id == ticket_id)
        .options(joinedload(TicketHistory.actor))
        .order_by(TicketHistory.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    entries = result.scalars().unique().all()
    return [TicketHistoryResponse.from_orm_instance(e) for e in entries]
