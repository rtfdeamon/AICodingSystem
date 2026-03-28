"""Prompt Regression Detector — CI/CD-integrated prompt quality regression testing.

The prompt is the new code.  A simple wording change can fix one issue
while silently creating another.  This module detects quality regressions
when prompts change by comparing baseline metrics against candidate metrics,
supporting automated go/no-go decisions in CI/CD pipelines.

Based on:
- Traceloop "Automated Prompt Regression Testing with LLM-as-a-Judge" (2026)
- Confident AI "Best LLM Observability Platforms" (2026)
- testRigor "Why DevOps Needs a PromptOps Layer" (2026)
- Maxim AI "Top 5 Prompt Engineering Platforms" (2026)
- Braintrust "AI Observability Tools" (2026)

Key capabilities:
- Baseline vs candidate prompt comparison
- Multi-metric regression detection (quality, latency, cost, safety)
- Statistical significance testing (z-test for proportion differences)
- Per-test-case regression tracking
- Regression severity classification (none / minor / major / critical)
- Quality gate: pass / warn / block
- Batch regression report across prompt families
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class RegressionSeverity(StrEnum):
    NONE = "none"
    MINOR = "minor"  # <5% drop
    MAJOR = "major"  # 5-15% drop
    CRITICAL = "critical"  # >15% drop


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class PromptTestResult:
    """Result for a single test case."""

    case_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt_version: str = ""
    test_input: str = ""
    quality_score: float = 0.0  # 0-1
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    safety_passed: bool = True
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class RegressionConfig:
    """Thresholds for regression detection."""

    minor_threshold: float = 0.03  # 3% drop
    major_threshold: float = 0.10  # 10% drop
    critical_threshold: float = 0.15  # 15% drop
    significance_level: float = 0.05  # p-value threshold
    min_test_cases: int = 5
    latency_regression_pct: float = 0.20  # 20% latency increase
    cost_regression_pct: float = 0.15  # 15% cost increase


@dataclass
class MetricComparison:
    """Comparison of a metric between baseline and candidate."""

    metric_name: str
    baseline_value: float
    candidate_value: float
    delta: float
    delta_pct: float
    is_regression: bool
    severity: RegressionSeverity


@dataclass
class TestCaseRegression:
    """Regression detail for a specific test case."""

    case_id: str
    test_input: str
    baseline_quality: float
    candidate_quality: float
    quality_delta: float
    is_regressed: bool


@dataclass
class RegressionReport:
    """Full regression report for a prompt version change."""

    prompt_family: str
    baseline_version: str
    candidate_version: str
    metric_comparisons: list[MetricComparison]
    test_case_regressions: list[TestCaseRegression]
    overall_severity: RegressionSeverity
    gate: GateDecision
    is_significant: bool
    z_score: float
    p_value: float
    baseline_count: int
    candidate_count: int
    regressed_cases: int
    improved_cases: int
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class BatchRegressionReport:
    """Batch report across multiple prompt families."""

    reports: list[RegressionReport]
    total_regressions: int
    critical_regressions: int
    overall_gate: GateDecision
    total_families: int


# ── Pure helpers ─────────────────────────────────────────────────────────

def _z_test_proportions(
    p1: float, n1: int, p2: float, n2: int,
) -> tuple[float, float]:
    """Two-proportion z-test.  Returns (z_score, p_value)."""
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0

    p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
    if p_pool <= 0 or p_pool >= 1:
        return 0.0, 1.0

    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0

    z = (p1 - p2) / se
    # Approximate p-value (one-tailed: baseline > candidate is regression)
    p_value = 0.5 * math.erfc(z / math.sqrt(2))
    return round(z, 4), round(p_value, 4)


def _compute_mean(values: list[float]) -> float:
    """Compute mean of a list of floats."""
    return sum(values) / len(values) if values else 0.0


def _classify_severity(
    delta_pct: float, config: RegressionConfig,
) -> RegressionSeverity:
    """Classify regression severity by percentage drop."""
    if delta_pct <= 0:
        return RegressionSeverity.NONE
    if delta_pct < config.minor_threshold:
        return RegressionSeverity.NONE
    if delta_pct < config.major_threshold:
        return RegressionSeverity.MINOR
    if delta_pct < config.critical_threshold:
        return RegressionSeverity.MAJOR
    return RegressionSeverity.CRITICAL


def _gate_from_severity(severity: RegressionSeverity) -> GateDecision:
    """Map severity to gate decision."""
    if severity == RegressionSeverity.NONE:
        return GateDecision.PASS
    if severity == RegressionSeverity.MINOR:
        return GateDecision.PASS
    if severity == RegressionSeverity.MAJOR:
        return GateDecision.WARN
    return GateDecision.BLOCK


# ── Main class ───────────────────────────────────────────────────────────

class PromptRegressionDetector:
    """Detects quality regressions across prompt version changes."""

    def __init__(self, config: RegressionConfig | None = None) -> None:
        self._config = config or RegressionConfig()
        self._results: dict[str, list[PromptTestResult]] = {}  # family → results

    def record_result(
        self,
        prompt_family: str,
        prompt_version: str,
        test_input: str = "",
        quality_score: float = 0.0,
        latency_ms: float = 0.0,
        cost_usd: float = 0.0,
        safety_passed: bool = True,
    ) -> PromptTestResult:
        """Record a test case result."""
        result = PromptTestResult(
            prompt_version=prompt_version,
            test_input=test_input,
            quality_score=max(0.0, min(1.0, quality_score)),
            latency_ms=max(0.0, latency_ms),
            cost_usd=max(0.0, cost_usd),
            safety_passed=safety_passed,
        )
        self._results.setdefault(prompt_family, []).append(result)
        return result

    def compare_versions(
        self,
        prompt_family: str,
        baseline_version: str,
        candidate_version: str,
    ) -> RegressionReport:
        """Compare baseline vs candidate prompt version."""
        all_results = self._results.get(prompt_family, [])
        baseline = [r for r in all_results if r.prompt_version == baseline_version]
        candidate = [r for r in all_results if r.prompt_version == candidate_version]

        # Metric comparisons
        comparisons: list[MetricComparison] = []
        cfg = self._config

        # Quality comparison
        base_quality = _compute_mean([r.quality_score for r in baseline])
        cand_quality = _compute_mean([r.quality_score for r in candidate])
        q_delta = base_quality - cand_quality  # positive = regression
        q_pct = q_delta / base_quality if base_quality > 0 else 0.0
        q_severity = _classify_severity(q_pct, cfg)
        comparisons.append(MetricComparison(
            "quality", round(base_quality, 4), round(cand_quality, 4),
            round(q_delta, 4), round(q_pct, 4), q_pct > cfg.minor_threshold, q_severity,
        ))

        # Latency comparison
        base_lat = _compute_mean([r.latency_ms for r in baseline])
        cand_lat = _compute_mean([r.latency_ms for r in candidate])
        lat_delta = cand_lat - base_lat  # positive = regression (higher latency)
        lat_pct = lat_delta / base_lat if base_lat > 0 else 0.0
        lat_regressed = lat_pct > cfg.latency_regression_pct
        comparisons.append(MetricComparison(
            "latency_ms", round(base_lat, 2), round(cand_lat, 2),
            round(lat_delta, 2), round(lat_pct, 4), lat_regressed,
            RegressionSeverity.MAJOR if lat_regressed else RegressionSeverity.NONE,
        ))

        # Cost comparison
        base_cost = _compute_mean([r.cost_usd for r in baseline])
        cand_cost = _compute_mean([r.cost_usd for r in candidate])
        cost_delta = cand_cost - base_cost
        cost_pct = cost_delta / base_cost if base_cost > 0 else 0.0
        cost_regressed = cost_pct > cfg.cost_regression_pct
        comparisons.append(MetricComparison(
            "cost_usd", round(base_cost, 6), round(cand_cost, 6),
            round(cost_delta, 6), round(cost_pct, 4), cost_regressed,
            RegressionSeverity.MINOR if cost_regressed else RegressionSeverity.NONE,
        ))

        # Safety comparison
        base_safety_vals = [1.0 if r.safety_passed else 0.0 for r in baseline]
        base_safety = _compute_mean(base_safety_vals) if baseline else 1.0
        cand_safety_vals = [1.0 if r.safety_passed else 0.0 for r in candidate]
        cand_safety = _compute_mean(cand_safety_vals) if candidate else 1.0
        safety_delta = base_safety - cand_safety
        safety_regressed = safety_delta > 0.01
        comparisons.append(MetricComparison(
            "safety_rate", round(base_safety, 4), round(cand_safety, 4),
            round(safety_delta, 4), round(safety_delta, 4), safety_regressed,
            RegressionSeverity.CRITICAL if safety_regressed else RegressionSeverity.NONE,
        ))

        # Per-test-case regression tracking
        case_regressions: list[TestCaseRegression] = []
        base_by_input = {r.test_input: r for r in baseline if r.test_input}
        regressed_count = 0
        improved_count = 0
        for r in candidate:
            if r.test_input and r.test_input in base_by_input:
                base_r = base_by_input[r.test_input]
                delta = base_r.quality_score - r.quality_score
                is_reg = delta > cfg.minor_threshold
                is_imp = -delta > cfg.minor_threshold
                if is_reg:
                    regressed_count += 1
                if is_imp:
                    improved_count += 1
                case_regressions.append(TestCaseRegression(
                    case_id=r.case_id,
                    test_input=r.test_input,
                    baseline_quality=base_r.quality_score,
                    candidate_quality=r.quality_score,
                    quality_delta=round(delta, 4),
                    is_regressed=is_reg,
                ))

        # Statistical significance
        z_score, p_value = _z_test_proportions(
            base_quality, len(baseline), cand_quality, len(candidate),
        )
        is_significant = p_value < cfg.significance_level

        # Overall severity
        severities = [c.severity for c in comparisons if c.is_regression]
        if RegressionSeverity.CRITICAL in severities:
            overall = RegressionSeverity.CRITICAL
        elif RegressionSeverity.MAJOR in severities:
            overall = RegressionSeverity.MAJOR
        elif RegressionSeverity.MINOR in severities:
            overall = RegressionSeverity.MINOR
        else:
            overall = RegressionSeverity.NONE

        gate = _gate_from_severity(overall)

        return RegressionReport(
            prompt_family=prompt_family,
            baseline_version=baseline_version,
            candidate_version=candidate_version,
            metric_comparisons=comparisons,
            test_case_regressions=case_regressions,
            overall_severity=overall,
            gate=gate,
            is_significant=is_significant,
            z_score=z_score,
            p_value=p_value,
            baseline_count=len(baseline),
            candidate_count=len(candidate),
            regressed_cases=regressed_count,
            improved_cases=improved_count,
        )

    def batch_compare(
        self,
        baseline_version: str,
        candidate_version: str,
    ) -> BatchRegressionReport:
        """Compare versions across all prompt families."""
        reports = []
        for family in self._results:
            report = self.compare_versions(family, baseline_version, candidate_version)
            reports.append(report)

        total_reg = sum(1 for r in reports if r.overall_severity != RegressionSeverity.NONE)
        critical_reg = sum(1 for r in reports if r.overall_severity == RegressionSeverity.CRITICAL)

        if critical_reg > 0:
            overall_gate = GateDecision.BLOCK
        elif total_reg > 0:
            overall_gate = GateDecision.WARN
        else:
            overall_gate = GateDecision.PASS

        return BatchRegressionReport(
            reports=reports,
            total_regressions=total_reg,
            critical_regressions=critical_reg,
            overall_gate=overall_gate,
            total_families=len(reports),
        )
