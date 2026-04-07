"""Kanban board orchestrator: state-machine transitions, RBAC, and side effects."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import ColumnName, Ticket
from app.models.ticket_history import TicketHistory
from app.schemas.ticket import TicketResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transition rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitionRule:
    """Defines a valid column transition."""

    allowed_roles: frozenset[str]
    prerequisites: list[str]  # field names that must be non-empty


TRANSITION_RULES: dict[tuple[str, str], TransitionRule] = {
    # backlog -> ai_planning: PM or owner queues ticket for AI planning
    (ColumnName.BACKLOG.value, ColumnName.AI_PLANNING.value): TransitionRule(
        allowed_roles=frozenset({"pm_lead", "owner"}),
        prerequisites=["description"],
    ),
    # ai_planning -> plan_review: AI agent completes planning
    (ColumnName.AI_PLANNING.value, ColumnName.PLAN_REVIEW.value): TransitionRule(
        allowed_roles=frozenset({"ai_agent", "pm_lead", "owner"}),
        prerequisites=[],
    ),
    # plan_review -> ai_coding: reviewer approves plan, send to AI coding
    (ColumnName.PLAN_REVIEW.value, ColumnName.AI_CODING.value): TransitionRule(
        allowed_roles=frozenset({"developer", "pm_lead", "owner"}),
        prerequisites=[],
    ),
    # plan_review -> backlog: reviewer rejects plan, send back
    (ColumnName.PLAN_REVIEW.value, ColumnName.BACKLOG.value): TransitionRule(
        allowed_roles=frozenset({"developer", "pm_lead", "owner"}),
        prerequisites=[],
    ),
    # ai_coding -> code_review: AI agent completes coding
    (ColumnName.AI_CODING.value, ColumnName.CODE_REVIEW.value): TransitionRule(
        allowed_roles=frozenset({"ai_agent", "pm_lead", "owner"}),
        prerequisites=[],
    ),
    # code_review -> staging: reviewer approves code
    (ColumnName.CODE_REVIEW.value, ColumnName.STAGING.value): TransitionRule(
        allowed_roles=frozenset({"developer", "pm_lead", "owner"}),
        prerequisites=[],
    ),
    # code_review -> ai_coding: reviewer requests changes
    (ColumnName.CODE_REVIEW.value, ColumnName.AI_CODING.value): TransitionRule(
        allowed_roles=frozenset({"developer", "pm_lead", "owner"}),
        prerequisites=[],
    ),
    # staging -> staging_verification: deploy to staging complete
    (ColumnName.STAGING.value, ColumnName.STAGING_VERIFICATION.value): TransitionRule(
        allowed_roles=frozenset({"ai_agent", "developer", "pm_lead", "owner"}),
        prerequisites=[],
    ),
    # staging_verification -> production: verification passed (PM only per TZ)
    (ColumnName.STAGING_VERIFICATION.value, ColumnName.PRODUCTION.value): TransitionRule(
        allowed_roles=frozenset({"pm_lead"}),
        prerequisites=[],
    ),
    # staging_verification -> ai_coding: verification failed, rework
    (ColumnName.STAGING_VERIFICATION.value, ColumnName.AI_CODING.value): TransitionRule(
        allowed_roles=frozenset({"developer", "pm_lead", "owner"}),
        prerequisites=[],
    ),
}


def validate_transition(
    ticket: Ticket,
    to_column: str,
    actor_role: str,
) -> tuple[bool, str]:
    """Check whether *ticket* can transition to *to_column* given *actor_role*.

    Returns ``(True, "")`` on success or ``(False, reason)`` on failure.
    """
    from_column = (
        ticket.column_name.value
        if isinstance(ticket.column_name, ColumnName)
        else ticket.column_name
    )
    key = (from_column, to_column)

    rule = TRANSITION_RULES.get(key)
    if rule is None:
        return False, f"Transition from '{from_column}' to '{to_column}' is not allowed."

    if actor_role not in rule.allowed_roles:
        return False, (
            f"Role '{actor_role}' cannot move tickets from '{from_column}' to '{to_column}'. "
            f"Allowed roles: {', '.join(sorted(rule.allowed_roles))}."
        )

    # Check prerequisites
    for field in rule.prerequisites:
        value = getattr(ticket, field, None)
        if not value:
            return False, f"Prerequisite not met: '{field}' must be set before this transition."

    return True, ""


async def move_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    to_column: str,
    actor_id: uuid.UUID,
    actor_role: str,
    comment: str | None = None,
) -> Ticket:
    """Validate and execute a ticket column transition.

    Creates a history record and returns the updated ticket.  Raises
    :class:`HTTPException` if the transition is invalid.
    """
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    ok, reason = validate_transition(ticket, to_column, actor_role)
    if not ok:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=reason)

    from_column = (
        ticket.column_name.value
        if isinstance(ticket.column_name, ColumnName)
        else ticket.column_name
    )

    # Perform transition
    ticket.column_name = ColumnName(to_column)
    ticket.position = 0  # top of the new column

    # Auto-generate branch name when entering ai_coding for the first time
    if to_column == ColumnName.AI_CODING.value:
        if not ticket.branch_name:
            slug = ticket.title.lower()
            slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
            slug = "-".join(slug.split()[:6])
            ticket.branch_name = f"feature/ticket-{ticket.ticket_number}-{slug}"
            logger.info("Auto-created branch name: %s", ticket.branch_name)

        # Track retries when sent back to ai_coding
        if from_column in (
            ColumnName.CODE_REVIEW.value,
            ColumnName.STAGING_VERIFICATION.value,
        ):
            ticket.retry_count += 1

    # Audit trail
    details: dict[str, Any] = {}
    if comment:
        details["comment"] = comment

    history = TicketHistory(
        ticket_id=ticket.id,
        actor_id=actor_id,
        actor_type="user",
        action="moved",
        from_column=from_column,
        to_column=to_column,
        details=details or None,
    )
    db.add(history)

    await db.flush()
    await db.refresh(ticket)

    logger.info(
        "Ticket %s moved: %s -> %s by user %s",
        ticket_id,
        from_column,
        to_column,
        actor_id,
    )

    # Publish real-time event
    try:
        from app.schemas.websocket import WSEventType
        from app.services.websocket_manager import ws_manager

        await ws_manager.broadcast_to_project(
            str(ticket.project_id),
            {
                "type": WSEventType.TICKET_MOVED,
                "data": {
                    "ticket_id": str(ticket.id),
                    "from_column": from_column,
                    "to_column": to_column,
                    "actor_id": str(actor_id),
                    "project_id": str(ticket.project_id),
                },
            },
        )
    except Exception as exc:
        logger.warning("Failed to broadcast ticket_moved event: %s", exc)

    # Dispatch AI pipeline tasks based on the column transition
    try:
        from app.services.pipeline_trigger import on_ticket_moved

        bg_task_id = await on_ticket_moved(
            db=db,
            ticket_id=ticket.id,
            from_column=from_column,
            to_column=to_column,
            project_id=ticket.project_id,
        )
        if bg_task_id:
            logger.info(
                "Dispatched background task %s for ticket %s (%s -> %s)",
                bg_task_id,
                ticket_id,
                from_column,
                to_column,
            )
    except Exception as exc:
        logger.warning("Failed to dispatch pipeline task: %s", exc)

    return ticket


async def get_board(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> dict[str, list[TicketResponse]]:
    """Return all tickets for *project_id* grouped by column name."""
    result = await db.execute(
        select(Ticket)
        .where(Ticket.project_id == project_id)
        .order_by(Ticket.position.asc(), Ticket.created_at.desc())
    )
    tickets = result.scalars().all()

    board: dict[str, list[TicketResponse]] = {col.value: [] for col in ColumnName}
    for ticket in tickets:
        col_key = (
            ticket.column_name.value
            if isinstance(ticket.column_name, ColumnName)
            else ticket.column_name
        )
        board[col_key].append(TicketResponse.model_validate(ticket))

    return board


async def reorder_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    new_position: int,
) -> Ticket:
    """Update the sort position of a ticket within its current column."""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    ticket.position = max(0, new_position)
    await db.flush()
    await db.refresh(ticket)

    logger.info("Ticket %s reordered to position %d", ticket_id, new_position)
    return ticket
