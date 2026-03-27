"""Tests for dashboard API endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_pipeline_stats_requires_auth(async_client: AsyncClient) -> None:
    resp = await async_client.get("/api/v1/dashboard/pipeline-stats")
    assert resp.status_code in (401, 403)


async def test_pipeline_stats_with_valid_project(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    # Create a project first
    proj_resp = await async_client.post(
        "/api/v1/projects",
        json={"name": "Dashboard Test"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    resp = await async_client.get(
        f"/api/v1/dashboard/pipeline-stats?project_id={project_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "tickets_per_column" in data
    assert "total_tickets" in data


async def test_pipeline_stats_invalid_uuid(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await async_client.get(
        "/api/v1/dashboard/pipeline-stats?project_id=not-a-uuid",
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_code_quality(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    proj_resp = await async_client.post(
        "/api/v1/projects",
        json={"name": "Code Quality Test"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    resp = await async_client.get(
        f"/api/v1/dashboard/code-quality?project_id={project_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "lint_pass_rate" in data
    assert "test_coverage_avg" in data


async def test_deployment_stats(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    proj_resp = await async_client.post(
        "/api/v1/projects",
        json={"name": "Deploy Stats Test"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    resp = await async_client.get(
        f"/api/v1/dashboard/deployment-stats?project_id={project_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "deploy_count" in data
    assert "success_rate" in data


# Note: test_ai_costs is excluded because the dashboard_service uses
# date_trunc() which is PostgreSQL-specific and not available in SQLite.
# This endpoint should be tested with a real PostgreSQL test database.
