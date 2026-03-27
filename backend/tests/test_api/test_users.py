"""Tests for user management endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.auth_service import create_access_token, hash_password

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_user(
    db_session: AsyncSession,
    *,
    role: str = "developer",
    email: str | None = None,
) -> tuple[User, dict[str, str]]:
    """Create a user in the DB and return (user, auth_headers)."""
    user = User(
        id=uuid.uuid4(),
        email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("testpassword123"),
        full_name="Test Person",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    token = create_access_token(user.id, user.role)
    headers = {"Authorization": f"Bearer {token}"}
    return user, headers


# ---------------------------------------------------------------------------
# List users
# ---------------------------------------------------------------------------


async def test_list_users(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Owner can list users and sees at least themselves."""
    response = await async_client.get("/api/v1/users", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1


async def test_list_users_requires_auth(
    async_client: AsyncClient,
) -> None:
    """Listing users without auth returns 401."""
    response = await async_client.get("/api/v1/users")
    assert response.status_code == 401


async def test_list_users_forbidden_for_developer(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A developer role cannot list users (requires pm_lead or owner)."""
    _, dev_headers = await _make_user(db_session, role="developer")

    response = await async_client.get("/api/v1/users", headers=dev_headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Get user by id
# ---------------------------------------------------------------------------


async def test_get_user_by_id(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    create_test_user,
) -> None:
    """Fetching a user by id returns their public profile."""
    user = await create_test_user(
        email=f"lookup-{uuid.uuid4().hex[:8]}@example.com",
    )

    response = await async_client.get(
        f"/api/v1/users/{user.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["email"] == user.email


async def test_get_user_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Fetching a non-existent user returns 404."""
    fake_id = uuid.uuid4()

    response = await async_client.get(
        f"/api/v1/users/{fake_id}",
        headers=auth_headers,
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update user role
# ---------------------------------------------------------------------------


async def test_update_user_role(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Owner can change another user's role via the dedicated endpoint."""
    target, _ = await _make_user(db_session, role="developer")

    response = await async_client.patch(
        f"/api/v1/users/{target.id}/role",
        headers=auth_headers,
        json={"role": "pm_lead"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "pm_lead"


async def test_update_user_role_missing_field(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Calling the role endpoint without 'role' field returns 400."""
    target, _ = await _make_user(db_session, role="developer")

    response = await async_client.patch(
        f"/api/v1/users/{target.id}/role",
        headers=auth_headers,
        json={"full_name": "New Name"},
    )

    assert response.status_code == 400


async def test_update_user_role_forbidden_for_developer(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A developer cannot change roles."""
    dev, dev_headers = await _make_user(db_session, role="developer")

    response = await async_client.patch(
        f"/api/v1/users/{dev.id}/role",
        headers=dev_headers,
        json={"role": "owner"},
    )

    assert response.status_code == 403


async def test_change_role_user_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Changing role for a non-existent user returns 404."""
    fake_id = uuid.uuid4()

    response = await async_client.patch(
        f"/api/v1/users/{fake_id}/role",
        headers=auth_headers,
        json={"role": "developer"},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update user (PATCH /{user_id})
# ---------------------------------------------------------------------------


async def test_update_self(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A user can update their own profile."""
    user, headers = await _make_user(db_session, role="developer")

    response = await async_client.patch(
        f"/api/v1/users/{user.id}",
        headers=headers,
        json={"full_name": "Updated Name"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Updated Name"


async def test_update_self_avatar(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A user can update their avatar_url."""
    user, headers = await _make_user(db_session, role="developer")

    response = await async_client.patch(
        f"/api/v1/users/{user.id}",
        headers=headers,
        json={"avatar_url": "https://example.com/avatar.png"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["avatar_url"] == "https://example.com/avatar.png"


async def test_admin_can_update_other_user(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Owner can update another user's profile."""
    target, _ = await _make_user(db_session, role="developer")

    response = await async_client.patch(
        f"/api/v1/users/{target.id}",
        headers=auth_headers,
        json={"full_name": "Admin Changed"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Admin Changed"


async def test_developer_cannot_update_other_user(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A developer cannot update another user's profile."""
    dev, dev_headers = await _make_user(db_session, role="developer")
    target, _ = await _make_user(db_session, role="developer")

    response = await async_client.patch(
        f"/api/v1/users/{target.id}",
        headers=dev_headers,
        json={"full_name": "Hacked"},
    )

    assert response.status_code == 403


async def test_update_user_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Updating a non-existent user returns 404."""
    fake_id = uuid.uuid4()

    response = await async_client.patch(
        f"/api/v1/users/{fake_id}",
        headers=auth_headers,
        json={"full_name": "Ghost"},
    )

    assert response.status_code == 404


async def test_developer_cannot_change_own_role(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A developer cannot promote themselves via the update endpoint."""
    dev, dev_headers = await _make_user(db_session, role="developer")

    response = await async_client.patch(
        f"/api/v1/users/{dev.id}",
        headers=dev_headers,
        json={"role": "owner"},
    )

    assert response.status_code == 403


async def test_admin_can_change_role_via_update(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """An owner can change another user's role via the general update endpoint."""
    target, _ = await _make_user(db_session, role="developer")

    response = await async_client.patch(
        f"/api/v1/users/{target.id}",
        headers=auth_headers,
        json={"role": "pm_lead"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "pm_lead"


async def test_update_no_fields(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Updating with an empty body is a valid no-op."""
    user, headers = await _make_user(db_session, role="developer")

    response = await async_client.patch(
        f"/api/v1/users/{user.id}",
        headers=headers,
        json={},
    )

    assert response.status_code == 200


async def test_list_users_filter_inactive(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Listing users with is_active=false returns only inactive users."""
    response = await async_client.get(
        "/api/v1/users",
        headers=auth_headers,
        params={"is_active": "false"},
    )

    assert response.status_code == 200
    body = response.json()
    # All returned users should be inactive
    for u in body:
        assert u["is_active"] is False


async def test_pm_lead_can_list_users(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A pm_lead can list users."""
    _, pm_headers = await _make_user(db_session, role="pm_lead")

    response = await async_client.get("/api/v1/users", headers=pm_headers)
    assert response.status_code == 200


async def test_pm_lead_can_change_role(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A pm_lead can change another user's role."""
    _, pm_headers = await _make_user(db_session, role="pm_lead")
    target, _ = await _make_user(db_session, role="developer")

    response = await async_client.patch(
        f"/api/v1/users/{target.id}/role",
        headers=pm_headers,
        json={"role": "ai_agent"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ai_agent"
