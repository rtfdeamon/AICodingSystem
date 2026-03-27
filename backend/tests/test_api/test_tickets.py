"""Tests for ticket CRUD endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.services.auth_service import create_access_token, hash_password

pytestmark = pytest.mark.asyncio


async def _register_and_create_project(db_session: AsyncSession) -> tuple[dict, str]:
    """Helper: create a user and project in the DB, return (headers, project_id)."""
    user = User(
        id=uuid.uuid4(),
        email=f"tickets-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("strongpassword123"),
        full_name="Ticket Tester",
        role="owner",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(user.id, user.role)
    headers = {"Authorization": f"Bearer {token}"}

    project = Project(
        id=uuid.uuid4(),
        name="Ticket Test Project",
        slug=f"ticket-test-{uuid.uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.flush()

    return headers, str(project.id)


async def test_create_ticket(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Creating a ticket returns 201 with the ticket data."""
    headers, project_id = await _register_and_create_project(db_session)

    resp = await async_client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={
            "title": "Implement login flow",
            "description": "Add OAuth support",
            "priority": "P1",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Implement login flow"
    assert body["priority"] == "P1"
    assert body["column_name"] == "backlog"


async def test_list_tickets(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Listing tickets returns a paginated response."""
    headers, project_id = await _register_and_create_project(db_session)

    # Create two tickets
    for i in range(2):
        await async_client.post(
            f"/api/v1/projects/{project_id}/tickets",
            json={"title": f"Ticket {i}"},
            headers=headers,
        )

    resp = await async_client.get(
        f"/api/v1/projects/{project_id}/tickets",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


async def test_get_ticket(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Getting a single ticket by ID returns 200."""
    headers, project_id = await _register_and_create_project(db_session)

    create_resp = await async_client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={"title": "Get me"},
        headers=headers,
    )
    ticket_id = create_resp.json()["id"]

    resp = await async_client.get(
        f"/api/v1/tickets/{ticket_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Get me"


async def test_update_ticket(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Updating a ticket changes its fields."""
    headers, project_id = await _register_and_create_project(db_session)

    create_resp = await async_client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={"title": "Original title"},
        headers=headers,
    )
    ticket_id = create_resp.json()["id"]

    resp = await async_client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"title": "Updated title", "priority": "P0"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Updated title"
    assert body["priority"] == "P0"


async def test_delete_ticket(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Deleting a ticket returns 204."""
    headers, project_id = await _register_and_create_project(db_session)

    create_resp = await async_client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={"title": "Delete me"},
        headers=headers,
    )
    ticket_id = create_resp.json()["id"]

    resp = await async_client.delete(
        f"/api/v1/tickets/{ticket_id}",
        headers=headers,
    )
    assert resp.status_code == 204
