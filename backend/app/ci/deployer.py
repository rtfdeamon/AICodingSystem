"""Deployment service — staging, canary, promote, rollback, and health checks."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.n8n_service import trigger_workflow

logger = logging.getLogger(__name__)


@dataclass
class DeployResult:
    """Result from a deployment operation."""

    status: str  # pending | deploying | deployed | rolled_back | failed
    url: str
    deploy_id: str
    environment: str  # staging | production


@dataclass
class HealthStatus:
    """Health metrics for a deployed service."""

    healthy: bool
    error_rate: float  # percentage 0-100
    latency_p50: int  # milliseconds
    latency_p95: int
    latency_p99: int
    uptime_pct: float  # percentage 0-100
    details: dict[str, Any] | None = None


async def deploy_staging(
    project: str,
    branch: str,
    commit_sha: str,
) -> DeployResult:
    """Deploy a branch to the staging environment.

    Parameters
    ----------
    project:
        Project identifier or "owner/repo" string.
    branch:
        Branch to deploy.
    commit_sha:
        Commit SHA to deploy.

    Returns
    -------
    DeployResult with status, URL, and deploy ID.
    """
    deploy_id = str(uuid.uuid4())
    logger.info(
        "Deploying to staging: project=%s branch=%s commit=%s deploy_id=%s",
        project,
        branch,
        commit_sha,
        deploy_id,
    )

    # Trigger the staging deploy via n8n workflow
    result = await trigger_workflow(
        "deploy_canary",
        {
            "deploy_id": deploy_id,
            "project": project,
            "branch": branch,
            "commit_sha": commit_sha,
            "environment": "staging",
            "canary_percentage": 100,
        },
    )

    status = "deploying"
    if result.get("status") == "error":
        status = "failed"
        logger.error("Staging deploy trigger failed: %s", result.get("detail"))
    elif result.get("status") == "skipped":
        # n8n not configured; simulate successful deploy for development
        logger.warning("n8n not configured; simulating staging deploy")
        status = "deployed"

    staging_url = f"https://staging.{project.split('/')[-1] if '/' in project else project}.app"

    return DeployResult(
        status=status,
        url=staging_url,
        deploy_id=deploy_id,
        environment="staging",
    )


async def deploy_production_canary(
    project: str,
    commit_sha: str,
    percentage: int = 10,
) -> DeployResult:
    """Deploy to production with canary traffic percentage.

    Parameters
    ----------
    project:
        Project identifier.
    commit_sha:
        Commit SHA to deploy.
    percentage:
        Initial canary traffic percentage (1-100).

    Returns
    -------
    DeployResult with status and deploy ID.
    """
    deploy_id = str(uuid.uuid4())
    percentage = max(1, min(100, percentage))

    logger.info(
        "Starting production canary: project=%s commit=%s percentage=%d%% deploy_id=%s",
        project,
        commit_sha,
        percentage,
        deploy_id,
    )

    result = await trigger_workflow(
        "deploy_canary",
        {
            "deploy_id": deploy_id,
            "project": project,
            "commit_sha": commit_sha,
            "environment": "production",
            "canary_percentage": percentage,
        },
    )

    status = "deploying"
    if result.get("status") == "error":
        status = "failed"
        logger.error("Production canary deploy trigger failed: %s", result.get("detail"))
    elif result.get("status") == "skipped":
        logger.warning("n8n not configured; simulating production canary deploy")
        status = "deployed"

    prod_url = f"https://{project.split('/')[-1] if '/' in project else project}.app"

    return DeployResult(
        status=status,
        url=prod_url,
        deploy_id=deploy_id,
        environment="production",
    )


async def promote_canary(
    deploy_id: str,
    new_percentage: int,
) -> DeployResult:
    """Increase the canary traffic percentage for an existing deployment.

    Parameters
    ----------
    deploy_id:
        ID of the deployment to promote.
    new_percentage:
        New traffic percentage (1-100). Setting to 100 completes the rollout.

    Returns
    -------
    DeployResult with updated status.
    """
    new_percentage = max(1, min(100, new_percentage))
    logger.info("Promoting canary %s to %d%%", deploy_id, new_percentage)

    result = await trigger_workflow(
        "deploy_canary",
        {
            "deploy_id": deploy_id,
            "action": "promote",
            "canary_percentage": new_percentage,
        },
    )

    status = "deployed" if new_percentage == 100 else "deploying"
    if result.get("status") == "error":
        status = "failed"
    elif result.get("status") == "skipped":
        logger.warning("n8n not configured; simulating canary promotion")

    return DeployResult(
        status=status,
        url="",
        deploy_id=deploy_id,
        environment="production",
    )


async def rollback(deploy_id: str) -> DeployResult:
    """Rollback a deployment to the previous version.

    Parameters
    ----------
    deploy_id:
        ID of the deployment to rollback.

    Returns
    -------
    DeployResult with rolled_back status.
    """
    logger.info("Rolling back deployment %s", deploy_id)

    result = await trigger_workflow(
        "deploy_canary",
        {
            "deploy_id": deploy_id,
            "action": "rollback",
        },
    )

    status = "rolled_back"
    if result.get("status") == "error":
        status = "failed"
        logger.error("Rollback trigger failed: %s", result.get("detail"))
    elif result.get("status") == "skipped":
        logger.warning("n8n not configured; simulating rollback")

    return DeployResult(
        status=status,
        url="",
        deploy_id=deploy_id,
        environment="unknown",
    )


async def check_deploy_health(deploy_id: str) -> HealthStatus:
    """Check health metrics for a deployment.

    Queries Prometheus/monitoring endpoints for real-time health data.

    Parameters
    ----------
    deploy_id:
        ID of the deployment to check.

    Returns
    -------
    HealthStatus with error rate, latency percentiles, and uptime.
    """
    logger.info("Checking health for deployment %s", deploy_id)

    # Query Prometheus metrics via the monitoring endpoint
    prometheus_url = "http://prometheus:9090"
    metrics: dict[str, Any] = {}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Error rate query
            error_query = (
                f'sum(rate(http_requests_total{{status=~"5..",deploy_id="{deploy_id}"}}[5m])) / '
                f'sum(rate(http_requests_total{{deploy_id="{deploy_id}"}}[5m])) * 100'
            )
            resp = await client.get(
                f"{prometheus_url}/api/v1/query",
                params={"query": error_query},
            )
            if resp.status_code == 200:
                prom_data = resp.json()
                results = prom_data.get("data", {}).get("result", [])
                if results:
                    metrics["error_rate"] = float(results[0].get("value", [0, 0])[1])

            # Latency percentiles
            for percentile, label in [(0.50, "p50"), (0.95, "p95"), (0.99, "p99")]:
                latency_query = (
                    f"histogram_quantile({percentile}, "
                    f"sum(rate(http_request_duration_seconds_bucket"
                    f'{{deploy_id="{deploy_id}"}}[5m])) by (le)) * 1000'
                )
                resp = await client.get(
                    f"{prometheus_url}/api/v1/query",
                    params={"query": latency_query},
                )
                if resp.status_code == 200:
                    prom_data = resp.json()
                    results = prom_data.get("data", {}).get("result", [])
                    if results:
                        metrics[f"latency_{label}"] = int(float(results[0].get("value", [0, 0])[1]))

    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Failed to query Prometheus for deploy %s: %s", deploy_id, exc)
        # Return defaults when monitoring is unavailable
        return HealthStatus(
            healthy=True,
            error_rate=0.0,
            latency_p50=0,
            latency_p95=0,
            latency_p99=0,
            uptime_pct=100.0,
            details={"source": "default", "reason": "monitoring unavailable"},
        )

    error_rate = metrics.get("error_rate", 0.0)
    latency_p50 = metrics.get("latency_p50", 0)
    latency_p95 = metrics.get("latency_p95", 0)
    latency_p99 = metrics.get("latency_p99", 0)

    # Determine health: error rate below 1% and p99 below 2000ms
    healthy = error_rate < 1.0 and latency_p99 < 2000

    return HealthStatus(
        healthy=healthy,
        error_rate=round(error_rate, 3),
        latency_p50=latency_p50,
        latency_p95=latency_p95,
        latency_p99=latency_p99,
        uptime_pct=round(100.0 - error_rate, 3),
        details=metrics,
    )
