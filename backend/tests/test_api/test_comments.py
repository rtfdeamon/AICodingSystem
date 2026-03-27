"""Tests for comment CRUD API endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.ticket import ColumnName, Priority, Ticket
from app.models.user import User
from app.services.auth_service import create_access_token, hash_password

pytestmark = pytest.mark.asyncio


async def _setup(db_session: AsyncSession) -> tuple[dict[str, str], str, str]:
    """Create a user, project, and ticket. Return (auth_headers, ticket_id, user_id)."""
    user = User(
        id=uuid.uuid4(),
        email=f"commenter-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("password123"),
        full_name="Comment Tester",
        role="owner",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    project = Project(
        id=uuid.uuid4(),
        name="Comment Project",
        slug=f"comment-proj-{uuid.uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.flush()

    ticket = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        ticket_number=1,
        title="A ticket with comments",
        description="desc",
        column_name=ColumnName("backlog"),
        priority=Priority("P2"),
    )
    db_session.add(ticket)
    await db_session.flush()

    token = create_access_token(user.id, user.role)
    headers = {"Authorization": f"Bearer {token}"}
    return headers, str(ticket.id), str(user.id)


# ------------------------------------------------------------------
# list_comments (line 33)
# ------------------------------------------------------------------


async def test_list_comments_empty(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /tickets/{id}/comments returns empty list when no comments exist."""
    headers, ticket_id, _ = await _setup(db_session)
    resp = await async_client.get(
        f"/api/v1/tickets/{ticket_id}/comments", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_comments_returns_comments(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /tickets/{id}/comments returns existing comments."""
    headers, ticket_id, _ = await _setup(db_session)

    # Create a comment first
    await async_client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        json={"body": "First comment"},
        headers=headers,
    )

    resp = await async_client.get(
        f"/api/v1/tickets/{ticket_id}/comments", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["body"] == "First comment"


# ------------------------------------------------------------------
# create_comment (lines 48-49)
# ------------------------------------------------------------------


async def test_create_comment(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /tickets/{id}/comments creates a comment and returns 201."""
    headers, ticket_id, _ = await _setup(db_session)

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        json={"body": "A new comment"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["body"] == "A new comment"
    assert body["ticket_id"] == ticket_id
    assert "id" in body


# ------------------------------------------------------------------
# update_comment (lines 60-61)
# ------------------------------------------------------------------


async def test_update_comment(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH /comments/{id} updates the comment body."""
    headers, ticket_id, _ = await _setup(db_session)

    # Create
    create_resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        json={"body": "Original body"},
        headers=headers,
    )
    comment_id = create_resp.json()["id"]

    # Update
    resp = await async_client.patch(
        f"/api/v1/comments/{comment_id}",
        json={"body": "Updated body"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["body"] == "Updated body"


# ------------------------------------------------------------------
# delete_comment (line 71)
# ------------------------------------------------------------------


async def test_delete_comment(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """DELETE /comments/{id} removes the comment and returns 204."""
    headers, ticket_id, _ = await _setup(db_session)

    # Create
    create_resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        json={"body": "To be deleted"},
        headers=headers,
    )
    comment_id = create_resp.json()["id"]

    # Delete
    resp = await async_client.delete(
        f"/api/v1/comments/{comment_id}",
        headers=headers,
    )
    assert resp.status_code == 204

    # Verify gone
    list_resp = await async_client.get(
        f"/api/v1/tickets/{ticket_id}/comments", headers=headers
    )
    assert len(list_resp.json()) == 0
