"""Dashboard metrics service — aggregates pipeline, cost, quality, and deployment data."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, cast, func, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AiLog
from app.models.deployment import Deployment, DeployStatus
from app.models.review import Review, ReviewDecision
from app.models.test_result import TestResult
from app.models.ticket import ColumnName, Ticket
from app.models.ticket_history import TicketHistory

logger = logging.getLogger(__name__)


async def get_pipeline_stats(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> dict[str, Any]:
    """Compute pipeline throughput statistics for a project.

    Returns
    -------
    Dict with tickets_per_column, avg_time_per_column_hours, and total_tickets.
    """
    # Count tickets per column
    result = await db.execute(
        select(Ticket.column_name, func.count(Ticket.id))
        .where(Ticket.project_id == project_id)
        .group_by(Ticket.column_name)
    )
    column_counts: dict[str, int] = {}
    total = 0
    for col, count in result.all():
        col_key = col.value if isinstance(col, ColumnName) else col
        column_counts[col_key] = count
        total += count

    # Ensure all columns present
    for col in ColumnName:
        if col.value not in column_counts:
            column_counts[col.value] = 0

    # Average time per column (from ticket_history transitions)
    avg_time_per_column: dict[str, float] = {}
    for col in ColumnName:
        # Calculate average duration tickets spent in each column
        # by looking at consecutive transitions
        sub = (
            select(
                TicketHistory.ticket_id,
                TicketHistory.created_at.label("entered_at"),
            )
            .where(TicketHistory.to_column == col.value)
            .join(Ticket, Ticket.id == TicketHistory.ticket_id)
            .where(Ticket.project_id == project_id)
            .subquery()
        )

        exit_sub = (
            select(
                TicketHistory.ticket_id,
                func.min(TicketHistory.created_at).label("exited_at"),
            )
            .where(TicketHistory.from_column == col.value)
            .join(Ticket, Ticket.id == TicketHistory.ticket_id)
            .where(Ticket.project_id == project_id)
            .group_by(TicketHistory.ticket_id)
            .subquery()
        )

        time_result = await db.execute(
            select(func.avg(func.extract("epoch", exit_sub.c.exited_at - sub.c.entered_at) / 3600))
            .select_from(sub)
            .join(exit_sub, sub.c.ticket_id == exit_sub.c.ticket_id, isouter=True)
        )
        avg_hours = time_result.scalar()
        avg_time_per_column[col.value] = round(float(avg_hours), 2) if avg_hours else 0.0

    return {
        "tickets_per_column": column_counts,
        "avg_time_per_column_hours": avg_time_per_column,
        "total_tickets": total,
    }


async def get_ai_costs(
    db: AsyncSession,
    project_id: uuid.UUID,
    date_range_days: int = 30,
) -> dict[str, Any]:
    """Compute AI cost metrics for a project.

    Returns
    -------
    Dict with cost_by_agent, cost_by_day, total_cost, and tokens_total.
    """
    cutoff = datetime.now(UTC) - timedelta(days=date_range_days)

    # Get ticket IDs for this project
    ticket_ids_subq = select(Ticket.id).where(Ticket.project_id == project_id).subquery()

    base_filter = [
        AiLog.ticket_id.in_(select(ticket_ids_subq)),
        AiLog.created_at >= cutoff,
    ]

    # Cost by agent
    result = await db.execute(
        select(AiLog.agent_name, func.sum(AiLog.cost_usd))
        .where(*base_filter)
        .group_by(AiLog.agent_name)
    )
    cost_by_agent = {name: round(float(cost), 4) for name, cost in result.all()}

    # Cost by day — use date() for SQLite compat, date_trunc for PostgreSQL
    from app.config import settings

    _is_sqlite = settings.DATABASE_URL.startswith("sqlite")
    if _is_sqlite:
        day_expr = func.date(AiLog.created_at).label("day")
    else:
        day_expr = func.date_trunc("day", AiLog.created_at).label("day")

    result = await db.execute(
        select(day_expr, func.sum(AiLog.cost_usd))
        .where(*base_filter)
        .group_by("day")
        .order_by("day")
    )
    cost_by_day = {}
    for row in result.all():
        day_str = row[0] if isinstance(row[0], str) else row[0].strftime("%Y-%m-%d")
        cost_by_day[day_str] = round(float(row[1]), 4)

    # Totals
    totals_result = await db.execute(
        select(
            func.coalesce(func.sum(AiLog.cost_usd), 0.0),
            func.coalesce(func.sum(AiLog.prompt_tokens + AiLog.completion_tokens), 0),
        ).where(*base_filter)
    )
    row = totals_result.one()
    total_cost = round(float(row[0]), 4)
    tokens_total = int(row[1])

    return {
        "cost_by_agent": cost_by_agent,
        "cost_by_day": cost_by_day,
        "total_cost": total_cost,
        "tokens_total": tokens_total,
    }


async def get_code_quality(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> dict[str, Any]:
    """Compute code quality metrics for a project.

    Returns
    -------
    Dict with lint_pass_rate, test_coverage_avg, review_pass_rate, security_vuln_count.
    """
    ticket_ids_subq = select(Ticket.id).where(Ticket.project_id == project_id).subquery()

    # Lint pass rate
    lint_result = await db.execute(
        select(
            func.count(TestResult.id).label("total"),
            func.sum(case((TestResult.passed == True, 1), else_=0)).label("passed"),  # noqa: E712
        ).where(
            TestResult.ticket_id.in_(select(ticket_ids_subq)),
            TestResult.run_type == "lint",
        )
    )
    lint_row = lint_result.one()
    lint_total = int(lint_row.total or 0)
    lint_passed = int(lint_row.passed or 0)
    lint_pass_rate = round((lint_passed / lint_total * 100) if lint_total > 0 else 0.0, 1)

    # Average test coverage
    cov_result = await db.execute(
        select(func.avg(TestResult.coverage_pct)).where(
            TestResult.ticket_id.in_(select(ticket_ids_subq)),
            TestResult.coverage_pct.isnot(None),
        )
    )
    coverage_avg = cov_result.scalar()
    test_coverage_avg = round(float(coverage_avg), 1) if coverage_avg else 0.0

    # Review pass rate (approved on first review)
    review_result = await db.execute(
        select(
            func.count(Review.id).label("total"),
            func.sum(case((Review.decision == ReviewDecision.APPROVED, 1), else_=0)).label(
                "approved"
            ),
        ).where(Review.ticket_id.in_(select(ticket_ids_subq)))
    )
    review_row = review_result.one()
    review_total = int(review_row.total or 0)
    review_approved = int(review_row.approved or 0)
    review_pass_rate = round(
        (review_approved / review_total * 100) if review_total > 0 else 0.0,
        1,
    )

    # Security vulnerability count (from latest security scans)
    sec_result = await db.execute(
        select(func.sum(TestResult.failed_count)).where(
            TestResult.ticket_id.in_(select(ticket_ids_subq)),
            TestResult.run_type == "security",
        )
    )
    sec_vuln_count = int(sec_result.scalar() or 0)

    return {
        "lint_pass_rate": lint_pass_rate,
        "test_coverage_avg": test_coverage_avg,
        "review_pass_rate": review_pass_rate,
        "security_vuln_count": sec_vuln_count,
    }


async def get_deployment_stats(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> dict[str, Any]:
    """Compute deployment statistics for a project.

    Returns
    -------
    Dict with deploy_count, rollback_rate, avg_deploy_time_ms, success_rate.
    """
    ticket_ids_subq = select(Ticket.id).where(Ticket.project_id == project_id).subquery()

    base_filter = [Deployment.ticket_id.in_(select(ticket_ids_subq))]

    # Total deployments
    total_result = await db.execute(select(func.count(Deployment.id)).where(*base_filter))
    deploy_count = int(total_result.scalar() or 0)

    # Rollback count
    rollback_result = await db.execute(
        select(func.count(Deployment.id)).where(
            *base_filter, Deployment.status == DeployStatus.ROLLED_BACK
        )
    )
    rollback_count = int(rollback_result.scalar() or 0)
    rollback_rate = round(
        (rollback_count / deploy_count * 100) if deploy_count > 0 else 0.0,
        1,
    )

    # Success count
    success_result = await db.execute(
        select(func.count(Deployment.id)).where(
            *base_filter, Deployment.status == DeployStatus.DEPLOYED
        )
    )
    success_count = int(success_result.scalar() or 0)
    success_rate = round(
        (success_count / deploy_count * 100) if deploy_count > 0 else 0.0,
        1,
    )

    # Average deploy time (from created_at to completed_at)
    avg_time_result = await db.execute(
        select(
            func.avg(func.extract("epoch", Deployment.completed_at - Deployment.created_at) * 1000)
        ).where(
            *base_filter,
            Deployment.completed_at.isnot(None),
        )
    )
    avg_deploy_time = avg_time_result.scalar()
    avg_deploy_time_ms = int(float(avg_deploy_time)) if avg_deploy_time else 0

    return {
        "deploy_count": deploy_count,
        "rollback_rate": rollback_rate,
        "avg_deploy_time_ms": avg_deploy_time_ms,
        "success_rate": success_rate,
    }
