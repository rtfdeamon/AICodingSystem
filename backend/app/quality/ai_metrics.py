"""AI-specific quality metrics — dashboard data for AI-attributed code quality.

Tracks metrics specific to AI-generated code:
- AI-attributed regression rate
- Defect density in AI vs human code
- Merge confidence scores
- Review acceptance rates by agent
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AiLog, AiLogStatus
from app.models.review import Review, ReviewDecision, ReviewerType
from app.models.test_result import TestResult
from app.models.ticket import Ticket

logger = logging.getLogger(__name__)


async def get_ai_quality_metrics(
    db: AsyncSession,
    project_id: uuid.UUID,
    date_range_days: int = 30,
) -> dict[str, Any]:
    """Compute AI-specific quality metrics for a project.

    Returns
    -------
    Dict with ai_regression_rate, defect_density, merge_confidence,
    agent_acceptance_rates, and ai_vs_human_stats.
    """
    cutoff = datetime.now(UTC) - timedelta(days=date_range_days)
    ticket_ids_subq = select(Ticket.id).where(Ticket.project_id == project_id).subquery()

    # AI review acceptance rate (by agent)
    agent_acceptance = await _get_agent_acceptance_rates(db, ticket_ids_subq, cutoff)

    # AI-attributed regression rate (test failures after AI coding)
    regression_rate = await _get_ai_regression_rate(db, ticket_ids_subq, cutoff)

    # AI defect density (review findings per AI-generated ticket)
    defect_density = await _get_ai_defect_density(db, ticket_ids_subq, cutoff)

    # Merge confidence (% of AI reviews that led to approval without human changes)
    merge_confidence = await _get_merge_confidence(db, ticket_ids_subq, cutoff)

    # AI vs human review comparison
    ai_vs_human = await _get_ai_vs_human_stats(db, ticket_ids_subq, cutoff)

    # Agent performance (latency, cost, success rate by agent)
    agent_performance = await _get_agent_performance(db, ticket_ids_subq, cutoff)

    return {
        "agent_acceptance_rates": agent_acceptance,
        "ai_regression_rate": regression_rate,
        "ai_defect_density": defect_density,
        "merge_confidence": merge_confidence,
        "ai_vs_human_stats": ai_vs_human,
        "agent_performance": agent_performance,
        "date_range_days": date_range_days,
    }


async def _get_agent_acceptance_rates(
    db: AsyncSession,
    ticket_ids_subq: Any,
    cutoff: datetime,
) -> dict[str, dict[str, Any]]:
    """Get acceptance rates for each AI agent's review findings."""
    result = await db.execute(
        select(
            Review.agent_name,
            func.count(Review.id).label("total"),
            func.sum(case((Review.decision == ReviewDecision.APPROVED, 1), else_=0)).label(
                "approved"
            ),
            func.sum(
                case((Review.decision == ReviewDecision.CHANGES_REQUESTED, 1), else_=0)
            ).label("changes_requested"),
        )
        .where(
            Review.ticket_id.in_(select(ticket_ids_subq)),
            Review.reviewer_type == ReviewerType.AI_AGENT,
            Review.created_at >= cutoff,
            Review.agent_name.isnot(None),
        )
        .group_by(Review.agent_name)
    )

    rates: dict[str, dict[str, Any]] = {}
    for row in result.all():
        total = int(row.total or 0)
        approved = int(row.approved or 0)
        rates[row.agent_name] = {
            "total_reviews": total,
            "approved": approved,
            "changes_requested": int(row.changes_requested or 0),
            "approval_rate": round((approved / total * 100) if total > 0 else 0.0, 1),
        }
    return rates


async def _get_ai_regression_rate(
    db: AsyncSession,
    ticket_ids_subq: Any,
    cutoff: datetime,
) -> dict[str, Any]:
    """Calculate rate of test failures in AI-coded tickets."""
    result = await db.execute(
        select(
            func.count(TestResult.id).label("total"),
            func.sum(case((TestResult.passed == False, 1), else_=0)).label("failed"),  # noqa: E712
        ).where(
            TestResult.ticket_id.in_(select(ticket_ids_subq)),
            TestResult.created_at >= cutoff,
            TestResult.run_type == "unit",
        )
    )
    row = result.one()
    total = int(row.total or 0)
    failed = int(row.failed or 0)
    return {
        "total_test_runs": total,
        "failed_runs": failed,
        "regression_rate": round((failed / total * 100) if total > 0 else 0.0, 1),
    }


async def _get_ai_defect_density(
    db: AsyncSession,
    ticket_ids_subq: Any,
    cutoff: datetime,
) -> dict[str, Any]:
    """Calculate defect density: review findings per AI ticket."""
    # Count AI reviews with changes_requested
    defect_result = await db.execute(
        select(func.count(Review.id)).where(
            Review.ticket_id.in_(select(ticket_ids_subq)),
            Review.reviewer_type == ReviewerType.AI_AGENT,
            Review.decision == ReviewDecision.CHANGES_REQUESTED,
            Review.created_at >= cutoff,
        )
    )
    defects = int(defect_result.scalar() or 0)

    # Count total AI-reviewed tickets
    ticket_result = await db.execute(
        select(func.count(func.distinct(Review.ticket_id))).where(
            Review.ticket_id.in_(select(ticket_ids_subq)),
            Review.reviewer_type == ReviewerType.AI_AGENT,
            Review.created_at >= cutoff,
        )
    )
    total_tickets = int(ticket_result.scalar() or 0)

    return {
        "defects_found": defects,
        "tickets_reviewed": total_tickets,
        "defect_density": round((defects / total_tickets) if total_tickets > 0 else 0.0, 2),
    }


async def _get_merge_confidence(
    db: AsyncSession,
    ticket_ids_subq: Any,
    cutoff: datetime,
) -> dict[str, Any]:
    """Calculate merge confidence: % of tickets approved on first AI review."""
    # Tickets where the first AI review was 'approved'
    first_review_subq = (
        select(
            Review.ticket_id,
            func.min(Review.created_at).label("first_review_at"),
        )
        .where(
            Review.ticket_id.in_(select(ticket_ids_subq)),
            Review.reviewer_type == ReviewerType.AI_AGENT,
            Review.created_at >= cutoff,
        )
        .group_by(Review.ticket_id)
        .subquery()
    )

    first_approved = await db.execute(
        select(func.count(Review.id)).where(
            Review.ticket_id == first_review_subq.c.ticket_id,
            Review.created_at == first_review_subq.c.first_review_at,
            Review.decision == ReviewDecision.APPROVED,
        )
    )
    approved_first = int(first_approved.scalar() or 0)

    total_first = await db.execute(
        select(func.count()).select_from(first_review_subq)
    )
    total = int(total_first.scalar() or 0)

    return {
        "approved_on_first_review": approved_first,
        "total_first_reviews": total,
        "confidence_pct": round((approved_first / total * 100) if total > 0 else 0.0, 1),
    }


async def _get_ai_vs_human_stats(
    db: AsyncSession,
    ticket_ids_subq: Any,
    cutoff: datetime,
) -> dict[str, Any]:
    """Compare AI and human review statistics."""
    result = await db.execute(
        select(
            Review.reviewer_type,
            func.count(Review.id).label("count"),
            func.sum(case((Review.decision == ReviewDecision.APPROVED, 1), else_=0)).label(
                "approved"
            ),
        )
        .where(
            Review.ticket_id.in_(select(ticket_ids_subq)),
            Review.created_at >= cutoff,
        )
        .group_by(Review.reviewer_type)
    )

    stats: dict[str, Any] = {}
    for row in result.all():
        rt = row.reviewer_type
        reviewer_type = rt.value if hasattr(rt, "value") else str(rt)
        total = int(row.count or 0)
        approved = int(row.approved or 0)
        stats[reviewer_type] = {
            "total_reviews": total,
            "approved": approved,
            "approval_rate": round((approved / total * 100) if total > 0 else 0.0, 1),
        }
    return stats


async def _get_agent_performance(
    db: AsyncSession,
    ticket_ids_subq: Any,
    cutoff: datetime,
) -> dict[str, dict[str, Any]]:
    """Get performance metrics per agent (latency, cost, success rate)."""
    result = await db.execute(
        select(
            AiLog.agent_name,
            func.count(AiLog.id).label("total"),
            func.avg(AiLog.latency_ms).label("avg_latency_ms"),
            func.sum(AiLog.cost_usd).label("total_cost"),
            func.sum(case((AiLog.status == AiLogStatus.SUCCESS, 1), else_=0)).label("success"),
        )
        .where(
            AiLog.ticket_id.in_(select(ticket_ids_subq)),
            AiLog.created_at >= cutoff,
        )
        .group_by(AiLog.agent_name)
    )

    performance: dict[str, dict[str, Any]] = {}
    for row in result.all():
        total = int(row.total or 0)
        success = int(row.success or 0)
        performance[row.agent_name] = {
            "total_calls": total,
            "avg_latency_ms": int(float(row.avg_latency_ms or 0)),
            "total_cost_usd": round(float(row.total_cost or 0), 4),
            "success_rate": round((success / total * 100) if total > 0 else 0.0, 1),
        }
    return performance
