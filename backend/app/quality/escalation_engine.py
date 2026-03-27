"""Confidence-Gated Human-in-the-Loop Escalation Engine.

Evaluates AI-generated code changes and routes them through appropriate
human review tiers based on confidence scores, risk patterns, change size,
and security findings.  Low-risk, high-confidence changes are auto-approved
while sensitive or uncertain changes are escalated for human review.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────────

class EscalationTier(StrEnum):
    AUTO_APPROVE = "auto_approve"
    DEVELOPER_REVIEW = "developer_review"
    SENIOR_REVIEW = "senior_review"
    SECURITY_REVIEW = "security_review"


class EscalationReason(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    HIGH_RISK_PATH = "high_risk_path"
    SECURITY_SURFACE = "security_surface"
    SCHEMA_CHANGE = "schema_change"
    NEW_DEPENDENCY = "new_dependency"
    LARGE_CHANGE = "large_change"
    PII_DETECTED = "pii_detected"
    CRYPTO_CODE = "crypto_code"


# ── SLA mapping ───────────────────────────────────────────────────────────

_SLA_HOURS: dict[EscalationTier, int] = {
    EscalationTier.SECURITY_REVIEW: 2,
    EscalationTier.SENIOR_REVIEW: 8,
    EscalationTier.DEVELOPER_REVIEW: 24,
    EscalationTier.AUTO_APPROVE: 0,
}


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class EscalationItem:
    """A single escalation record."""

    id: str
    tier: EscalationTier
    reasons: list[EscalationReason]
    confidence_score: float
    file_paths: list[str]
    change_size: int
    priority: int
    sla_hours: int
    created_at: datetime
    resolved_at: datetime | None = None
    resolution: str | None = None


@dataclass
class EscalationPolicy:
    """Configuration governing escalation behaviour."""

    high_risk_patterns: list[str] = field(default_factory=list)
    confidence_threshold: float = 0.7
    max_auto_approve_lines: int = 50
    require_human_for_irreversible: bool = True


@dataclass
class EscalationStats:
    """Aggregate statistics for the escalation queue."""

    total_escalations: int = 0
    by_tier: dict[str, int] = field(default_factory=dict)
    avg_resolution_time_hours: float = 0.0
    escalation_rate: float = 0.0
    sla_breaches: int = 0


# ── In-memory storage ────────────────────────────────────────────────────

_escalation_queue: list[EscalationItem] = []
_policy: EscalationPolicy = EscalationPolicy()
_resolution_history: list[EscalationItem] = []


# ── Public API ────────────────────────────────────────────────────────────

def configure_policy(
    high_risk_patterns: list[str],
    confidence_threshold: float = 0.7,
    max_auto_lines: int = 50,
    require_human_irreversible: bool = True,
) -> EscalationPolicy:
    """Create and store the active escalation policy."""
    global _policy  # noqa: PLW0603
    _policy = EscalationPolicy(
        high_risk_patterns=high_risk_patterns,
        confidence_threshold=confidence_threshold,
        max_auto_approve_lines=max_auto_lines,
        require_human_for_irreversible=require_human_irreversible,
    )
    logger.info(
        "Escalation policy configured: threshold=%.2f, max_auto_lines=%d, patterns=%s",
        confidence_threshold,
        max_auto_lines,
        high_risk_patterns,
    )
    return _policy


def matches_high_risk_pattern(file_path: str, patterns: list[str]) -> bool:
    """Return True if *file_path* matches any high-risk pattern."""
    return any(pattern in file_path for pattern in patterns)


def compute_composite_confidence(
    confidence_score: float,
    hallucination_score: float,
    security_clean: bool,
) -> float:
    """Compute a weighted composite confidence value in [0, 1].

    Weights:
        confidence_score  – 50 %
        hallucination     – 30 % (inverted: lower hallucination = higher confidence)
        security_clean    – 20 %
    """
    security_value = 1.0 if security_clean else 0.0
    composite = (
        0.5 * confidence_score
        + 0.3 * (1.0 - hallucination_score)
        + 0.2 * security_value
    )
    return max(0.0, min(1.0, composite))


def evaluate_escalation(
    file_paths: list[str],
    change_size: int,
    confidence_score: float,
    hallucination_score: float = 0.0,
    has_security_findings: bool = False,
    is_irreversible: bool = False,
) -> EscalationItem:
    """Evaluate a change and assign an escalation tier.

    The function collects reasons then picks the highest tier that applies.
    """
    reasons: list[EscalationReason] = []

    # ── Collect reasons ───────────────────────────────────────────────
    composite = compute_composite_confidence(
        confidence_score, hallucination_score, not has_security_findings,
    )

    if composite < _policy.confidence_threshold:
        reasons.append(EscalationReason.LOW_CONFIDENCE)

    for fp in file_paths:
        if matches_high_risk_pattern(fp, _policy.high_risk_patterns):
            reasons.append(EscalationReason.HIGH_RISK_PATH)
            break

    if has_security_findings:
        reasons.append(EscalationReason.SECURITY_SURFACE)

    if change_size > _policy.max_auto_approve_lines * 4:
        reasons.append(EscalationReason.LARGE_CHANGE)

    # Heuristic detections based on file paths
    for fp in file_paths:
        lower = fp.lower()
        if "migration" in lower or "schema" in lower:
            reasons.append(EscalationReason.SCHEMA_CHANGE)
            break

    for fp in file_paths:
        lower = fp.lower()
        if "crypto" in lower or "encrypt" in lower or "signing" in lower:
            reasons.append(EscalationReason.CRYPTO_CODE)
            break

    for fp in file_paths:
        lower = fp.lower()
        if "pii" in lower or "personal" in lower or "gdpr" in lower:
            reasons.append(EscalationReason.PII_DETECTED)
            break

    # ── Determine tier ────────────────────────────────────────────────
    tier = _determine_tier(reasons, change_size, is_irreversible)

    # ── Priority (lower = more urgent) ────────────────────────────────
    _tier_priority = {
        EscalationTier.SECURITY_REVIEW: 1,
        EscalationTier.SENIOR_REVIEW: 2,
        EscalationTier.DEVELOPER_REVIEW: 3,
        EscalationTier.AUTO_APPROVE: 4,
    }
    priority = _tier_priority[tier]

    item = EscalationItem(
        id=str(uuid.uuid4()),
        tier=tier,
        reasons=reasons,
        confidence_score=composite,
        file_paths=file_paths,
        change_size=change_size,
        priority=priority,
        sla_hours=_SLA_HOURS[tier],
        created_at=datetime.now(UTC),
    )

    if tier == EscalationTier.AUTO_APPROVE:
        item.resolved_at = datetime.now(UTC)
        item.resolution = "approved"
        _resolution_history.append(item)
        logger.info("Auto-approved escalation %s", item.id)
    else:
        _escalation_queue.append(item)
        logger.info("Escalation %s queued as %s (reasons=%s)", item.id, tier, reasons)

    return item


def resolve_escalation(item_id: str, resolution: str) -> EscalationItem:
    """Resolve a pending escalation item.

    Parameters
    ----------
    item_id:
        UUID of the escalation to resolve.
    resolution:
        One of ``"approved"``, ``"rejected"``, ``"modified"``.

    Raises
    ------
    ValueError
        If *item_id* is not found in the pending queue.
    """
    for idx, item in enumerate(_escalation_queue):
        if item.id == item_id:
            item.resolved_at = datetime.now(UTC)
            item.resolution = resolution
            _escalation_queue.pop(idx)
            _resolution_history.append(item)
            logger.info("Resolved escalation %s as %s", item_id, resolution)
            return item
    raise ValueError(f"Escalation item {item_id!r} not found in pending queue")


def get_pending_escalations(
    tier: EscalationTier | None = None,
) -> list[EscalationItem]:
    """Return pending (unresolved) escalation items, optionally filtered by tier."""
    if tier is None:
        return list(_escalation_queue)
    return [item for item in _escalation_queue if item.tier == tier]


def get_sla_breaches() -> list[EscalationItem]:
    """Return pending items that have exceeded their SLA window."""
    now = datetime.now(UTC)
    breaches: list[EscalationItem] = []
    for item in _escalation_queue:
        if item.sla_hours <= 0:
            continue
        elapsed_hours = (now - item.created_at).total_seconds() / 3600
        if elapsed_hours > item.sla_hours:
            breaches.append(item)
    return breaches


def get_escalation_stats() -> EscalationStats:
    """Compute aggregate statistics across all escalations."""
    all_items = list(_resolution_history) + list(_escalation_queue)
    total = len(all_items)

    by_tier: dict[str, int] = {}
    for item in all_items:
        by_tier[item.tier.value] = by_tier.get(item.tier.value, 0) + 1

    # Average resolution time (only resolved items)
    resolved = [i for i in _resolution_history if i.resolved_at and i.created_at]
    if resolved:
        total_hours = sum(
            (i.resolved_at - i.created_at).total_seconds() / 3600  # type: ignore[operator]
            for i in resolved
        )
        avg_hours = total_hours / len(resolved)
    else:
        avg_hours = 0.0

    # Escalation rate = non-auto / total
    non_auto = sum(1 for i in all_items if i.tier != EscalationTier.AUTO_APPROVE)
    escalation_rate = non_auto / total if total else 0.0

    sla_breaches = len(get_sla_breaches())

    return EscalationStats(
        total_escalations=total,
        by_tier=by_tier,
        avg_resolution_time_hours=avg_hours,
        escalation_rate=escalation_rate,
        sla_breaches=sla_breaches,
    )


def clear_escalation_data() -> None:
    """Reset all in-memory escalation state.  Intended for tests."""
    global _policy  # noqa: PLW0603
    _escalation_queue.clear()
    _resolution_history.clear()
    _policy = EscalationPolicy()


def escalation_item_to_json(item: EscalationItem) -> dict:
    """Serialise an EscalationItem to a JSON-compatible dict."""
    return {
        "id": item.id,
        "tier": item.tier.value,
        "reasons": [r.value for r in item.reasons],
        "confidence_score": item.confidence_score,
        "file_paths": item.file_paths,
        "change_size": item.change_size,
        "priority": item.priority,
        "sla_hours": item.sla_hours,
        "created_at": item.created_at.isoformat(),
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "resolution": item.resolution,
    }


# ── Internal helpers ──────────────────────────────────────────────────────

def _determine_tier(
    reasons: list[EscalationReason],
    change_size: int,
    is_irreversible: bool,
) -> EscalationTier:
    """Pick the highest-severity tier given the collected reasons."""
    reason_set = set(reasons)

    # Security tier triggers
    security_triggers = {
        EscalationReason.SECURITY_SURFACE,
        EscalationReason.CRYPTO_CODE,
        EscalationReason.PII_DETECTED,
    }
    if reason_set & security_triggers:
        return EscalationTier.SECURITY_REVIEW

    # High-risk path with low confidence → security
    high_risk_low_conf = (
        EscalationReason.HIGH_RISK_PATH in reason_set
        and EscalationReason.LOW_CONFIDENCE in reason_set
    )
    if high_risk_low_conf:
        return EscalationTier.SECURITY_REVIEW

    # Senior tier triggers
    senior_triggers = {
        EscalationReason.LARGE_CHANGE,
        EscalationReason.SCHEMA_CHANGE,
    }
    if reason_set & senior_triggers:
        return EscalationTier.SENIOR_REVIEW

    # Irreversible actions require at least developer review
    if is_irreversible and _policy.require_human_for_irreversible:
        return EscalationTier.DEVELOPER_REVIEW

    # Any remaining reasons → developer review
    if reasons:
        return EscalationTier.DEVELOPER_REVIEW

    # Small, confident, safe → auto-approve
    if change_size <= _policy.max_auto_approve_lines:
        return EscalationTier.AUTO_APPROVE

    return EscalationTier.DEVELOPER_REVIEW
