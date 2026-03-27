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
