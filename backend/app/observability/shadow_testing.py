"""Shadow Mode A/B Testing — compare model and prompt changes safely.

Runs challenger models/prompts in shadow mode alongside the champion,
capturing both responses without affecting production output:
- Create experiments comparing champion vs challenger configurations
- Record shadow results with quality scores, latency, and cost
- Compute statistical significance of differences
- Generate experiment reports with winner determination
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class ExperimentStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VariantType(StrEnum):
    CHAMPION = "champion"
    CHALLENGER = "challenger"


@dataclass
class Experiment:
    """An A/B test experiment comparing champion vs challenger."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:32])
    name: str = ""
    champion_model: str = ""
    challenger_model: str = ""
    champion_prompt_version: str = ""
    challenger_prompt_version: str = ""
    status: ExperimentStatus = ExperimentStatus.DRAFT
    min_samples: int = 500
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


@dataclass
class ShadowResult:
    """A single shadow comparison between champion and challenger."""

    experiment_id: str = ""
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:32])
    prompt: str = ""
    champion_response: str = ""
    challenger_response: str = ""
    champion_score: float = 0.0
    challenger_score: float = 0.0
    champion_latency_ms: float = 0.0
    challenger_latency_ms: float = 0.0
    champion_cost: float = 0.0
    challenger_cost: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ExperimentReport:
    """Aggregated report for an experiment."""

    experiment_id: str = ""
    name: str = ""
    total_samples: int = 0
    champion_avg_score: float = 0.0
    challenger_avg_score: float = 0.0
    champion_avg_latency: float = 0.0
    challenger_avg_latency: float = 0.0
    champion_total_cost: float = 0.0
    challenger_total_cost: float = 0.0
    is_significant: bool = False
    winner: VariantType | None = None
    p_value: float = 1.0


# ── In-memory storage ─────────────────────────────────────────────────

_experiments: dict[str, Experiment] = {}
_shadow_results: dict[str, list[ShadowResult]] = {}


# ── Public API ─────────────────────────────────────────────────────────


def create_experiment(
    name: str,
    champion_model: str,
    challenger_model: str,
    champion_prompt: str,
    challenger_prompt: str,
    min_samples: int = 500,
) -> Experiment:
    """Create a new shadow testing experiment."""
    experiment = Experiment(
        name=name,
        champion_model=champion_model,
        challenger_model=challenger_model,
        champion_prompt_version=champion_prompt,
        challenger_prompt_version=challenger_prompt,
        status=ExperimentStatus.ACTIVE,
        min_samples=min_samples,
    )
    _experiments[experiment.id] = experiment
    _shadow_results[experiment.id] = []
    logger.info(
        "Created experiment: id=%s name=%s champion=%s challenger=%s",
        experiment.id,
        name,
        champion_model,
        challenger_model,
    )
    return experiment


def record_shadow_result(
    experiment_id: str,
    prompt: str,
    champion_resp: str,
    challenger_resp: str,
    champion_score: float,
    challenger_score: float,
    champion_latency: float,
    challenger_latency: float,
    champion_cost: float,
    challenger_cost: float,
) -> ShadowResult:
    """Record a shadow comparison result for an experiment."""
    if experiment_id not in _experiments:
        msg = f"Experiment not found: {experiment_id}"
        raise ValueError(msg)

    experiment = _experiments[experiment_id]
    if experiment.status != ExperimentStatus.ACTIVE:
        msg = f"Experiment is not active: {experiment_id}"
        raise ValueError(msg)

    result = ShadowResult(
        experiment_id=experiment_id,
        prompt=prompt,
        champion_response=champion_resp,
        challenger_response=challenger_resp,
        champion_score=champion_score,
        challenger_score=challenger_score,
        champion_latency_ms=champion_latency,
        challenger_latency_ms=challenger_latency,
        champion_cost=champion_cost,
        challenger_cost=challenger_cost,
    )
    _shadow_results[experiment_id].append(result)

    logger.debug(
        "Recorded shadow result: experiment=%s champion_score=%.3f challenger_score=%.3f",
        experiment_id,
        champion_score,
        challenger_score,
    )
    return result


def get_experiment(experiment_id: str) -> Experiment | None:
    """Get an experiment by ID."""
    return _experiments.get(experiment_id)


def get_experiment_results(experiment_id: str) -> list[ShadowResult]:
    """Get all shadow results for an experiment."""
    return _shadow_results.get(experiment_id, [])


def simple_significance_test(
    scores_a: list[float],
    scores_b: list[float],
) -> tuple[bool, float]:
    """Two-sample Welch's t-test approximation (no scipy needed).

    Returns (is_significant, p_value_approx).
    Uses a p < 0.05 threshold for significance.
    """
    n_a = len(scores_a)
    n_b = len(scores_b)

    if n_a < 2 or n_b < 2:
        return False, 1.0

    mean_a = sum(scores_a) / n_a
    mean_b = sum(scores_b) / n_b

    var_a = sum((x - mean_a) ** 2 for x in scores_a) / (n_a - 1)
    var_b = sum((x - mean_b) ** 2 for x in scores_b) / (n_b - 1)

    se_a = var_a / n_a
    se_b = var_b / n_b
    se_sum = se_a + se_b

    if se_sum == 0:
        return False, 1.0

    t_stat = (mean_a - mean_b) / math.sqrt(se_sum)

    # Welch–Satterthwaite degrees of freedom
    if se_a == 0 and se_b == 0:
        return False, 1.0

    numerator = se_sum**2
    denominator = 0.0
    if se_a > 0:
        denominator += se_a**2 / (n_a - 1)
    if se_b > 0:
        denominator += se_b**2 / (n_b - 1)

    if denominator == 0:
        return False, 1.0

    df = numerator / denominator

    # Approximate two-tailed p-value using the t-distribution CDF
    # via the regularised incomplete beta function approximation
    p_value = _approx_two_tailed_p(abs(t_stat), df)

    return p_value < 0.05, p_value


def _approx_two_tailed_p(t: float, df: float) -> float:
    """Approximate two-tailed p-value for Student's t-distribution.

    Uses the approximation:  p ≈ 2 * (1 - Φ(t * (1 - 1/(4*df))))
    where Φ is the standard normal CDF, which is reasonable for df >= 3.
    For very small df we fall back to a conservative estimate.
    """
    if df < 1:
        return 1.0

    # Adjust t-statistic for degrees of freedom
    adjusted_t = t * (1.0 - 1.0 / (4.0 * df)) if df >= 4 else t * 0.8

    # Standard normal CDF approximation (Abramowitz & Stegun 26.2.17)
    p = 2.0 * (1.0 - _normal_cdf(adjusted_t))
    return min(max(p, 0.0), 1.0)


def _normal_cdf(x: float) -> float:
    """Approximate the standard normal CDF using the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def compute_experiment_report(experiment_id: str) -> ExperimentReport:
    """Compute an aggregated report for an experiment."""
    experiment = _experiments.get(experiment_id)
    if experiment is None:
        msg = f"Experiment not found: {experiment_id}"
        raise ValueError(msg)

    results = _shadow_results.get(experiment_id, [])
    total = len(results)

    if total == 0:
        return ExperimentReport(
            experiment_id=experiment_id,
            name=experiment.name,
        )

    champion_scores = [r.champion_score for r in results]
    challenger_scores = [r.challenger_score for r in results]

    champion_avg_score = sum(champion_scores) / total
    challenger_avg_score = sum(challenger_scores) / total

    champion_avg_latency = sum(r.champion_latency_ms for r in results) / total
    challenger_avg_latency = sum(r.challenger_latency_ms for r in results) / total

    champion_total_cost = sum(r.champion_cost for r in results)
    challenger_total_cost = sum(r.challenger_cost for r in results)

    is_significant, p_value = simple_significance_test(
        champion_scores, challenger_scores
    )

    winner: VariantType | None = None
    if is_significant:
        winner = (
            VariantType.CHAMPION
            if champion_avg_score >= challenger_avg_score
            else VariantType.CHALLENGER
        )

    return ExperimentReport(
        experiment_id=experiment_id,
        name=experiment.name,
        total_samples=total,
        champion_avg_score=champion_avg_score,
        challenger_avg_score=challenger_avg_score,
        champion_avg_latency=champion_avg_latency,
        challenger_avg_latency=challenger_avg_latency,
        champion_total_cost=champion_total_cost,
        challenger_total_cost=challenger_total_cost,
        is_significant=is_significant,
        winner=winner,
        p_value=p_value,
    )


def complete_experiment(experiment_id: str) -> Experiment:
    """Mark an experiment as completed."""
    experiment = _experiments.get(experiment_id)
    if experiment is None:
        msg = f"Experiment not found: {experiment_id}"
        raise ValueError(msg)
    experiment.status = ExperimentStatus.COMPLETED
    experiment.completed_at = datetime.now(UTC)
    logger.info("Experiment completed: id=%s name=%s", experiment_id, experiment.name)
    return experiment


def cancel_experiment(experiment_id: str) -> Experiment:
    """Cancel an experiment."""
    experiment = _experiments.get(experiment_id)
    if experiment is None:
        msg = f"Experiment not found: {experiment_id}"
        raise ValueError(msg)
    experiment.status = ExperimentStatus.CANCELLED
    experiment.completed_at = datetime.now(UTC)
    logger.info("Experiment cancelled: id=%s name=%s", experiment_id, experiment.name)
    return experiment


def list_active_experiments() -> list[Experiment]:
    """List all active experiments."""
    return [
        exp
        for exp in _experiments.values()
        if exp.status == ExperimentStatus.ACTIVE
    ]


def clear_experiment_data() -> None:
    """Clear all experiment data (for testing)."""
    _experiments.clear()
    _shadow_results.clear()


def experiment_report_to_json(report: ExperimentReport) -> dict[str, Any]:
    """Serialize an ExperimentReport to a JSON-compatible dict."""
    return {
        "experiment_id": report.experiment_id,
        "name": report.name,
        "total_samples": report.total_samples,
        "champion_avg_score": report.champion_avg_score,
        "challenger_avg_score": report.challenger_avg_score,
        "champion_avg_latency": report.champion_avg_latency,
        "challenger_avg_latency": report.challenger_avg_latency,
        "champion_total_cost": report.champion_total_cost,
        "challenger_total_cost": report.challenger_total_cost,
        "is_significant": report.is_significant,
        "winner": report.winner.value if report.winner else None,
        "p_value": report.p_value,
    }
