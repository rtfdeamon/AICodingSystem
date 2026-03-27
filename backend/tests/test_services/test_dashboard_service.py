"""Tests for dashboard_service — pipeline stats, AI costs, code quality, deployments.

The dashboard service uses PostgreSQL-specific SQL functions (date_trunc,
extract(epoch, ...)) that are unavailable in SQLite.  For functions that hit
those code-paths we mock ``db.execute`` to return canned result objects so
that the Python-level logic (aggregation, rounding, dict-building) is fully
exercised.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.review import Review, ReviewDecision, ReviewerType
from app.models.test_result import TestResult
from app.models.ticket import ColumnName, Priority, Ticket
from app.services.dashboard_service import (
    get_ai_costs,
    get_code_quality,
    get_deployment_stats,
    get_pipeline_stats,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_project(db: AsyncSession, user_id: uuid.UUID) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name="Dashboard Test Project",
        slug="dashboard-test",
        description="For dashboard testing",
        created_by=user_id,
    )
    db.add(project)
    await db.flush()
    return project


async def _make_ticket(
    db: AsyncSession,
    project: Project,
    column: ColumnName = ColumnName.BACKLOG,
    ticket_number: int = 1,
) -> Ticket:
    ticket = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        ticket_number=ticket_number,
        title=f"Ticket {ticket_number}",
        description="test",
        column_name=column,
        priority=Priority.P2,
    )
    db.add(ticket)
    await db.flush()
    return ticket


def _mock_result(rows: list[Any] | None = None, scalar: Any = None):
    """Build a mock SQLAlchemy result with .all(), .scalar(), .one(), .scalar_one_or_none()."""
    result = MagicMock()
    result.all.return_value = rows or []
    result.scalar.return_value = scalar
    if rows:
        result.one.return_value = rows[0]
    else:
        result.one.return_value = None
    result.scalar_one_or_none.return_value = scalar
    return result


# ---------------------------------------------------------------------------
# get_pipeline_stats
# ---------------------------------------------------------------------------


class TestGetPipelineStats:
    async def test_empty_project(
        self, db_session: AsyncSession, create_test_user
    ) -> None:
        """No tickets yields zero counts for every column."""
        user = await create_test_user()
        project = await _make_project(db_session, user.id)

        result = await get_pipeline_stats(db_session, project.id)

        assert result["total_tickets"] == 0
        for col in ColumnName:
            assert result["tickets_per_column"][col.value] == 0
            assert result["avg_time_per_column_hours"][col.value] == 0.0

    async def test_tickets_counted_per_column(
        self, db_session: AsyncSession, create_test_user
    ) -> None:
        """Tickets in different columns are counted correctly."""
        user = await create_test_user()
        project = await _make_project(db_session, user.id)

        await _make_ticket(db_session, project, ColumnName.BACKLOG, 1)
        await _make_ticket(db_session, project, ColumnName.BACKLOG, 2)
        await _make_ticket(db_session, project, ColumnName.AI_CODING, 3)
        await db_session.flush()

        result = await get_pipeline_stats(db_session, project.id)

        assert result["total_tickets"] == 3
        assert result["tickets_per_column"]["backlog"] == 2
        assert result["tickets_per_column"]["ai_coding"] == 1

    async def test_pipeline_stats_via_mock(self) -> None:
        """Exercise the full function including avg_time computation with mocked db."""
        project_id = uuid.uuid4()
        db = AsyncMock(spec=AsyncSession)

        # First call: column counts
        col_count_result = _mock_result(
            rows=[(ColumnName.BACKLOG, 5), (ColumnName.AI_CODING, 3)]
        )
        # Subsequent calls: avg time per column (one per ColumnName)
        avg_time_results = []
        for col in ColumnName:
            if col == ColumnName.BACKLOG:
                avg_time_results.append(_mock_result(scalar=2.5))
            elif col == ColumnName.AI_CODING:
                avg_time_results.append(_mock_result(scalar=1.0))
            else:
                avg_time_results.append(_mock_result(scalar=None))

        db.execute = AsyncMock(
            side_effect=[col_count_result, *avg_time_results]
        )

        result = await get_pipeline_stats(db, project_id)

        assert result["total_tickets"] == 8
        assert result["tickets_per_column"]["backlog"] == 5
        assert result["tickets_per_column"]["ai_coding"] == 3
        assert result["avg_time_per_column_hours"]["backlog"] == 2.5
        assert result["avg_time_per_column_hours"]["ai_coding"] == 1.0
        # Columns without data should be 0.0
        assert result["avg_time_per_column_hours"]["staging"] == 0.0


# ---------------------------------------------------------------------------
# get_ai_costs  (fully mocked — uses date_trunc which SQLite lacks)
# ---------------------------------------------------------------------------


class TestGetAiCosts:
    async def test_empty_project(self) -> None:
        """No AI logs yields zero cost and tokens."""
        project_id = uuid.uuid4()
        db = AsyncMock(spec=AsyncSession)

        # cost_by_agent
        agent_result = _mock_result(rows=[])
        # cost_by_day
        day_result = _mock_result(rows=[])
        # totals
        totals_row = (0.0, 0)
        totals_result = _mock_result()
        totals_result.one.return_value = totals_row

        db.execute = AsyncMock(
            side_effect=[agent_result, day_result, totals_result]
        )

        result = await get_ai_costs(db, project_id)

        assert result["total_cost"] == 0.0
        assert result["tokens_total"] == 0
        assert result["cost_by_agent"] == {}
        assert result["cost_by_day"] == {}

    async def test_costs_aggregated(self) -> None:
        """Costs are grouped by agent and by day."""
        project_id = uuid.uuid4()
        db = AsyncMock(spec=AsyncSession)

        # cost_by_agent
        agent_result = _mock_result(rows=[("claude", 0.015), ("codex", 0.02)])
        # cost_by_day
        day1 = datetime(2026, 3, 1, tzinfo=UTC)
        day2 = datetime(2026, 3, 2, tzinfo=UTC)
        day_result = _mock_result(rows=[(day1, 0.01), (day2, 0.025)])
        # totals
        totals_row = (0.035, 900)
        totals_result = _mock_result()
        totals_result.one.return_value = totals_row

        db.execute = AsyncMock(
            side_effect=[agent_result, day_result, totals_result]
        )

        result = await get_ai_costs(db, project_id)

        assert result["total_cost"] == pytest.approx(0.035, abs=1e-4)
        assert result["tokens_total"] == 900
        assert result["cost_by_agent"]["claude"] == pytest.approx(0.015, abs=1e-4)
        assert result["cost_by_agent"]["codex"] == pytest.approx(0.02, abs=1e-4)
        assert result["cost_by_day"]["2026-03-01"] == pytest.approx(0.01, abs=1e-4)

    async def test_custom_date_range(self) -> None:
        """date_range_days parameter changes the cutoff window."""
        project_id = uuid.uuid4()
        db = AsyncMock(spec=AsyncSession)

        agent_result = _mock_result(rows=[])
        day_result = _mock_result(rows=[])
        totals_result = _mock_result()
        totals_result.one.return_value = (0.0, 0)

        db.execute = AsyncMock(
            side_effect=[agent_result, day_result, totals_result]
        )

        result = await get_ai_costs(db, project_id, date_range_days=7)

        assert result["total_cost"] == 0.0
        # Verify the function was called (i.e. the parameter was accepted)
        assert db.execute.call_count == 3


# ---------------------------------------------------------------------------
# get_code_quality
# ---------------------------------------------------------------------------


class TestGetCodeQuality:
    async def test_empty_project(
        self, db_session: AsyncSession, create_test_user
    ) -> None:
        """No test results or reviews yields zeros."""
        user = await create_test_user()
        project = await _make_project(db_session, user.id)

        result = await get_code_quality(db_session, project.id)

        assert result["lint_pass_rate"] == 0.0
        assert result["test_coverage_avg"] == 0.0
        assert result["review_pass_rate"] == 0.0
        assert result["security_vuln_count"] == 0

    async def test_lint_pass_rate(
        self, db_session: AsyncSession, create_test_user
    ) -> None:
        """Lint pass rate is correctly computed from TestResult records."""
        user = await create_test_user()
        project = await _make_project(db_session, user.id)
        ticket = await _make_ticket(db_session, project)

        # 2 passed, 1 failed lint
        for passed in [True, True, False]:
            db_session.add(
                TestResult(
                    id=uuid.uuid4(),
                    ticket_id=ticket.id,
                    run_type="lint",
                    tool_name="ruff",
                    passed=passed,
                    total_tests=1,
                    passed_count=1 if passed else 0,
                    failed_count=0 if passed else 1,
                )
            )
        await db_session.flush()

        result = await get_code_quality(db_session, project.id)
        # 2/3 = 66.7%
        assert result["lint_pass_rate"] == pytest.approx(66.7, abs=0.1)

    async def test_coverage_avg(
        self, db_session: AsyncSession, create_test_user
    ) -> None:
        """Average test coverage is computed from coverage_pct values."""
        user = await create_test_user()
        project = await _make_project(db_session, user.id)
        ticket = await _make_ticket(db_session, project)

        for pct in [80.0, 90.0]:
            db_session.add(
                TestResult(
                    id=uuid.uuid4(),
                    ticket_id=ticket.id,
                    run_type="unit",
                    tool_name="pytest",
                    passed=True,
                    total_tests=10,
                    passed_count=10,
                    failed_count=0,
                    coverage_pct=pct,
                )
            )
        await db_session.flush()

        result = await get_code_quality(db_session, project.id)
        assert result["test_coverage_avg"] == pytest.approx(85.0, abs=0.1)

    async def test_review_pass_rate(
        self, db_session: AsyncSession, create_test_user
    ) -> None:
        """Review pass rate counts approved vs total reviews."""
        user = await create_test_user()
        project = await _make_project(db_session, user.id)
        ticket = await _make_ticket(db_session, project)

        db_session.add(
            Review(
                id=uuid.uuid4(),
                ticket_id=ticket.id,
                reviewer_type=ReviewerType.AI_AGENT,
                decision=ReviewDecision.APPROVED,
            )
        )
        db_session.add(
            Review(
                id=uuid.uuid4(),
                ticket_id=ticket.id,
                reviewer_type=ReviewerType.AI_AGENT,
                decision=ReviewDecision.REJECTED,
            )
        )
        await db_session.flush()

        result = await get_code_quality(db_session, project.id)
        assert result["review_pass_rate"] == pytest.approx(50.0, abs=0.1)

    async def test_security_vuln_count(
        self, db_session: AsyncSession, create_test_user
    ) -> None:
        """Security vulnerability count sums failed_count for security runs."""
        user = await create_test_user()
        project = await _make_project(db_session, user.id)
        ticket = await _make_ticket(db_session, project)

        db_session.add(
            TestResult(
                id=uuid.uuid4(),
                ticket_id=ticket.id,
                run_type="security",
                tool_name="semgrep",
                passed=False,
                total_tests=5,
                passed_count=2,
                failed_count=3,
            )
        )
        db_session.add(
            TestResult(
                id=uuid.uuid4(),
                ticket_id=ticket.id,
                run_type="security",
                tool_name="semgrep",
                passed=False,
                total_tests=2,
                passed_count=0,
                failed_count=2,
            )
        )
        await db_session.flush()

        result = await get_code_quality(db_session, project.id)
        assert result["security_vuln_count"] == 5

    async def test_all_metrics_with_data_via_mock(self) -> None:
        """Exercise all branches of get_code_quality with fully mocked db."""
        project_id = uuid.uuid4()
        db = AsyncMock(spec=AsyncSession)

        # lint result: total=10, passed=8
        lint_row = MagicMock()
        lint_row.total = 10
        lint_row.passed = 8
        lint_result = _mock_result()
        lint_result.one.return_value = lint_row

        # coverage avg
        cov_result = _mock_result(scalar=87.5)

        # review result: total=4, approved=3
        review_row = MagicMock()
        review_row.total = 4
        review_row.approved = 3
        review_result = _mock_result()
        review_result.one.return_value = review_row

        # security vulns
        sec_result = _mock_result(scalar=7)

        db.execute = AsyncMock(
            side_effect=[lint_result, cov_result, review_result, sec_result]
        )

        result = await get_code_quality(db, project_id)

        assert result["lint_pass_rate"] == 80.0
        assert result["test_coverage_avg"] == 87.5
        assert result["review_pass_rate"] == 75.0
        assert result["security_vuln_count"] == 7


# ---------------------------------------------------------------------------
# get_deployment_stats
# ---------------------------------------------------------------------------


class TestGetDeploymentStats:
    async def test_empty_project(
        self, db_session: AsyncSession, create_test_user
    ) -> None:
        """No deployments yields zeros."""
        user = await create_test_user()
        project = await _make_project(db_session, user.id)

        result = await get_deployment_stats(db_session, project.id)

        assert result["deploy_count"] == 0
        assert result["rollback_rate"] == 0.0
        assert result["success_rate"] == 0.0
        assert result["avg_deploy_time_ms"] == 0

    async def test_deploy_counts_and_rates_via_mock(self) -> None:
        """Counts, rollback rate, success rate via mocked db."""
        project_id = uuid.uuid4()
        db = AsyncMock(spec=AsyncSession)

        # total
        total_result = _mock_result(scalar=10)
        # rollback
        rollback_result = _mock_result(scalar=2)
        # success
        success_result = _mock_result(scalar=7)
        # avg deploy time
        avg_time_result = _mock_result(scalar=5000.0)

        db.execute = AsyncMock(
            side_effect=[total_result, rollback_result, success_result, avg_time_result]
        )

        result = await get_deployment_stats(db, project_id)

        assert result["deploy_count"] == 10
        assert result["rollback_rate"] == 20.0
        assert result["success_rate"] == 70.0
        assert result["avg_deploy_time_ms"] == 5000

    async def test_deploy_without_completed_at_via_mock(self) -> None:
        """When avg deploy time is None, avg_deploy_time_ms = 0."""
        project_id = uuid.uuid4()
        db = AsyncMock(spec=AsyncSession)

        total_result = _mock_result(scalar=1)
        rollback_result = _mock_result(scalar=0)
        success_result = _mock_result(scalar=0)
        avg_time_result = _mock_result(scalar=None)

        db.execute = AsyncMock(
            side_effect=[total_result, rollback_result, success_result, avg_time_result]
        )

        result = await get_deployment_stats(db, project_id)

        assert result["deploy_count"] == 1
        assert result["avg_deploy_time_ms"] == 0
        assert result["success_rate"] == 0.0
        assert result["rollback_rate"] == 0.0

    async def test_zero_deploys_avoids_division_by_zero(self) -> None:
        """When deploy_count is 0, rates are 0.0 without ZeroDivisionError."""
        project_id = uuid.uuid4()
        db = AsyncMock(spec=AsyncSession)

        total_result = _mock_result(scalar=0)
        rollback_result = _mock_result(scalar=0)
        success_result = _mock_result(scalar=0)
        avg_time_result = _mock_result(scalar=None)

        db.execute = AsyncMock(
            side_effect=[total_result, rollback_result, success_result, avg_time_result]
        )

        result = await get_deployment_stats(db, project_id)

        assert result["deploy_count"] == 0
        assert result["rollback_rate"] == 0.0
        assert result["success_rate"] == 0.0
        assert result["avg_deploy_time_ms"] == 0
