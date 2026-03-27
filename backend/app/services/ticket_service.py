"""Ticket CRUD service layer."""

from __future__ import annotations

import logging
import math
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.ticket import ColumnName, Priority, Ticket
from app.models.ticket_history import TicketHistory
from app.schemas.ticket import TicketCreate, TicketListResponse, TicketResponse, TicketUpdate

logger = logging.getLogger(__name__)


async def _next_ticket_number(db: AsyncSession, project_id: uuid.UUID) -> int:
    """Return the next ticket number for *project_id* (max + 1)."""
    result = await db.execute(
        select(func.coalesce(func.max(Ticket.ticket_number), 0)).where(
            Ticket.project_id == project_id
        )
    )
    return result.scalar_one() + 1


async def create_ticket(
    db: AsyncSession,
    project_id: uuid.UUID,
    reporter_id: uuid.UUID,
    data: TicketCreate,
) -> Ticket:
    """Create a new ticket in the backlog and record a history entry."""
    ticket_number = await _next_ticket_number(db, project_id)

    ticket = Ticket(
        project_id=project_id,
        reporter_id=reporter_id,
        ticket_number=ticket_number,
        title=data.title,
        description=data.description,
        acceptance_criteria=data.acceptance_criteria,
        priority=Priority(data.priority),
        labels=data.labels or [],
        column_name=ColumnName.BACKLOG,
        position=0,
    )
    db.add(ticket)
    await db.flush()
    await db.refresh(ticket)

    # Audit history
    history = TicketHistory(
        ticket_id=ticket.id,
        actor_id=reporter_id,
        actor_type="user",
        action="created",
        to_column=ColumnName.BACKLOG.value,
        details={"title": data.title},
    )
    db.add(history)

    logger.info(
        "Ticket created: #%d in project %s (id=%s)",
        ticket_number,
        project_id,
        ticket.id,
    )
    return ticket


async def get_ticket(db: AsyncSession, ticket_id: uuid.UUID) -> Ticket:
    """Return a ticket by id or raise 404."""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    return ticket


async def list_tickets(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    column: str | None = None,
    priority: str | None = None,
    assignee_id: uuid.UUID | None = None,
    page: int = 1,
    per_page: int = 50,
) -> TicketListResponse:
    """Return a paginated, filterable list of tickets for a project."""
    query: Select[tuple[Ticket]] = select(Ticket).where(Ticket.project_id == project_id)

    if column is not None:
        query = query.where(Ticket.column_name == ColumnName(column))
    if priority is not None:
        query = query.where(Ticket.priority == Priority(priority))
    if assignee_id is not None:
        query = query.where(Ticket.assignee_id == assignee_id)

    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Paginated results ordered by position then created_at
    query = (
        query.order_by(Ticket.position.asc(), Ticket.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    tickets = list(result.scalars().all())

    return TicketListResponse(
        items=[TicketResponse.model_validate(t) for t in tickets],
        total=total,
        page=page,
        page_size=per_page,
        pages=max(1, math.ceil(total / per_page)),
    )


async def update_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    data: TicketUpdate,
) -> Ticket:
    """Update a ticket's mutable fields.  Returns the updated ticket."""
    ticket = await get_ticket(db, ticket_id)

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        return ticket

    # Map priority string to enum
    if "priority" in update_data and update_data["priority"] is not None:
        update_data["priority"] = Priority(update_data["priority"])

    for field, value in update_data.items():
        setattr(ticket, field, value)

    await db.flush()
    await db.refresh(ticket)

    logger.info("Ticket updated: %s fields=%s", ticket_id, list(update_data.keys()))
    return ticket


async def delete_ticket(db: AsyncSession, ticket_id: uuid.UUID) -> None:
    """Soft-delete a ticket by removing it from the database.

    In a production system this might set an ``is_deleted`` flag.  For now we
    perform a hard delete but log it clearly so the audit trail is preserved
    via ``ticket_history``.
    """
    ticket = await get_ticket(db, ticket_id)

    # Record deletion in history before removing
    history = TicketHistory(
        ticket_id=ticket.id,
        actor_type="system",
        action="deleted",
        from_column=ticket.column_name.value if ticket.column_name else None,
        details={"title": ticket.title},
    )
    db.add(history)

    await db.delete(ticket)
    logger.info("Ticket deleted: %s", ticket_id)
