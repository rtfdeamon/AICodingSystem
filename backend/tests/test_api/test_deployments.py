"""Tests for deployment API endpoints, including RBAC negative tests."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.services.auth_service import create_access_token

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_project_and_ticket(client: AsyncClient, headers: dict) -> tuple[str, str]:
    """Create a project and ticket, returning (project_id, ticket_id)."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Deploy Test Project"},
        headers=headers,
    )
    project_id = proj_resp.json()["id"]

    ticket_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={
            "title": "Deploy ticket",
            "description": "For deployment testing",
            "priority": "P1",
        },
        headers=headers,
    )
    ticket_id = ticket_resp.json()["id"]
    return project_id, ticket_id


def _mock_deploy_result(deploy_status: str = "deployed"):
    """Return a mock DeployResult-like object."""
    from dataclasses import dataclass

    @dataclass
    class FakeResult:
        status: str
        url: str
        deploy_id: str
        environment: str

    return FakeResult(
        status=deploy_status,
        url="https://deploy.example.com/run/123",
        deploy_id=str(uuid.uuid4()),
        environment="staging",
    )


# ---------------------------------------------------------------------------
# Staging deploy tests
# ---------------------------------------------------------------------------


@patch("app.ci.deployer.deploy_staging")
async def test_deploy_staging_as_developer(
    mock_deploy,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    mock_deploy.return_value = _mock_deploy_result()
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    dev_user = await create_test_user(email="dev@deploy.com", role="developer")
    dev_token = create_access_token(dev_user.id, dev_user.role)
    dev_headers = {"Authorization": f"Bearer {dev_token}"}

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/deploy/staging",
        json={"branch": "main"},
        headers=dev_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["environment"] == "staging"


# ---------------------------------------------------------------------------
# Production deploy — RBAC negative tests (P0 requirement)
# ---------------------------------------------------------------------------


@patch("app.ci.deployer.deploy_production_canary")
async def test_deploy_production_as_pm_lead(
    mock_deploy,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """PM lead should be able to deploy to production."""
    mock_deploy.return_value = _mock_deploy_result()
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    pm_user = await create_test_user(email="pm@deploy.com", role="pm_lead")
    pm_token = create_access_token(pm_user.id, pm_user.role)
    pm_headers = {"Authorization": f"Bearer {pm_token}"}

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/deploy/production",
        json={"commit_sha": "abc123", "canary_pct": 10},
        headers=pm_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["environment"] == "production"


async def test_deploy_production_as_owner_forbidden(
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Owner should NOT be allowed to deploy to production (PM-only gate)."""
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    # auth_headers is for the default 'owner' role user
    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/deploy/production",
        json={"commit_sha": "abc123", "canary_pct": 10},
        headers=auth_headers,
    )
    assert resp.status_code == 403


async def test_deploy_production_as_developer_forbidden(
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Developer should NOT be allowed to deploy to production."""
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    dev_user = await create_test_user(email="dev2@deploy.com", role="developer")
    dev_token = create_access_token(dev_user.id, dev_user.role)
    dev_headers = {"Authorization": f"Bearer {dev_token}"}

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/deploy/production",
        json={"commit_sha": "abc123", "canary_pct": 10},
        headers=dev_headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Promote — RBAC negative tests
# ---------------------------------------------------------------------------


async def test_promote_as_owner_forbidden(
    async_client: AsyncClient,
    auth_headers,
) -> None:
    """Owner should NOT be allowed to promote canary (PM-only)."""
    fake_deployment_id = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/deployments/{fake_deployment_id}/promote",
        json={"new_percentage": 50},
        headers=auth_headers,
    )
    assert resp.status_code == 403


async def test_promote_as_developer_forbidden(
    async_client: AsyncClient,
    db_session,
    create_test_user,
) -> None:
    """Developer should NOT be allowed to promote canary."""
    dev_user = await create_test_user(email="dev3@deploy.com", role="developer")
    dev_token = create_access_token(dev_user.id, dev_user.role)
    dev_headers = {"Authorization": f"Bearer {dev_token}"}

    fake_deployment_id = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/deployments/{fake_deployment_id}/promote",
        json={"new_percentage": 50},
        headers=dev_headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# List deployments
# ---------------------------------------------------------------------------


async def test_list_deployments_empty(
    async_client: AsyncClient,
    auth_headers,
) -> None:
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)
    resp = await async_client.get(
        f"/api/v1/tickets/{ticket_id}/deployments",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Ticket not found
# ---------------------------------------------------------------------------


@patch("app.ci.deployer.deploy_staging")
async def test_deploy_staging_ticket_not_found(
    mock_deploy,
    async_client: AsyncClient,
    auth_headers,
) -> None:
    mock_deploy.return_value = _mock_deploy_result()
    fake_ticket = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/tickets/{fake_ticket}/deploy/staging",
        json={"branch": "main"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
