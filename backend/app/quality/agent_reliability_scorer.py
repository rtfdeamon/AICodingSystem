"""Agent Reliability Scorer — multi-dimensional reliability assessment.

Production AI agents need more than accuracy — they need *reliability*.
This module scores agents across four dimensions: consistency (same input →
same quality), robustness (performance under perturbation), calibration
(confidence matches actual quality), and safety (how catastrophic mistakes
are).  Inspired by the emerging science of AI agent reliability.

Based on:
- Fortune / Narayanan & Kapoor "AI Agent Reliability" (2026)
- Anthropic "Demystifying Evals for AI Agents" (2026)
- Galileo "Agent Evaluation Framework: Metrics, Rubrics & Benchmarks" (2026)
- Evidently AI "10 AI Agent Benchmarks" (2026)
- Amazon "Evaluating AI Agents: Real-world Lessons" (2026)

Key capabilities:
- Four reliability dimensions: consistency, robustness, calibration, safety
- Per-dimension scoring (0-1) with weighted composite
- Confidence calibration: expected vs observed quality correlation
- Safety incident tracking with severity classification
- Rolling reliability trending with window-based analysis
- Quality gate: reliable / acceptable / fragile / unreliable
- Batch reliability report across all agents
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class ReliabilityGrade(StrEnum):
    RELIABLE = "reliable"  # >= 0.85
    ACCEPTABLE = "acceptable"  # >= 0.65
    FRAGILE = "fragile"  # >= 0.45
    UNRELIABLE = "unreliable"  # < 0.45


class SafetySeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class ObservationRecord:
    """Single agent execution observation."""

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent: str = ""
    input_hash: str = ""
    quality_score: float = 0.0  # actual quality 0-1
    confidence: float = 0.0  # agent's stated confidence 0-1
    is_perturbed: bool = False  # was input perturbed?
    safety_incident: bool = False
    safety_severity: SafetySeverity | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReliabilityConfig:
    """Configuration for reliability scoring."""

    reliable_threshold: float = 0.85
    acceptable_threshold: float = 0.65
    fragile_threshold: float = 0.45
    min_samples: int = 5
    # Dimension weights (must sum to 1.0)
    consistency_weight: float = 0.30
    robustness_weight: float = 0.25
    calibration_weight: float = 0.20
    safety_weight: float = 0.25


@dataclass
class DimensionScore:
    """Score for one reliability dimension."""

    dimension: str
    score: float
    sample_count: int
    details: str = ""


@dataclass
class ReliabilityScore:
    """Composite reliability score for an agent."""

    agent: str
    consistency: DimensionScore
    robustness: DimensionScore
    calibration: DimensionScore
    safety: DimensionScore
    composite_score: float
    grade: ReliabilityGrade
    gate: GateDecision
    sample_count: int
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReliabilityTrend:
    """Reliability trending over a window."""

    agent: str
    current_score: float
    previous_score: float
    delta: float
    direction: str  # "improving", "stable", "degrading"


@dataclass
class BatchReliabilityReport:
    """Reliability across all agents."""

    scores: list[ReliabilityScore]
    trends: list[ReliabilityTrend]
    overall_score: float
    overall_grade: ReliabilityGrade
    least_reliable_agent: str
    most_reliable_agent: str
    total_observations: int


# ── Pure helpers ─────────────────────────────────────────────────────────

def _compute_consistency(records: list[ObservationRecord]) -> DimensionScore:
    """Consistency: variance in quality scores for the same inputs."""
    if len(records) < 2:
        return DimensionScore("consistency", 1.0, len(records), "insufficient data")

    # Group by input_hash
    groups: dict[str, list[float]] = {}
    for r in records:
        if r.input_hash:
            groups.setdefault(r.input_hash, []).append(r.quality_score)

    if not groups:
        # No repeated inputs — measure overall variance
        scores = [r.quality_score for r in records]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        consistency = max(0.0, 1.0 - variance * 4)  # scale variance
        return DimensionScore("consistency", round(consistency, 4), len(records),
                              f"overall variance={variance:.4f}")

    variances = []
    for _hash, qualities in groups.items():
        if len(qualities) >= 2:
            mean = sum(qualities) / len(qualities)
            var = sum((q - mean) ** 2 for q in qualities) / len(qualities)
            variances.append(var)

    if not variances:
        return DimensionScore("consistency", 1.0, len(records), "no repeated inputs")

    avg_variance = sum(variances) / len(variances)
    # Low variance → high consistency
    consistency = max(0.0, 1.0 - avg_variance * 4)
    return DimensionScore(
        "consistency", round(consistency, 4), len(records),
        f"avg_variance={avg_variance:.4f}, groups={len(variances)}",
    )


def _compute_robustness(records: list[ObservationRecord]) -> DimensionScore:
    """Robustness: quality drop under perturbation."""
    normal = [r.quality_score for r in records if not r.is_perturbed]
    perturbed = [r.quality_score for r in records if r.is_perturbed]

    if not normal or not perturbed:
        return DimensionScore("robustness", 1.0, len(records),
                              "no perturbation data")

    normal_avg = sum(normal) / len(normal)
    perturbed_avg = sum(perturbed) / len(perturbed)

    drop = 0.0 if normal_avg == 0 else max(0.0, (normal_avg - perturbed_avg) / normal_avg)

    robustness = max(0.0, 1.0 - drop * 2)  # >50% drop → 0
    return DimensionScore(
        "robustness", round(robustness, 4), len(records),
        f"normal_avg={normal_avg:.3f}, perturbed_avg={perturbed_avg:.3f}, drop={drop:.3f}",
    )


def _compute_calibration(records: list[ObservationRecord]) -> DimensionScore:
    """Calibration: correlation between confidence and actual quality."""
    valid = [r for r in records if r.confidence > 0]
    if len(valid) < 2:
        return DimensionScore("calibration", 1.0, len(valid), "insufficient data")

    # Mean absolute error between confidence and quality
    errors = [abs(r.confidence - r.quality_score) for r in valid]
    mae = sum(errors) / len(errors)

    calibration = max(0.0, 1.0 - mae * 2)  # MAE 0.5 → score 0
    return DimensionScore(
        "calibration", round(calibration, 4), len(valid),
        f"mae={mae:.4f}, samples={len(valid)}",
    )


def _compute_safety(records: list[ObservationRecord]) -> DimensionScore:
    """Safety: frequency and severity of safety incidents."""
    if not records:
        return DimensionScore("safety", 1.0, 0, "no records")

    severity_weights = {
        SafetySeverity.LOW: 0.1,
        SafetySeverity.MEDIUM: 0.3,
        SafetySeverity.HIGH: 0.6,
        SafetySeverity.CRITICAL: 1.0,
    }

    incidents = [r for r in records if r.safety_incident]
    if not incidents:
        return DimensionScore("safety", 1.0, len(records), "no incidents")

    weighted_severity = sum(
        severity_weights.get(r.safety_severity, 0.5) for r in incidents
    )
    # Normalize by total records
    incident_impact = weighted_severity / len(records)
    safety = max(0.0, 1.0 - incident_impact * 3)

    return DimensionScore(
        "safety", round(safety, 4), len(records),
        f"incidents={len(incidents)}, weighted_severity={weighted_severity:.2f}",
    )


def _grade_reliability(score: float, config: ReliabilityConfig) -> ReliabilityGrade:
    """Grade a reliability score."""
    if score >= config.reliable_threshold:
        return ReliabilityGrade.RELIABLE
    if score >= config.acceptable_threshold:
        return ReliabilityGrade.ACCEPTABLE
    if score >= config.fragile_threshold:
        return ReliabilityGrade.FRAGILE
    return ReliabilityGrade.UNRELIABLE


def _gate_from_grade(grade: ReliabilityGrade) -> GateDecision:
    """Map grade to gate decision."""
    if grade in {ReliabilityGrade.RELIABLE, ReliabilityGrade.ACCEPTABLE}:
        return GateDecision.PASS
    if grade == ReliabilityGrade.FRAGILE:
        return GateDecision.WARN
    return GateDecision.BLOCK


# ── Main class ───────────────────────────────────────────────────────────

class AgentReliabilityScorer:
    """Scores agent reliability across multiple dimensions."""

    def __init__(self, config: ReliabilityConfig | None = None) -> None:
        self._config = config or ReliabilityConfig()
        self._observations: list[ObservationRecord] = []
        self._history: dict[str, list[float]] = {}  # agent → past composite scores

    def record_observation(
        self,
        agent: str,
        input_hash: str = "",
        quality_score: float = 0.0,
        confidence: float = 0.0,
        is_perturbed: bool = False,
        safety_incident: bool = False,
        safety_severity: SafetySeverity | None = None,
    ) -> ObservationRecord:
        """Record an agent execution observation."""
        rec = ObservationRecord(
            agent=agent,
            input_hash=input_hash,
            quality_score=max(0.0, min(1.0, quality_score)),
            confidence=max(0.0, min(1.0, confidence)),
            is_perturbed=is_perturbed,
            safety_incident=safety_incident,
            safety_severity=safety_severity,
        )
        self._observations.append(rec)
        return rec

    def evaluate_agent(self, agent: str) -> ReliabilityScore:
        """Evaluate reliability for a specific agent."""
        records = [r for r in self._observations if r.agent == agent]

        consistency = _compute_consistency(records)
        robustness = _compute_robustness(records)
        calibration = _compute_calibration(records)
        safety = _compute_safety(records)

        cfg = self._config
        composite = (
            cfg.consistency_weight * consistency.score
            + cfg.robustness_weight * robustness.score
            + cfg.calibration_weight * calibration.score
            + cfg.safety_weight * safety.score
        )
        composite = round(composite, 4)

        grade = _grade_reliability(composite, cfg)
        gate = _gate_from_grade(grade)

        # Track history
        self._history.setdefault(agent, []).append(composite)

        return ReliabilityScore(
            agent=agent,
            consistency=consistency,
            robustness=robustness,
            calibration=calibration,
            safety=safety,
            composite_score=composite,
            grade=grade,
            gate=gate,
            sample_count=len(records),
        )

    def get_trend(self, agent: str) -> ReliabilityTrend:
        """Get reliability trend for an agent."""
        history = self._history.get(agent, [])
        if len(history) < 2:
            current = history[-1] if history else 0.0
            return ReliabilityTrend(
                agent=agent,
                current_score=current,
                previous_score=current,
                delta=0.0,
                direction="stable",
            )

        current = history[-1]
        previous = history[-2]
        delta = round(current - previous, 4)

        if delta > 0.05:
            direction = "improving"
        elif delta < -0.05:
            direction = "degrading"
        else:
            direction = "stable"

        return ReliabilityTrend(
            agent=agent,
            current_score=current,
            previous_score=previous,
            delta=delta,
            direction=direction,
        )

    def batch_evaluate(self) -> BatchReliabilityReport:
        """Evaluate reliability across all agents."""
        agents = list({r.agent for r in self._observations})

        scores = [self.evaluate_agent(a) for a in agents]
        trends = [self.get_trend(a) for a in agents]

        overall = (
            sum(s.composite_score for s in scores) / len(scores) if scores else 1.0
        )
        overall_grade = _grade_reliability(overall, self._config)

        least = min(scores, key=lambda s: s.composite_score) if scores else None
        most = max(scores, key=lambda s: s.composite_score) if scores else None

        return BatchReliabilityReport(
            scores=scores,
            trends=trends,
            overall_score=round(overall, 4),
            overall_grade=overall_grade,
            least_reliable_agent=least.agent if least else "",
            most_reliable_agent=most.agent if most else "",
            total_observations=len(self._observations),
        )
