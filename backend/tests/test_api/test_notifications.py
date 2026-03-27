"""Tests for app.api.v1.notifications — list, mark-read, count endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationChannel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_notification(
    user_id: uuid.UUID,
    *,
    title: str = "Test notification",
    body: str = "Some body text",
    is_read: bool = False,
    ticket_id: uuid.UUID | None = None,
) -> Notification:
    """Create an unsaved Notification instance."""
    return Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        ticket_id=ticket_id,
        channel=NotificationChannel.IN_APP,
        title=title,
        body=body,
        is_read=is_read,
        sent_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestNotifications:
    async def test_list_notifications_empty(self, async_client, auth_headers):
        """Listing notifications for a user with none should return an empty list."""
        resp = await async_client.get("/api/v1/notifications", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_notifications_with_data(
        self, async_client, auth_headers, db_session: AsyncSession, create_test_user
    ):
        """Listing notifications should return created notifications."""
        # The auth_headers fixture already created a user; we need that user's id.
        # Fetch it by making a request first to confirm auth works, then create
        # notifications for the same user.  The auth_headers fixture uses
        # create_test_user() with default email, so we look up that user.
        from sqlalchemy import select

        from app.models.user import User

        result = await db_session.execute(select(User).where(User.email == "testuser@example.com"))
        user = result.scalar_one()

        n1 = _make_notification(user.id, title="First")
        n2 = _make_notification(user.id, title="Second")
        db_session.add_all([n1, n2])
        await db_session.flush()

        resp = await async_client.get("/api/v1/notifications", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_unread_count_zero(self, async_client, auth_headers):
        """Unread count for a user with no notifications should be 0."""
        resp = await async_client.get("/api/v1/notifications/unread-count", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 0

    async def test_mark_read_not_found(self, async_client, auth_headers):
        """Marking a non-existent notification should return 404."""
        fake_id = uuid.uuid4()
        resp = await async_client.patch(
            f"/api/v1/notifications/{fake_id}/read", headers=auth_headers
        )
        assert resp.status_code == 404

    async def test_mark_all_read(self, async_client, auth_headers, db_session: AsyncSession):
        """POST /notifications/read-all should mark all unread notifications as read."""
        from sqlalchemy import select

        from app.models.user import User

        result = await db_session.execute(select(User).where(User.email == "testuser@example.com"))
        user = result.scalar_one()

        n1 = _make_notification(user.id, title="A", is_read=False)
        n2 = _make_notification(user.id, title="B", is_read=False)
        n3 = _make_notification(user.id, title="C", is_read=True)
        db_session.add_all([n1, n2, n3])
        await db_session.flush()

        resp = await async_client.post("/api/v1/notifications/read-all", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 2

        # Verify unread count is now 0
        count_resp = await async_client.get(
            "/api/v1/notifications/unread-count", headers=auth_headers
        )
        assert count_resp.json()["unread_count"] == 0

    async def test_list_notifications_unread_only(
        self, async_client, auth_headers, db_session: AsyncSession
    ):
        """Filtering with unread_only=true should exclude read notifications."""
        from sqlalchemy import select

        from app.models.user import User

        result = await db_session.execute(select(User).where(User.email == "testuser@example.com"))
        user = result.scalar_one()

        n_read = _make_notification(user.id, title="Read", is_read=True)
        n_unread = _make_notification(user.id, title="Unread", is_read=False)
        db_session.add_all([n_read, n_unread])
        await db_session.flush()

        resp = await async_client.get(
            "/api/v1/notifications", params={"unread_only": "true"}, headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Unread"

    async def test_list_notifications_requires_auth(self, async_client):
        """Requesting notifications without auth should fail."""
        resp = await async_client.get("/api/v1/notifications")
        # Expect 401 or 403
        assert resp.status_code in (401, 403)
