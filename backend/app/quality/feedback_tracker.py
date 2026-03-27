"""Developer feedback tracker — tracks accepted/rejected review findings.

Records which AI review findings developers accept vs. reject,
enabling prompt fine-tuning and false-positive reduction over time.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review, ReviewerType

logger = logging.getLogger(__name__)


class FeedbackAction(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass
class FindingFeedback:
    """Feedback on a single AI review finding."""

    review_id: uuid.UUID
    finding_index: int
    action: FeedbackAction
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class FeedbackStats:
    """Aggregated feedback statistics."""

    total_findings: int = 0
    accepted: int = 0
    rejected: int = 0
    deferred: int = 0

    @property
    def acceptance_rate(self) -> float:
        if self.total_findings == 0:
            return 0.0
        return round(self.accepted / self.total_findings * 100, 1)

    @property
    def rejection_rate(self) -> float:
        if self.total_findings == 0:
            return 0.0
        return round(self.rejected / self.total_findings * 100, 1)


# ── In-memory feedback store (production would use DB table) ─────────────
# Using in-memory for MVP; can be migrated to a DB model later.

_feedback_store: dict[uuid.UUID, list[FindingFeedback]] = {}


def record_feedback(
    review_id: uuid.UUID,
    finding_index: int,
    action: FeedbackAction,
    reason: str = "",
) -> FindingFeedback:
    """Record developer feedback on an AI review finding.

    Parameters
    ----------
    review_id:
        The review that contains the finding.
    finding_index:
        Index of the finding in the review's inline_comments list.
    action:
        Whether the developer accepted, rejected, or deferred the finding.
    reason:
        Optional reason for the action (useful for prompt tuning).

    Returns
    -------
    The recorded FindingFeedback.
    """
    feedback = FindingFeedback(
        review_id=review_id,
        finding_index=finding_index,
        action=action,
        reason=reason,
    )

    if review_id not in _feedback_store:
        _feedback_store[review_id] = []
    _feedback_store[review_id].append(feedback)

    logger.info(
        "Feedback recorded: review=%s finding=%d action=%s",
        review_id,
        finding_index,
        action.value,
    )
    return feedback


def get_feedback_for_review(review_id: uuid.UUID) -> list[FindingFeedback]:
    """Get all feedback for a specific review."""
    return _feedback_store.get(review_id, [])


def get_feedback_stats() -> FeedbackStats:
    """Get aggregated feedback statistics across all reviews."""
    stats = FeedbackStats()
    for feedbacks in _feedback_store.values():
        for fb in feedbacks:
            stats.total_findings += 1
            if fb.action == FeedbackAction.ACCEPTED:
                stats.accepted += 1
            elif fb.action == FeedbackAction.REJECTED:
                stats.rejected += 1
            elif fb.action == FeedbackAction.DEFERRED:
                stats.deferred += 1
    return stats


def get_rejection_reasons() -> dict[str, int]:
    """Get aggregated rejection reasons for prompt tuning.

    Returns a dict of {reason: count} sorted by frequency.
    """
    reasons: dict[str, int] = {}
    for feedbacks in _feedback_store.values():
        for fb in feedbacks:
            if fb.action == FeedbackAction.REJECTED and fb.reason:
                reasons[fb.reason] = reasons.get(fb.reason, 0) + 1
    return dict(sorted(reasons.items(), key=lambda x: x[1], reverse=True))


def clear_feedback() -> None:
    """Clear all stored feedback (for testing)."""
    _feedback_store.clear()


async def get_review_feedback_metrics(
    db: AsyncSession,
    project_id: uuid.UUID,
    date_range_days: int = 30,
) -> dict[str, Any]:
    """Get feedback-relevant metrics from the database.

    Computes how often human reviewers agree with AI reviewers
    by comparing AI review decisions with subsequent human decisions
    on the same tickets.
    """
    cutoff = datetime.now(UTC) - timedelta(days=date_range_days)
    from app.models.ticket import Ticket

    ticket_ids_subq = select(Ticket.id).where(Ticket.project_id == project_id).subquery()

    # Find tickets with both AI and human reviews
    ai_reviews = (
        select(
            Review.ticket_id,
            Review.decision.label("ai_decision"),
        )
        .where(
            Review.ticket_id.in_(select(ticket_ids_subq)),
            Review.reviewer_type == ReviewerType.AI_AGENT,
            Review.created_at >= cutoff,
        )
        .subquery()
    )

    human_reviews = (
        select(
            Review.ticket_id,
            Review.decision.label("human_decision"),
        )
        .where(
            Review.ticket_id.in_(select(ticket_ids_subq)),
            Review.reviewer_type == ReviewerType.USER,
            Review.created_at >= cutoff,
        )
        .subquery()
    )

    # Count agreements
    agreement_result = await db.execute(
        select(func.count()).select_from(
            ai_reviews.join(
                human_reviews,
                ai_reviews.c.ticket_id == human_reviews.c.ticket_id,
            )
        ).where(ai_reviews.c.ai_decision == human_reviews.c.human_decision)
    )
    agreements = int(agreement_result.scalar() or 0)

    # Count total comparisons
    total_result = await db.execute(
        select(func.count()).select_from(
            ai_reviews.join(
                human_reviews,
                ai_reviews.c.ticket_id == human_reviews.c.ticket_id,
            )
        )
    )
    total_comparisons = int(total_result.scalar() or 0)

    # In-memory feedback stats
    in_memory_stats = get_feedback_stats()

    return {
        "ai_human_agreement_rate": round(
            (agreements / total_comparisons * 100) if total_comparisons > 0 else 0.0, 1
        ),
        "total_comparisons": total_comparisons,
        "agreements": agreements,
        "in_memory_feedback": {
            "total": in_memory_stats.total_findings,
            "accepted": in_memory_stats.accepted,
            "rejected": in_memory_stats.rejected,
            "acceptance_rate": in_memory_stats.acceptance_rate,
        },
        "top_rejection_reasons": get_rejection_reasons(),
    }
