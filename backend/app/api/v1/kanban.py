"""Kanban board operation endpoints: move, reorder, board state."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.ticket import TicketMoveRequest, TicketResponse
from app.services import kanban_service

logger = logging.getLogger(__name__)

router = APIRouter()


class ReorderRequest(BaseModel):
    """Request body for reordering a ticket within its column."""

    position: int = Field(ge=0, description="New sort position within the column")


@router.post("/tickets/{ticket_id}/move", response_model=TicketResponse)
async def move_ticket(
    ticket_id: uuid.UUID,
    data: TicketMoveRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TicketResponse:
    """Move a ticket to a new Kanban column.

    Validates the state-machine transition rules and RBAC permissions.
    """
    ticket = await kanban_service.move_ticket(
        db,
        ticket_id,
        to_column=data.to_column,
        actor_id=current_user.id,
        actor_role=current_user.role,
        comment=data.comment,
    )
    return TicketResponse.model_validate(ticket)


@router.patch("/tickets/{ticket_id}/position", response_model=TicketResponse)
async def reorder_ticket(
    ticket_id: uuid.UUID,
    data: ReorderRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> TicketResponse:
    """Change the sort position of a ticket within its current column."""
    ticket = await kanban_service.reorder_ticket(db, ticket_id, data.position)
    return TicketResponse.model_validate(ticket)


class BoardResponse(BaseModel):
    columns: dict[str, list[TicketResponse]]
    project_id: str


@router.get("/projects/{project_id}/board", response_model=BoardResponse)
async def get_board(
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> BoardResponse:
    """Return the full Kanban board state: all tickets grouped by column."""
    board = await kanban_service.get_board(db, project_id)
    return BoardResponse(columns=board, project_id=str(project_id))
