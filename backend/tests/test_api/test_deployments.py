"""Tests for deployment API endpoints, including RBAC negative tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment import (
    DeployEnvironment,
    Deployment,
    DeployStatus,
    DeployType,
)
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


def _mock_health_status(healthy: bool = True):
    """Return a mock HealthStatus-like object."""

    @dataclass
    class FakeHealth:
        healthy: bool
        error_rate: float
        latency_p50: int
        latency_p95: int
        latency_p99: int
        uptime_pct: float
        details: dict | None

    return FakeHealth(
        healthy=healthy,
        error_rate=0.1 if healthy else 5.0,
        latency_p50=45,
        latency_p95=120,
        latency_p99=350 if healthy else 2500,
        uptime_pct=99.9 if healthy else 95.0,
        details={"source": "test"},
    )


async def _create_deployment_record(
    db: AsyncSession,
    ticket_id: str,
    *,
    environment: DeployEnvironment = DeployEnvironment.PRODUCTION,
    deploy_type: DeployType = DeployType.CANARY,
    status: DeployStatus = DeployStatus.DEPLOYED,
    canary_pct: int | None = 10,
    initiated_by: uuid.UUID | None = None,
    commit_sha: str = "abc123",
) -> Deployment:
    """Insert a Deployment row directly and return it."""
    dep = Deployment(
        id=uuid.uuid4(),
        ticket_id=uuid.UUID(ticket_id),
        environment=environment,
        deploy_type=deploy_type,
        status=status,
        canary_pct=canary_pct,
        initiated_by=initiated_by,
        commit_sha=commit_sha,
        build_url="https://ci.example.com/build/1",
        created_at=datetime.now(UTC),
    )
    db.add(dep)
    await db.flush()
    await db.refresh(dep)
    return dep


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


async def test_deploy_production_ticket_not_found(
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Production deploy should 404 when ticket does not exist."""
    pm_user = await create_test_user(email="pm_404@deploy.com", role="pm_lead")
    pm_token = create_access_token(pm_user.id, pm_user.role)
    pm_headers = {"Authorization": f"Bearer {pm_token}"}

    fake_ticket = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/tickets/{fake_ticket}/deploy/production",
        json={"commit_sha": "abc123", "canary_pct": 10},
        headers=pm_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Staging deploy — with commit_sha supplied
# ---------------------------------------------------------------------------


@patch("app.ci.deployer.deploy_staging")
async def test_deploy_staging_with_commit_sha(
    mock_deploy,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Staging deploy should accept an explicit commit_sha."""
    mock_deploy.return_value = _mock_deploy_result()
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    dev_user = await create_test_user(email="dev_sha@deploy.com", role="developer")
    dev_token = create_access_token(dev_user.id, dev_user.role)
    dev_headers = {"Authorization": f"Bearer {dev_token}"}

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/deploy/staging",
        json={"branch": "feature-x", "commit_sha": "deadbeef"},
        headers=dev_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["commit_sha"] == "deadbeef"
    assert data["deploy_type"] == "full"


# ---------------------------------------------------------------------------
# Staging deploy — deploying (not yet deployed) status
# ---------------------------------------------------------------------------


@patch("app.ci.deployer.deploy_staging")
async def test_deploy_staging_deploying_status(
    mock_deploy,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """When deployer returns 'deploying', completed_at should be None."""
    mock_deploy.return_value = _mock_deploy_result(deploy_status="deploying")
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    dev_user = await create_test_user(email="dev_dep@deploy.com", role="developer")
    dev_token = create_access_token(dev_user.id, dev_user.role)
    dev_headers = {"Authorization": f"Bearer {dev_token}"}

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/deploy/staging",
        json={"branch": "main"},
        headers=dev_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "deploying"
    assert data["completed_at"] is None


# ---------------------------------------------------------------------------
# Production deploy — deploying (not yet deployed) status
# ---------------------------------------------------------------------------


@patch("app.ci.deployer.deploy_production_canary")
async def test_deploy_production_deploying_status(
    mock_deploy,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """When deployer returns 'deploying', completed_at should be None."""
    mock_deploy.return_value = _mock_deploy_result(deploy_status="deploying")
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    pm_user = await create_test_user(email="pm_deploying@deploy.com", role="pm_lead")
    pm_token = create_access_token(pm_user.id, pm_user.role)
    pm_headers = {"Authorization": f"Bearer {pm_token}"}

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/deploy/production",
        json={"commit_sha": "abc123", "canary_pct": 25},
        headers=pm_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "deploying"
    assert data["canary_pct"] == 25
    assert data["completed_at"] is None


# ---------------------------------------------------------------------------
# List deployments — with results
# ---------------------------------------------------------------------------


@patch("app.ci.deployer.deploy_staging")
async def test_list_deployments_with_results(
    mock_deploy,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """List should return deployments after one has been created."""
    mock_deploy.return_value = _mock_deploy_result()
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    # Create a deployment first
    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/deploy/staging",
        json={"branch": "main"},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    resp = await async_client.get(
        f"/api/v1/tickets/{ticket_id}/deployments",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["ticket_id"] == ticket_id


# ---------------------------------------------------------------------------
# Rollback tests
# ---------------------------------------------------------------------------


@patch("app.ci.deployer.rollback")
async def test_rollback_deployment_success(
    mock_rollback,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Rollback a deployed deployment should succeed."""
    mock_rollback.return_value = _mock_deploy_result(deploy_status="rolled_back")
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    dep = await _create_deployment_record(
        db_session,
        ticket_id,
        status=DeployStatus.DEPLOYED,
    )

    resp = await async_client.post(
        f"/api/v1/deployments/{dep.id}/rollback",
        json={"reason": "High error rate detected"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rolled_back"
    assert data["rollback_reason"] == "High error rate detected"
    assert data["completed_at"] is not None


@patch("app.ci.deployer.rollback")
async def test_rollback_deploying_deployment(
    mock_rollback,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Rollback a deployment in 'deploying' state should also succeed."""
    mock_rollback.return_value = _mock_deploy_result(deploy_status="rolled_back")
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    dep = await _create_deployment_record(
        db_session,
        ticket_id,
        status=DeployStatus.DEPLOYING,
    )

    resp = await async_client.post(
        f"/api/v1/deployments/{dep.id}/rollback",
        json={"reason": "Bad metrics"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rolled_back"


async def test_rollback_not_found(
    async_client: AsyncClient,
    auth_headers,
) -> None:
    """Rollback a nonexistent deployment should 404."""
    fake_id = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/deployments/{fake_id}/rollback",
        json={"reason": "Does not exist"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_rollback_already_rolled_back(
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Rollback a deployment that is already rolled_back should 422."""
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    dep = await _create_deployment_record(
        db_session,
        ticket_id,
        status=DeployStatus.ROLLED_BACK,
    )

    resp = await async_client.post(
        f"/api/v1/deployments/{dep.id}/rollback",
        json={"reason": "Try again"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "rolled_back" in resp.json()["detail"].lower()


async def test_rollback_failed_deployment(
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Rollback a failed deployment should 422."""
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    dep = await _create_deployment_record(
        db_session,
        ticket_id,
        status=DeployStatus.FAILED,
    )

    resp = await async_client.post(
        f"/api/v1/deployments/{dep.id}/rollback",
        json={"reason": "Already failed"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "failed" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Promote tests
# ---------------------------------------------------------------------------


@patch("app.ci.deployer.promote_canary")
async def test_promote_canary_success(
    mock_promote,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """PM lead can promote a canary deployment to a higher percentage."""
    mock_promote.return_value = _mock_deploy_result(deploy_status="deploying")
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    pm_user = await create_test_user(email="pm_promote@deploy.com", role="pm_lead")
    pm_token = create_access_token(pm_user.id, pm_user.role)
    pm_headers = {"Authorization": f"Bearer {pm_token}"}

    dep = await _create_deployment_record(
        db_session,
        ticket_id,
        deploy_type=DeployType.CANARY,
        status=DeployStatus.DEPLOYED,
        canary_pct=10,
    )

    resp = await async_client.post(
        f"/api/v1/deployments/{dep.id}/promote",
        json={"new_percentage": 50},
        headers=pm_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["canary_pct"] == 50
    assert data["completed_at"] is None  # not 100%, so not completed


@patch("app.ci.deployer.promote_canary")
async def test_promote_canary_to_100_sets_completed(
    mock_promote,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Promoting to 100% should set completed_at."""
    mock_promote.return_value = _mock_deploy_result(deploy_status="deployed")
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    pm_user = await create_test_user(email="pm_100@deploy.com", role="pm_lead")
    pm_token = create_access_token(pm_user.id, pm_user.role)
    pm_headers = {"Authorization": f"Bearer {pm_token}"}

    dep = await _create_deployment_record(
        db_session,
        ticket_id,
        deploy_type=DeployType.CANARY,
        status=DeployStatus.DEPLOYING,
        canary_pct=50,
    )

    resp = await async_client.post(
        f"/api/v1/deployments/{dep.id}/promote",
        json={"new_percentage": 100},
        headers=pm_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["canary_pct"] == 100
    assert data["completed_at"] is not None


async def test_promote_not_found(
    async_client: AsyncClient,
    db_session,
    create_test_user,
) -> None:
    """Promote a nonexistent deployment should 404."""
    pm_user = await create_test_user(email="pm_nf@deploy.com", role="pm_lead")
    pm_token = create_access_token(pm_user.id, pm_user.role)
    pm_headers = {"Authorization": f"Bearer {pm_token}"}

    fake_id = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/deployments/{fake_id}/promote",
        json={"new_percentage": 50},
        headers=pm_headers,
    )
    assert resp.status_code == 404


async def test_promote_non_canary_deployment(
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Promoting a full (non-canary) deployment should 422."""
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    pm_user = await create_test_user(email="pm_full@deploy.com", role="pm_lead")
    pm_token = create_access_token(pm_user.id, pm_user.role)
    pm_headers = {"Authorization": f"Bearer {pm_token}"}

    dep = await _create_deployment_record(
        db_session,
        ticket_id,
        deploy_type=DeployType.FULL,
        status=DeployStatus.DEPLOYED,
        canary_pct=None,
    )

    resp = await async_client.post(
        f"/api/v1/deployments/{dep.id}/promote",
        json={"new_percentage": 50},
        headers=pm_headers,
    )
    assert resp.status_code == 422
    assert "canary" in resp.json()["detail"].lower()


async def test_promote_rolled_back_deployment(
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Promoting a rolled-back canary should 422."""
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    pm_user = await create_test_user(email="pm_rb@deploy.com", role="pm_lead")
    pm_token = create_access_token(pm_user.id, pm_user.role)
    pm_headers = {"Authorization": f"Bearer {pm_token}"}

    dep = await _create_deployment_record(
        db_session,
        ticket_id,
        deploy_type=DeployType.CANARY,
        status=DeployStatus.ROLLED_BACK,
        canary_pct=10,
    )

    resp = await async_client.post(
        f"/api/v1/deployments/{dep.id}/promote",
        json={"new_percentage": 50},
        headers=pm_headers,
    )
    assert resp.status_code == 422
    assert "rolled_back" in resp.json()["detail"].lower()


async def test_promote_failed_deployment(
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Promoting a failed canary should 422."""
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    pm_user = await create_test_user(email="pm_fail@deploy.com", role="pm_lead")
    pm_token = create_access_token(pm_user.id, pm_user.role)
    pm_headers = {"Authorization": f"Bearer {pm_token}"}

    dep = await _create_deployment_record(
        db_session,
        ticket_id,
        deploy_type=DeployType.CANARY,
        status=DeployStatus.FAILED,
        canary_pct=10,
    )

    resp = await async_client.post(
        f"/api/v1/deployments/{dep.id}/promote",
        json={"new_percentage": 50},
        headers=pm_headers,
    )
    assert resp.status_code == 422
    assert "failed" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------


@patch("app.ci.deployer.check_deploy_health")
async def test_health_check_success(
    mock_health,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Health check should return metrics and persist snapshot."""
    mock_health.return_value = _mock_health_status(healthy=True)
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    dep = await _create_deployment_record(
        db_session,
        ticket_id,
        status=DeployStatus.DEPLOYED,
    )

    resp = await async_client.get(
        f"/api/v1/deployments/{dep.id}/health",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["healthy"] is True
    assert data["error_rate"] == 0.1
    assert data["latency_p50"] == 45
    assert data["latency_p95"] == 120
    assert data["latency_p99"] == 350
    assert data["uptime_pct"] == 99.9
    assert data["details"] == {"source": "test"}


@patch("app.ci.deployer.check_deploy_health")
async def test_health_check_unhealthy(
    mock_health,
    async_client: AsyncClient,
    db_session,
    create_test_user,
    auth_headers,
) -> None:
    """Health check should return unhealthy metrics."""
    mock_health.return_value = _mock_health_status(healthy=False)
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    dep = await _create_deployment_record(
        db_session,
        ticket_id,
        status=DeployStatus.DEPLOYED,
    )

    resp = await async_client.get(
        f"/api/v1/deployments/{dep.id}/health",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["healthy"] is False
    assert data["error_rate"] == 5.0


async def test_health_check_not_found(
    async_client: AsyncClient,
    auth_headers,
) -> None:
    """Health check for nonexistent deployment should 404."""
    fake_id = str(uuid.uuid4())
    resp = await async_client.get(
        f"/api/v1/deployments/{fake_id}/health",
        headers=auth_headers,
    )
    assert resp.status_code == 404
