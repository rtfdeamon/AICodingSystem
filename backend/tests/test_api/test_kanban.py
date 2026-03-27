"""Tests for Kanban board endpoints: get board, move ticket, RBAC, reorder."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.services.auth_service import create_access_token, hash_password

pytestmark = pytest.mark.asyncio


async def _setup_user_project_ticket(
    client: AsyncClient,
    db_session: AsyncSession,
    role: str = "owner",
    column: str = "backlog",
    description: str = "Has a description",
) -> tuple[dict, str, str]:
    """Helper: create user, project & ticket, return (headers, project_id, ticket_id)."""
    user = User(
        id=uuid.uuid4(),
        email=f"kanban-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("strongpassword123"),
        full_name="Kanban Tester",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(user.id, user.role)
    headers = {"Authorization": f"Bearer {token}"}

    project = Project(
        id=uuid.uuid4(),
        name="Kanban Project",
        slug=f"kanban-{uuid.uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.flush()

    project_id = str(project.id)

    ticket_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={
            "title": "Kanban test ticket",
            "description": description,
        },
        headers=headers,
    )
    ticket_id = ticket_resp.json()["id"]

    return headers, project_id, ticket_id


async def test_get_board(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Getting the board returns all columns with tickets grouped correctly."""
    headers, project_id, _ticket_id = await _setup_user_project_ticket(async_client, db_session)

    resp = await async_client.get(
        f"/api/v1/projects/{project_id}/board",
        headers=headers,
    )
    assert resp.status_code == 200
    board = resp.json()

    # Board should have all 8 columns
    expected_columns = {
        "backlog",
        "ai_planning",
        "plan_review",
        "ai_coding",
        "code_review",
        "staging",
        "staging_verification",
        "production",
    }
    assert "columns" in board
    assert "project_id" in board
    assert set(board["columns"].keys()) == expected_columns

    # The ticket we created should be in backlog
    assert len(board["columns"]["backlog"]) == 1
    assert board["columns"]["backlog"][0]["title"] == "Kanban test ticket"


async def test_move_ticket_valid(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Moving a ticket through a valid transition succeeds."""
    headers, project_id, ticket_id = await _setup_user_project_ticket(async_client, db_session)

    # backlog -> ai_planning (owner role, description is set)
    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/move",
        json={"to_column": "ai_planning"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["column_name"] == "ai_planning"


async def test_move_ticket_invalid_transition(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Moving a ticket through an invalid transition returns 422."""
    headers, project_id, ticket_id = await _setup_user_project_ticket(async_client, db_session)

    # backlog -> production is not a valid direct transition
    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/move",
        json={"to_column": "production"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "not allowed" in resp.json()["detail"].lower()


async def test_move_ticket_rbac_forbidden(async_client: AsyncClient, db_session) -> None:
    """A developer cannot move a ticket to production (only pm_lead/owner can).

    This test validates the RBAC enforcement at the service layer by
    creating a user with 'developer' role directly in the database and
    attempting a forbidden transition.
    """
    from app.models.ticket import ColumnName, Ticket

    # Create developer user directly
    dev_user = User(
        id=uuid.uuid4(),
        email=f"dev-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("password123"),
        full_name="Developer",
        role="developer",
        is_active=True,
    )
    db_session.add(dev_user)
    await db_session.flush()

    # Create project
    project = Project(
        id=uuid.uuid4(),
        name="RBAC Project",
        slug=f"rbac-{uuid.uuid4().hex[:8]}",
        created_by=dev_user.id,
    )
    db_session.add(project)
    await db_session.flush()

    # Create a ticket in staging_verification
    ticket = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        ticket_number=1,
        title="RBAC test",
        description="Testing RBAC",
        column_name=ColumnName.STAGING_VERIFICATION,
    )
    db_session.add(ticket)
    await db_session.flush()

    token = create_access_token(dev_user.id, dev_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # developer trying staging_verification -> production should fail
    resp = await async_client.post(
        f"/api/v1/tickets/{ticket.id}/move",
        json={"to_column": "production"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "role" in resp.json()["detail"].lower()


async def test_reorder_ticket(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Changing a ticket's position updates its sort order."""
    headers, project_id, ticket_id = await _setup_user_project_ticket(async_client, db_session)

    resp = await async_client.patch(
        f"/api/v1/tickets/{ticket_id}/position",
        json={"position": 5},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["position"] == 5
