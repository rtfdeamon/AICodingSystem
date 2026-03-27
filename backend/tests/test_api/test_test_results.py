"""Tests for app.api.v1.test_results — list, get, trigger run, and generate."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.test_result import TestResult

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_project_and_ticket(
    client: AsyncClient,
    headers: dict,
) -> tuple[str, str]:
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Test Results Proj"},
        headers=headers,
    )
    project_id = proj_resp.json()["id"]

    ticket_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={
            "title": "Test results ticket",
            "description": "For testing test results",
            "priority": "P2",
        },
        headers=headers,
    )
    return project_id, ticket_resp.json()["id"]


async def _create_test_result(
    db_session: AsyncSession,
    ticket_id: str,
    *,
    run_type: str = "unit",
    passed: bool = True,
) -> TestResult:
    tr = TestResult(
        id=uuid.uuid4(),
        ticket_id=uuid.UUID(ticket_id),
        run_type=run_type,
        tool_name="pytest",
        passed=passed,
        total_tests=10,
        passed_count=10 if passed else 5,
        failed_count=0 if passed else 5,
        skipped_count=0,
        coverage_pct=87.5,
        duration_ms=3000,
    )
    db_session.add(tr)
    await db_session.flush()
    await db_session.refresh(tr)
    return tr


# ---------------------------------------------------------------------------
# List test results
# ---------------------------------------------------------------------------


async def test_list_test_results_empty(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)
    resp = await async_client.get(
        f"/api/v1/tickets/{ticket_id}/test-results",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_test_results_with_data(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)
    await _create_test_result(db_session, ticket_id, run_type="unit")
    await _create_test_result(db_session, ticket_id, run_type="integration")

    resp = await async_client.get(
        f"/api/v1/tickets/{ticket_id}/test-results",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


async def test_list_test_results_filter_by_run_type(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)
    await _create_test_result(db_session, ticket_id, run_type="unit")
    await _create_test_result(db_session, ticket_id, run_type="e2e")

    resp = await async_client.get(
        f"/api/v1/tickets/{ticket_id}/test-results?run_type=unit",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["run_type"] == "unit"


# ---------------------------------------------------------------------------
# Get single test result
# ---------------------------------------------------------------------------


async def test_get_test_result(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)
    tr = await _create_test_result(db_session, ticket_id)

    resp = await async_client.get(
        f"/api/v1/test-results/{tr.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(tr.id)
    assert data["passed"] is True
    assert data["total_tests"] == 10


async def test_get_test_result_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake_id = uuid.uuid4()
    resp = await async_client.get(
        f"/api/v1/test-results/{fake_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Trigger test run
# ---------------------------------------------------------------------------


async def test_trigger_test_run(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Trigger a test run with mocked runner."""
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    from dataclasses import dataclass

    @dataclass
    class FakeSuiteResult:
        tool_name: str = "pytest"
        passed: bool = True
        total: int = 15
        passed_count: int = 15
        failed: int = 0
        skipped: int = 0
        coverage_pct: float = 92.0
        report_json: dict | None = None
        duration_ms: int = 5000

    with patch(
        "app.ci.test_runner.run_tests",
        new_callable=AsyncMock,
        return_value=FakeSuiteResult(),
    ):
        resp = await async_client.post(
            f"/api/v1/tickets/{ticket_id}/tests/run",
            json={"test_type": "unit", "branch": "main"},
            headers=auth_headers,
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["passed"] is True
    assert data["total_tests"] == 15
    assert data["tool_name"] == "pytest"


async def test_trigger_test_run_ticket_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/tickets/{fake_id}/tests/run",
        json={"test_type": "unit"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Generate tests
# ---------------------------------------------------------------------------


async def test_generate_tests(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """AI test generation with mocked agent."""
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    from dataclasses import dataclass

    @dataclass
    class FakeAgentResponse:
        content: str = "def test_foo():\n    assert True\n\ndef test_bar():\n    assert True"
        cost_usd: float = 0.005

    mock_agent = AsyncMock()
    with (
        patch("app.agents.router.route_task", return_value=mock_agent),
        patch(
            "app.agents.router.execute_with_fallback",
            new_callable=AsyncMock,
            return_value=FakeAgentResponse(),
        ),
    ):
        resp = await async_client.post(
            f"/api/v1/tickets/{ticket_id}/tests/generate",
            json={"test_type": "unit", "target_files": ["app/main.py"]},
            headers=auth_headers,
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["file_count"] == 2
    assert data["cost_usd"] == 0.005
    assert "def test_" in data["generated_tests"]


async def test_generate_tests_ticket_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/tickets/{fake_id}/tests/generate",
        json={"test_type": "unit"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
