"""Tests for the CI deployer module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.ci.deployer import (
    DeployResult,
    HealthStatus,
    check_deploy_health,
    deploy_production_canary,
    deploy_staging,
    promote_canary,
    rollback,
)

pytestmark = pytest.mark.asyncio


# ── Dataclass defaults ────────────────────────────────────────────────


def test_deploy_result() -> None:
    r = DeployResult(
        status="deployed", url="https://example.com", deploy_id="abc", environment="staging"
    )
    assert r.status == "deployed"


def test_health_status_defaults() -> None:
    h = HealthStatus(
        healthy=True,
        error_rate=0.0,
        latency_p50=10,
        latency_p95=50,
        latency_p99=100,
        uptime_pct=99.9,
    )
    assert h.healthy is True
    assert h.details is None


# ── deploy_staging ────────────────────────────────────────────────────


@patch("app.ci.deployer.trigger_workflow", new_callable=AsyncMock)
async def test_deploy_staging_success(mock_trigger: AsyncMock) -> None:
    mock_trigger.return_value = {"status": "skipped"}
    result = await deploy_staging("org/repo", "feature-1", "abc123")
    assert result.status == "deployed"
    assert result.environment == "staging"
    assert "staging" in result.url


@patch("app.ci.deployer.trigger_workflow", new_callable=AsyncMock)
async def test_deploy_staging_n8n_running(mock_trigger: AsyncMock) -> None:
    mock_trigger.return_value = {"status": "ok"}
    result = await deploy_staging("org/repo", "main", "def456")
    assert result.status == "deploying"


@patch("app.ci.deployer.trigger_workflow", new_callable=AsyncMock)
async def test_deploy_staging_failure(mock_trigger: AsyncMock) -> None:
    mock_trigger.return_value = {"status": "error", "detail": "Webhook failed"}
    result = await deploy_staging("org/repo", "main", "ghi789")
    assert result.status == "failed"


# ── deploy_production_canary ──────────────────────────────────────────


@patch("app.ci.deployer.trigger_workflow", new_callable=AsyncMock)
async def test_deploy_production_canary_success(mock_trigger: AsyncMock) -> None:
    mock_trigger.return_value = {"status": "skipped"}
    result = await deploy_production_canary("org/repo", "abc123", percentage=10)
    assert result.status == "deployed"
    assert result.environment == "production"


@patch("app.ci.deployer.trigger_workflow", new_callable=AsyncMock)
async def test_deploy_production_canary_clamps_percentage(mock_trigger: AsyncMock) -> None:
    mock_trigger.return_value = {"status": "skipped"}
    result = await deploy_production_canary("org/repo", "abc123", percentage=200)
    assert result.status == "deployed"
    # Verify the percentage was clamped (check the call)
    call_args = mock_trigger.call_args
    assert call_args[0][1]["canary_percentage"] == 100


@patch("app.ci.deployer.trigger_workflow", new_callable=AsyncMock)
async def test_deploy_production_canary_failure(mock_trigger: AsyncMock) -> None:
    mock_trigger.return_value = {"status": "error", "detail": "Error"}
    result = await deploy_production_canary("org/repo", "abc123")
    assert result.status == "failed"


# ── promote_canary ────────────────────────────────────────────────────


@patch("app.ci.deployer.trigger_workflow", new_callable=AsyncMock)
async def test_promote_canary_partial(mock_trigger: AsyncMock) -> None:
    mock_trigger.return_value = {"status": "skipped"}
    result = await promote_canary("deploy-1", 50)
    assert result.status == "deploying"


@patch("app.ci.deployer.trigger_workflow", new_callable=AsyncMock)
async def test_promote_canary_full(mock_trigger: AsyncMock) -> None:
    mock_trigger.return_value = {"status": "skipped"}
    result = await promote_canary("deploy-1", 100)
    assert result.status == "deployed"


@patch("app.ci.deployer.trigger_workflow", new_callable=AsyncMock)
async def test_promote_canary_failure(mock_trigger: AsyncMock) -> None:
    mock_trigger.return_value = {"status": "error"}
    result = await promote_canary("deploy-1", 50)
    assert result.status == "failed"


# ── rollback ──────────────────────────────────────────────────────────


@patch("app.ci.deployer.trigger_workflow", new_callable=AsyncMock)
async def test_rollback_success(mock_trigger: AsyncMock) -> None:
    mock_trigger.return_value = {"status": "skipped"}
    result = await rollback("deploy-1")
    assert result.status == "rolled_back"


@patch("app.ci.deployer.trigger_workflow", new_callable=AsyncMock)
async def test_rollback_failure(mock_trigger: AsyncMock) -> None:
    mock_trigger.return_value = {"status": "error", "detail": "Rollback failed"}
    result = await rollback("deploy-1")
    assert result.status == "failed"


# ── check_deploy_health ──────────────────────────────────────────────


@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
async def test_check_health_monitoring_unavailable(mock_get: AsyncMock) -> None:
    """When Prometheus is unreachable, returns healthy defaults."""
    import httpx

    mock_get.side_effect = httpx.ConnectError("Connection refused")
    result = await check_deploy_health("deploy-1")
    assert result.healthy is True
    assert result.error_rate == 0.0
    assert result.details is not None
    assert result.details["source"] == "default"
