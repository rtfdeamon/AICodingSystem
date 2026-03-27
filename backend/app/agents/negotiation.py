"""Negotiation Workflow — agents propose alternatives when developers push back.

When a developer rejects an AI review finding or coding suggestion,
the negotiation workflow:
1. Analyzes the rejection reason
2. Generates alternative approaches
3. Presents options with trade-off analysis
4. Tracks negotiation outcomes for learning
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class NegotiationStatus(StrEnum):
    PENDING = "pending"
    ALTERNATIVES_PROPOSED = "alternatives_proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    WITHDRAWN = "withdrawn"


@dataclass
class Alternative:
    """A single alternative approach proposed by the agent."""

    id: str
    title: str
    description: str
    code_snippet: str = ""
    trade_offs: list[str] = field(default_factory=list)
    effort_estimate: str = ""  # "low", "medium", "high"
    confidence: float = 0.0  # 0.0 - 1.0


@dataclass
class NegotiationRequest:
    """A negotiation initiated by developer pushback."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    review_id: uuid.UUID | None = None
    ticket_id: uuid.UUID | None = None
    finding_index: int = 0
    original_suggestion: str = ""
    rejection_reason: str = ""
    status: NegotiationStatus = NegotiationStatus.PENDING
    alternatives: list[Alternative] = field(default_factory=list)
    selected_alternative_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None


@dataclass
class NegotiationOutcome:
    """Outcome of a negotiation for learning."""

    negotiation_id: uuid.UUID
    original_accepted: bool = False
    alternative_selected: str | None = None
    developer_comment: str = ""
    resolution_time_ms: int = 0


# ── In-memory store (MVP) ─────────────────────────────────────────────

_negotiations: dict[uuid.UUID, NegotiationRequest] = {}
_outcomes: list[NegotiationOutcome] = []


def clear_negotiations() -> None:
    """Clear all stored negotiations (for testing)."""
    _negotiations.clear()
    _outcomes.clear()


def create_negotiation(
    review_id: uuid.UUID,
    finding_index: int,
    original_suggestion: str,
    rejection_reason: str,
    *,
    ticket_id: uuid.UUID | None = None,
) -> NegotiationRequest:
    """Create a new negotiation request from developer pushback.

    Parameters
    ----------
    review_id:
        The review containing the rejected finding.
    finding_index:
        Index of the rejected finding.
    original_suggestion:
        The AI suggestion that was rejected.
    rejection_reason:
        Why the developer rejected it.
    ticket_id:
        Optional ticket ID for context.
    """
    negotiation = NegotiationRequest(
        review_id=review_id,
        ticket_id=ticket_id,
        finding_index=finding_index,
        original_suggestion=original_suggestion,
        rejection_reason=rejection_reason,
    )
    _negotiations[negotiation.id] = negotiation

    logger.info(
        "Negotiation created: id=%s review=%s finding=%d reason=%s",
        negotiation.id,
        review_id,
        finding_index,
        rejection_reason[:100],
    )
    return negotiation


def generate_alternatives(
    negotiation_id: uuid.UUID,
    rejection_reason: str,
    original_suggestion: str,
    *,
    max_alternatives: int = 3,
) -> list[Alternative]:
    """Generate alternative approaches based on the rejection reason.

    In production, this calls the AI agent to generate alternatives.
    Here we implement the framework and categorization logic.
    """
    negotiation = _negotiations.get(negotiation_id)
    if not negotiation:
        raise ValueError(f"Negotiation {negotiation_id} not found")

    alternatives: list[Alternative] = []
    reason_lower = rejection_reason.lower()

    # Categorize rejection and generate appropriate alternatives
    if any(kw in reason_lower for kw in ("performance", "slow", "overhead", "latency")):
        alternatives.append(Alternative(
            id="perf-optimized",
            title="Performance-optimized approach",
            description=(
                "Modified implementation with minimal overhead. "
                "Uses lazy evaluation and caching to reduce performance impact."
            ),
            trade_offs=["May sacrifice some readability", "Requires cache invalidation"],
            effort_estimate="medium",
            confidence=0.8,
        ))

    if any(kw in reason_lower for kw in ("complex", "simple", "overkill", "over-engineer")):
        alternatives.append(Alternative(
            id="simplified",
            title="Simplified approach",
            description=(
                "Minimal implementation that addresses the core concern "
                "without additional abstraction layers."
            ),
            trade_offs=["Less extensible", "May need refactoring later"],
            effort_estimate="low",
            confidence=0.85,
        ))

    if any(kw in reason_lower for kw in ("breaking", "backward", "compat", "migration")):
        alternatives.append(Alternative(
            id="backward-compat",
            title="Backward-compatible approach",
            description=(
                "Keeps the existing API surface intact while adding the improvement "
                "behind a feature flag or adapter layer."
            ),
            trade_offs=["More code to maintain", "Dual paths during transition"],
            effort_estimate="medium",
            confidence=0.75,
        ))

    if any(kw in reason_lower for kw in ("test", "coverage", "untested")):
        alternatives.append(Alternative(
            id="test-first",
            title="Test-first approach",
            description=(
                "Adds comprehensive test coverage before making the change, "
                "ensuring behavior is preserved."
            ),
            trade_offs=["Takes longer", "Tests may be brittle initially"],
            effort_estimate="medium",
            confidence=0.9,
        ))

    # Always offer a "defer" option
    if len(alternatives) < max_alternatives:
        alternatives.append(Alternative(
            id="defer",
            title="Defer to future iteration",
            description=(
                "Log the finding as tech debt and address it in a "
                "dedicated cleanup sprint with proper context."
            ),
            trade_offs=["Issue remains temporarily", "May accumulate debt"],
            effort_estimate="low",
            confidence=0.7,
        ))

    negotiation.alternatives = alternatives[:max_alternatives]
    negotiation.status = NegotiationStatus.ALTERNATIVES_PROPOSED

    logger.info(
        "Generated %d alternatives for negotiation %s",
        len(negotiation.alternatives),
        negotiation_id,
    )
    return negotiation.alternatives


def select_alternative(
    negotiation_id: uuid.UUID,
    alternative_id: str,
    *,
    developer_comment: str = "",
) -> NegotiationRequest:
    """Developer selects an alternative, resolving the negotiation.

    Parameters
    ----------
    negotiation_id:
        The negotiation to resolve.
    alternative_id:
        ID of the selected alternative (or "original" to accept original).
    developer_comment:
        Optional comment from developer.
    """
    negotiation = _negotiations.get(negotiation_id)
    if not negotiation:
        raise ValueError(f"Negotiation {negotiation_id} not found")

    if alternative_id == "original":
        negotiation.status = NegotiationStatus.ACCEPTED
        outcome = NegotiationOutcome(
            negotiation_id=negotiation_id,
            original_accepted=True,
            developer_comment=developer_comment,
        )
    else:
        valid_ids = {a.id for a in negotiation.alternatives}
        if alternative_id not in valid_ids:
            raise ValueError(
                f"Alternative '{alternative_id}' not found. "
                f"Valid: {valid_ids}"
            )
        negotiation.status = NegotiationStatus.ACCEPTED
        negotiation.selected_alternative_id = alternative_id
        outcome = NegotiationOutcome(
            negotiation_id=negotiation_id,
            original_accepted=False,
            alternative_selected=alternative_id,
            developer_comment=developer_comment,
        )

    negotiation.resolved_at = datetime.now(UTC)
    _outcomes.append(outcome)

    logger.info(
        "Negotiation %s resolved: selected=%s",
        negotiation_id,
        alternative_id,
    )
    return negotiation


def escalate_negotiation(negotiation_id: uuid.UUID) -> NegotiationRequest:
    """Escalate a negotiation to a human tech lead."""
    negotiation = _negotiations.get(negotiation_id)
    if not negotiation:
        raise ValueError(f"Negotiation {negotiation_id} not found")

    negotiation.status = NegotiationStatus.ESCALATED
    negotiation.resolved_at = datetime.now(UTC)

    logger.info("Negotiation %s escalated to human", negotiation_id)
    return negotiation


def withdraw_negotiation(negotiation_id: uuid.UUID) -> NegotiationRequest:
    """Agent withdraws its original suggestion."""
    negotiation = _negotiations.get(negotiation_id)
    if not negotiation:
        raise ValueError(f"Negotiation {negotiation_id} not found")

    negotiation.status = NegotiationStatus.WITHDRAWN
    negotiation.resolved_at = datetime.now(UTC)

    logger.info("Negotiation %s withdrawn", negotiation_id)
    return negotiation


def get_negotiation(negotiation_id: uuid.UUID) -> NegotiationRequest | None:
    """Get a negotiation by ID."""
    return _negotiations.get(negotiation_id)


def get_negotiation_stats() -> dict[str, Any]:
    """Get aggregated negotiation statistics for learning."""
    total = len(_outcomes)
    if total == 0:
        return {
            "total_negotiations": 0,
            "original_accepted_rate": 0.0,
            "alternative_selected_rate": 0.0,
            "most_selected_alternatives": {},
        }

    original_accepted = sum(1 for o in _outcomes if o.original_accepted)
    alternative_counts: dict[str, int] = {}
    for o in _outcomes:
        if o.alternative_selected:
            alternative_counts[o.alternative_selected] = (
                alternative_counts.get(o.alternative_selected, 0) + 1
            )

    return {
        "total_negotiations": total,
        "original_accepted_rate": round(original_accepted / total * 100, 1),
        "alternative_selected_rate": round((total - original_accepted) / total * 100, 1),
        "most_selected_alternatives": dict(
            sorted(alternative_counts.items(), key=lambda x: x[1], reverse=True)
        ),
    }


def negotiation_to_json(negotiation: NegotiationRequest) -> dict[str, Any]:
    """Serialize a NegotiationRequest to JSON-compatible dict."""
    return {
        "id": str(negotiation.id),
        "review_id": str(negotiation.review_id) if negotiation.review_id else None,
        "ticket_id": str(negotiation.ticket_id) if negotiation.ticket_id else None,
        "finding_index": negotiation.finding_index,
        "original_suggestion": negotiation.original_suggestion,
        "rejection_reason": negotiation.rejection_reason,
        "status": negotiation.status.value,
        "alternatives": [
            {
                "id": a.id,
                "title": a.title,
                "description": a.description,
                "trade_offs": a.trade_offs,
                "effort_estimate": a.effort_estimate,
                "confidence": a.confidence,
            }
            for a in negotiation.alternatives
        ],
        "selected_alternative_id": negotiation.selected_alternative_id,
        "created_at": negotiation.created_at.isoformat(),
        "resolved_at": negotiation.resolved_at.isoformat() if negotiation.resolved_at else None,
    }
