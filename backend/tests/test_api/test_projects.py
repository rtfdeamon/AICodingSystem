"""Tests for projects API endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.services.auth_service import create_access_token

pytestmark = pytest.mark.asyncio


async def test_create_project(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await async_client.post(
        "/api/v1/projects",
        json={"name": "My New Project", "description": "A fresh project"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My New Project"
    assert data["description"] == "A fresh project"
    assert "id" in data
    assert "created_at" in data


async def test_create_project_unauthenticated(async_client: AsyncClient) -> None:
    resp = await async_client.post(
        "/api/v1/projects",
        json={"name": "No Auth"},
    )
    assert resp.status_code in (401, 403)


async def test_list_projects(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    # Create two projects first
    await async_client.post(
        "/api/v1/projects",
        json={"name": "Project A"},
        headers=auth_headers,
    )
    await async_client.post(
        "/api/v1/projects",
        json={"name": "Project B"},
        headers=auth_headers,
    )

    resp = await async_client.get("/api/v1/projects", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2


async def test_get_project_by_id(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    create_resp = await async_client.post(
        "/api/v1/projects",
        json={"name": "Fetch Me"},
        headers=auth_headers,
    )
    project_id = create_resp.json()["id"]

    resp = await async_client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Fetch Me"


async def test_get_project_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.get(f"/api/v1/projects/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


async def test_update_project(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    create_resp = await async_client.post(
        "/api/v1/projects",
        json={"name": "Before Update"},
        headers=auth_headers,
    )
    project_id = create_resp.json()["id"]

    resp = await async_client.put(
        f"/api/v1/projects/{project_id}",
        json={"name": "After Update", "description": "Updated desc"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "After Update"
    assert resp.json()["description"] == "Updated desc"


async def test_delete_project_owner(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create_resp = await async_client.post(
        "/api/v1/projects",
        json={"name": "To Delete"},
        headers=auth_headers,
    )
    project_id = create_resp.json()["id"]

    resp = await async_client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Verify it's gone
    resp2 = await async_client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert resp2.status_code == 404


async def test_delete_project_developer_forbidden(
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers: dict[str, str],
) -> None:
    # Create project as owner
    create_resp = await async_client.post(
        "/api/v1/projects",
        json={"name": "Protected"},
        headers=auth_headers,
    )
    project_id = create_resp.json()["id"]

    # Try to delete as developer
    dev_user = await create_test_user(email="dev@test.com", role="developer")
    dev_token = create_access_token(dev_user.id, dev_user.role)
    dev_headers = {"Authorization": f"Bearer {dev_token}"}

    resp = await async_client.delete(f"/api/v1/projects/{project_id}", headers=dev_headers)
    assert resp.status_code == 403
