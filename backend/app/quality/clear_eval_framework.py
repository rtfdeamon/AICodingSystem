"""CLEAR Evaluation Framework — multi-dimensional AI system evaluation
across Cost, Latency, Efficacy, Assurance, and Reliability.

Traditional AI benchmarks optimise for a single metric (accuracy),
while enterprise deployments require holistic evaluation across five
critical dimensions.  CLEAR fills this gap with a structured scoring
model and quality gates per dimension.

Based on:
- "Beyond Accuracy: A Multi-Dimensional Framework for Evaluating
  Enterprise Agentic AI Systems" (arXiv:2511.14136, Nov 2025)
- LangChain "2026 State of AI Agents" (quality as #1 barrier)
- Maxim.ai "AI Evaluation Metrics 2026"
- Master of Code "AI Agent Evaluation" (2026)
- Galileo reliability metrics and compliance audit logs

Key capabilities:
- Five-dimension scoring: Cost, Latency, Efficacy, Assurance, Reliability
- Per-dimension configurable thresholds and weights
- Composite CLEAR score (weighted harmonic mean)
- Trend detection: track score changes over time
- Dimension-level quality gates (pass/warn/fail)
- Overall system health verdict
- Batch evaluation across multiple AI stages/agents
"""

from __future__ import annotations

import logging
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class Dimension(StrEnum):
    COST = "cost"
    LATENCY = "latency"
    EFFICACY = "efficacy"
    ASSURANCE = "assurance"
    RELIABILITY = "reliability"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class Trend(StrEnum):
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class DimensionScore:
    """Score for a single CLEAR dimension."""

    dimension: Dimension
    score: float  # 0-1, higher is better
    raw_value: float  # original metric value
    threshold_pass: float
    threshold_warn: float
    gate: GateDecision
    details: str = ""


@dataclass
class CLEARScore:
    """Composite CLEAR evaluation result."""

    id: str
    dimensions: dict[Dimension, DimensionScore]
    composite_score: float  # 0-1
    gate_decision: GateDecision
    failing_dimensions: list[Dimension]
    warning_dimensions: list[Dimension]
    agent_id: str = ""
    stage: str = ""
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class TrendAnalysis:
    """Trend analysis for a dimension over time."""

    dimension: Dimension
    trend: Trend
    current_score: float
    previous_score: float
    change_pct: float
    data_points: int


@dataclass
class BatchCLEARReport:
    """Report across multiple CLEAR evaluations."""

    scores: list[CLEARScore]
    avg_composite: float
    dimension_averages: dict[Dimension, float]
    weakest_dimension: Dimension
    strongest_dimension: Dimension
    gate_decision: GateDecision
    trends: list[TrendAnalysis]
    total_evaluations: int


# ── Scoring helpers ──────────────────────────────────────────────────────

def _score_cost(cost_usd: float, budget_usd: float) -> float:
    """Score cost: 1.0 = free, 0.0 = at/over budget."""
    if budget_usd <= 0:
        return 0.0
    ratio = cost_usd / budget_usd
    return max(0.0, min(1.0, 1.0 - ratio))


def _score_latency(latency_ms: float, target_ms: float) -> float:
    """Score latency: 1.0 = instant, 0.0 = 2x target or worse."""
    if target_ms <= 0:
        return 0.0
    ratio = latency_ms / target_ms
    return max(0.0, min(1.0, 1.0 - (ratio - 1.0) / 1.0)) if ratio > 1.0 else 1.0


def _score_efficacy(
    correct: int,
    total: int,
    quality_score: float = 0.0,
) -> float:
    """Score efficacy from accuracy and quality metrics."""
    if total == 0:
        return quality_score if quality_score > 0 else 0.5
    accuracy = correct / total
    if quality_score > 0:
        return (accuracy + quality_score) / 2.0
    return accuracy


def _score_assurance(
    safety_pass_rate: float,
    compliance_rate: float = 1.0,
    audit_coverage: float = 1.0,
) -> float:
    """Score assurance: safety, compliance, and audit coverage."""
    return (safety_pass_rate + compliance_rate + audit_coverage) / 3.0


def _score_reliability(
    success_rate: float,
    consistency: float = 1.0,
    error_recovery_rate: float = 1.0,
) -> float:
    """Score reliability: success rate, consistency, error recovery."""
    return (success_rate * 2 + consistency + error_recovery_rate) / 4.0


def _weighted_harmonic_mean(
    scores: dict[Dimension, float],
    weights: dict[Dimension, float],
) -> float:
    """Compute weighted harmonic mean of dimension scores."""
    total_weight = 0.0
    weighted_inv_sum = 0.0
    for dim, score in scores.items():
        w = weights.get(dim, 1.0)
        if score <= 0:
            return 0.0
        weighted_inv_sum += w / score
        total_weight += w
    if total_weight == 0 or weighted_inv_sum == 0:
        return 0.0
    return total_weight / weighted_inv_sum


# ── Main class ───────────────────────────────────────────────────────────

class CLEAREvalFramework:
    """Multi-dimensional AI evaluation using the CLEAR framework.

    Evaluates AI stages and agents across Cost, Latency, Efficacy,
    Assurance, and Reliability to provide a holistic quality picture.
    """

    def __init__(
        self,
        weights: dict[Dimension, float] | None = None,
        pass_thresholds: dict[Dimension, float] | None = None,
        warn_thresholds: dict[Dimension, float] | None = None,
    ) -> None:
        self.weights = weights or {
            Dimension.COST: 1.0,
            Dimension.LATENCY: 1.0,
            Dimension.EFFICACY: 2.0,  # Quality is paramount
            Dimension.ASSURANCE: 1.5,
            Dimension.RELIABILITY: 1.5,
        }
        self.pass_thresholds = pass_thresholds or {
            Dimension.COST: 0.5,
            Dimension.LATENCY: 0.6,
            Dimension.EFFICACY: 0.7,
            Dimension.ASSURANCE: 0.8,
            Dimension.RELIABILITY: 0.7,
        }
        self.warn_thresholds = warn_thresholds or {
            Dimension.COST: 0.3,
            Dimension.LATENCY: 0.4,
            Dimension.EFFICACY: 0.5,
            Dimension.ASSURANCE: 0.6,
            Dimension.RELIABILITY: 0.5,
        }
        self._history: list[CLEARScore] = []

    # ── Evaluation ───────────────────────────────────────────────────

    def evaluate(
        self,
        cost_usd: float = 0.0,
        budget_usd: float = 1.0,
        latency_ms: float = 0.0,
        target_latency_ms: float = 5000.0,
        correct: int = 0,
        total: int = 0,
        quality_score: float = 0.0,
        safety_pass_rate: float = 1.0,
        compliance_rate: float = 1.0,
        audit_coverage: float = 1.0,
        success_rate: float = 1.0,
        consistency: float = 1.0,
        error_recovery_rate: float = 1.0,
        agent_id: str = "",
        stage: str = "",
    ) -> CLEARScore:
        """Evaluate all five CLEAR dimensions and compute composite."""
        raw_scores: dict[Dimension, float] = {
            Dimension.COST: _score_cost(cost_usd, budget_usd),
            Dimension.LATENCY: _score_latency(latency_ms, target_latency_ms),
            Dimension.EFFICACY: _score_efficacy(correct, total, quality_score),
            Dimension.ASSURANCE: _score_assurance(
                safety_pass_rate, compliance_rate, audit_coverage,
            ),
            Dimension.RELIABILITY: _score_reliability(
                success_rate, consistency, error_recovery_rate,
            ),
        }

        raw_values: dict[Dimension, float] = {
            Dimension.COST: cost_usd,
            Dimension.LATENCY: latency_ms,
            Dimension.EFFICACY: (correct / max(total, 1)) if total else quality_score,
            Dimension.ASSURANCE: safety_pass_rate,
            Dimension.RELIABILITY: success_rate,
        }

        dimensions: dict[Dimension, DimensionScore] = {}
        failing: list[Dimension] = []
        warning: list[Dimension] = []

        for dim in Dimension:
            score = raw_scores[dim]
            pass_t = self.pass_thresholds[dim]
            warn_t = self.warn_thresholds[dim]

            if score >= pass_t:
                gate = GateDecision.PASS
            elif score >= warn_t:
                gate = GateDecision.WARN
                warning.append(dim)
            else:
                gate = GateDecision.FAIL
                failing.append(dim)

            dimensions[dim] = DimensionScore(
                dimension=dim,
                score=score,
                raw_value=raw_values[dim],
                threshold_pass=pass_t,
                threshold_warn=warn_t,
                gate=gate,
                details=f"{dim.value}: {score:.2f} (raw={raw_values[dim]:.2f})",
            )

        composite = _weighted_harmonic_mean(raw_scores, self.weights)

        if failing:
            overall_gate = GateDecision.FAIL
        elif warning:
            overall_gate = GateDecision.WARN
        else:
            overall_gate = GateDecision.PASS

        result = CLEARScore(
            id=uuid.uuid4().hex[:12],
            dimensions=dimensions,
            composite_score=composite,
            gate_decision=overall_gate,
            failing_dimensions=failing,
            warning_dimensions=warning,
            agent_id=agent_id,
            stage=stage,
        )
        self._history.append(result)
        return result

    # ── Trend analysis ───────────────────────────────────────────────

    def analyze_trends(self, window: int = 10) -> list[TrendAnalysis]:
        """Analyze score trends over recent evaluations."""
        if len(self._history) < 2:
            return []

        recent = self._history[-window:]
        if len(self._history) > window:
            older = self._history[-window * 2 : -window]
        else:
            older = self._history[:1]

        trends: list[TrendAnalysis] = []
        for dim in Dimension:
            recent_scores = [s.dimensions[dim].score for s in recent if dim in s.dimensions]
            older_scores = [s.dimensions[dim].score for s in older if dim in s.dimensions]

            if not recent_scores or not older_scores:
                continue

            curr = statistics.mean(recent_scores)
            prev = statistics.mean(older_scores)
            change = ((curr - prev) / max(prev, 0.001)) * 100

            if change > 5:
                trend = Trend.IMPROVING
            elif change < -5:
                trend = Trend.DEGRADING
            else:
                trend = Trend.STABLE

            trends.append(TrendAnalysis(
                dimension=dim,
                trend=trend,
                current_score=curr,
                previous_score=prev,
                change_pct=change,
                data_points=len(recent_scores),
            ))

        return trends

    # ── Batch evaluation ─────────────────────────────────────────────

    def batch_report(self) -> BatchCLEARReport:
        """Generate a report across all evaluations."""
        if not self._history:
            return BatchCLEARReport(
                scores=[],
                avg_composite=0.0,
                dimension_averages={d: 0.0 for d in Dimension},
                weakest_dimension=Dimension.COST,
                strongest_dimension=Dimension.COST,
                gate_decision=GateDecision.PASS,
                trends=[],
                total_evaluations=0,
            )

        composites = [s.composite_score for s in self._history]
        avg_composite = statistics.mean(composites)

        dim_avgs: dict[Dimension, float] = {}
        for dim in Dimension:
            vals = [
                s.dimensions[dim].score
                for s in self._history
                if dim in s.dimensions
            ]
            dim_avgs[dim] = statistics.mean(vals) if vals else 0.0

        weakest = min(dim_avgs, key=lambda d: dim_avgs[d])
        strongest = max(dim_avgs, key=lambda d: dim_avgs[d])

        # Overall gate: fail if any recent eval failed
        recent_gates = [s.gate_decision for s in self._history[-5:]]
        if GateDecision.FAIL in recent_gates:
            gate = GateDecision.FAIL
        elif GateDecision.WARN in recent_gates:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        trends = self.analyze_trends()

        return BatchCLEARReport(
            scores=self._history,
            avg_composite=avg_composite,
            dimension_averages=dim_avgs,
            weakest_dimension=weakest,
            strongest_dimension=strongest,
            gate_decision=gate,
            trends=trends,
            total_evaluations=len(self._history),
        )
