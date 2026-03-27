"""Tests for file attachment endpoints."""

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


async def _setup_ticket(db_session: AsyncSession) -> tuple[dict[str, str], Ticket, User]:
    """Create a user, project, and ticket. Return (headers, ticket, user)."""
    user = User(
        id=uuid.uuid4(),
        email=f"attach-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("securepassword123"),
        full_name="Attachment Tester",
        role="owner",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    project = Project(
        id=uuid.uuid4(),
        name="Attach Project",
        slug=f"attach-{uuid.uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.flush()

    ticket = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        ticket_number=1,
        title="Attachment Ticket",
        description="For testing attachments",
        column_name=ColumnName("backlog"),
        priority=Priority("P2"),
    )
    db_session.add(ticket)
    await db_session.flush()
    await db_session.refresh(ticket)

    token = create_access_token(user.id, user.role)
    headers = {"Authorization": f"Bearer {token}"}
    return headers, ticket, user


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


async def test_upload_attachment(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Uploading a file returns 201 with attachment metadata."""
    headers, ticket, _ = await _setup_ticket(db_session)

    response = await async_client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers=headers,
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "test.txt"
    assert body["content_type"] == "text/plain"
    assert body["file_size"] == len(b"hello world")
    assert body["ticket_id"] == str(ticket.id)


async def test_upload_requires_auth(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Upload without auth token returns 401."""
    _, ticket, _ = await _setup_ticket(db_session)

    response = await async_client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        files={"file": ("test.txt", b"data", "text/plain")},
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_attachments_empty(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Listing attachments on a ticket with none returns an empty list."""
    headers, ticket, _ = await _setup_ticket(db_session)

    response = await async_client.get(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_attachments_with_data(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """After uploading a file, listing returns it."""
    headers, ticket, _ = await _setup_ticket(db_session)

    # Upload a file first
    await async_client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers=headers,
        files={"file": ("report.pdf", b"pdf-bytes", "application/pdf")},
    )

    response = await async_client.get(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["filename"] == "report.pdf"


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


async def test_download_attachment_not_found(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Downloading a non-existent attachment returns 404."""
    headers, _, _ = await _setup_ticket(db_session)
    fake_id = uuid.uuid4()

    response = await async_client.get(
        f"/api/v1/attachments/{fake_id}/download",
        headers=headers,
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def test_delete_attachment_not_found(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Deleting a non-existent attachment returns 404."""
    headers, _, _ = await _setup_ticket(db_session)
    fake_id = uuid.uuid4()

    response = await async_client.delete(
        f"/api/v1/attachments/{fake_id}",
        headers=headers,
    )

    assert response.status_code == 404


async def test_delete_attachment_forbidden_wrong_user(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A user who is neither the uploader nor an owner cannot delete."""
    headers, ticket, _ = await _setup_ticket(db_session)

    # Upload as the owner user
    upload_resp = await async_client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers=headers,
        files={"file": ("secret.txt", b"secret", "text/plain")},
    )
    assert upload_resp.status_code == 201
    attachment_id = upload_resp.json()["id"]

    # Create a different user with 'developer' role (not owner, not uploader)
    other_user = User(
        id=uuid.uuid4(),
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("otherpassword123"),
        full_name="Other User",
        role="developer",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.flush()

    other_token = create_access_token(other_user.id, other_user.role)
    other_headers = {"Authorization": f"Bearer {other_token}"}

    response = await async_client.delete(
        f"/api/v1/attachments/{attachment_id}",
        headers=other_headers,
    )

    assert response.status_code == 403
