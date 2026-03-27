"""Ticket CRUD endpoints."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.ticket import (
    TicketCreate,
    TicketListResponse,
    TicketResponse,
    TicketUpdate,
)
from app.services import ticket_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/projects/{project_id}/tickets",
    response_model=TicketResponse,
    status_code=201,
)
async def create_ticket(
    project_id: uuid.UUID,
    data: TicketCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TicketResponse:
    """Create a new ticket in the project backlog."""
    ticket = await ticket_service.create_ticket(db, project_id, current_user.id, data)
    return TicketResponse.model_validate(ticket)


@router.get(
    "/projects/{project_id}/tickets",
    response_model=TicketListResponse,
)
async def list_tickets(
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    column: str | None = Query(default=None, description="Filter by column name"),
    priority: str | None = Query(
        default=None,
        pattern=r"^P[0-3]$",
        description="Filter by priority",
    ),
    assignee_id: uuid.UUID | None = Query(default=None, description="Filter by assignee"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> TicketListResponse:
    """List tickets for a project with optional filters and pagination."""
    return await ticket_service.list_tickets(
        db,
        project_id,
        column=column,
        priority=priority,
        assignee_id=assignee_id,
        page=page,
        per_page=per_page,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> TicketResponse:
    """Get a single ticket by id."""
    ticket = await ticket_service.get_ticket(db, ticket_id)
    return TicketResponse.model_validate(ticket)


@router.patch("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: uuid.UUID,
    data: TicketUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> TicketResponse:
    """Update ticket fields."""
    ticket = await ticket_service.update_ticket(db, ticket_id, data)
    return TicketResponse.model_validate(ticket)


@router.delete("/tickets/{ticket_id}", status_code=204)
async def delete_ticket(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Soft-delete a ticket."""
    await ticket_service.delete_ticket(db, ticket_id)
