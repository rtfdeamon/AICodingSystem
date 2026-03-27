"""Tests for ticket history API endpoint."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.ticket import ColumnName, Priority, Ticket
from app.models.ticket_history import TicketHistory
from app.models.user import User
from app.services.auth_service import create_access_token, hash_password

pytestmark = pytest.mark.asyncio


async def _setup(db_session: AsyncSession) -> tuple[dict[str, str], Ticket]:
    """Create user, project, ticket and return (headers, ticket)."""
    user = User(
        id=uuid.uuid4(),
        email=f"history-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpass123"),
        full_name="History Tester",
        role="owner",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(user.id, user.role)
    headers = {"Authorization": f"Bearer {token}"}

    project = Project(
        id=uuid.uuid4(),
        name="History Test Project",
        slug=f"history-{uuid.uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.flush()

    ticket = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        ticket_number=1,
        title="Test Ticket",
        description="Test",
        column_name=ColumnName("backlog"),
        priority=Priority("P2"),
    )
    db_session.add(ticket)
    await db_session.flush()
    await db_session.refresh(ticket)

    return headers, ticket


async def test_list_ticket_history_empty(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Returns empty list when ticket has no history entries."""
    headers, ticket = await _setup(db_session)
    resp = await async_client.get(
        f"/api/v1/tickets/{ticket.id}/history",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_ticket_history_with_entries(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Returns history entries ordered newest first."""
    headers, ticket = await _setup(db_session)

    entry1 = TicketHistory(
        id=uuid.uuid4(),
        ticket_id=ticket.id,
        actor_type="user",
        action="created",
        details={"title": ticket.title},
    )
    entry2 = TicketHistory(
        id=uuid.uuid4(),
        ticket_id=ticket.id,
        actor_type="ai_agent",
        from_column="backlog",
        to_column="ai_planning",
        action="moved",
    )
    db_session.add(entry1)
    db_session.add(entry2)
    await db_session.flush()

    resp = await async_client.get(
        f"/api/v1/tickets/{ticket.id}/history",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["action"] in ("created", "moved")
    assert data[0]["ticket_id"] == str(ticket.id)


async def test_list_ticket_history_pagination(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Pagination limits results correctly."""
    headers, ticket = await _setup(db_session)

    for i in range(5):
        db_session.add(
            TicketHistory(
                id=uuid.uuid4(),
                ticket_id=ticket.id,
                actor_type="system",
                action=f"action_{i}",
            )
        )
    await db_session.flush()

    resp = await async_client.get(
        f"/api/v1/tickets/{ticket.id}/history?per_page=2&page=1",
        headers=headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_list_ticket_history_unauthorized(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Returns 403 without auth headers."""
    _, ticket = await _setup(db_session)
    resp = await async_client.get(f"/api/v1/tickets/{ticket.id}/history")
    assert resp.status_code in (401, 403)
