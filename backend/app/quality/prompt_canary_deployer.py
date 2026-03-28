"""Prompt Canary Deployer — canary deployment strategy for prompt changes.

Implements gradual rollout of new prompt versions with traffic splitting,
automatic rollback on quality degradation, and A/B testing capabilities.

A single prompt change can cause hallucinations, tool misuse, or quality
regressions.  Canary deployment sends a small slice of traffic to the
new version first.  If quality, latency, or cost metrics degrade beyond
thresholds, the rollout halts automatically.

Based on:
- Braintrust "What is Prompt Management?" (2026)
- Maxim.ai "Managing Prompt Versions: Effective Strategies" (2026)
- LangWatch "Prompt Management: Version, Control & Deploy" (2026)
- NJ Raman "Versioning, Rollback & Lifecycle Management of AI Agents" (2026)
- OpenAI GPT-4o sycophancy rollback incident lessons (April 2025)

Key capabilities:
- Traffic splitting: configurable canary percentage (1–50 %)
- Multi-metric health checks: quality, latency, cost, error rate
- Automatic rollback when any metric breaches threshold
- Gradual ramp-up schedule (e.g., 5 % → 10 % → 25 % → 50 % → 100 %)
- A/B comparison reports with statistical significance
- Rollback history for audit trail
- Quality gate: promote / hold / rollback
"""

from __future__ import annotations

import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class CanaryStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    RAMPING = "ramping"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"


class GateDecision(StrEnum):
    PROMOTE = "promote"
    HOLD = "hold"
    ROLLBACK = "rollback"


class MetricKind(StrEnum):
    QUALITY = "quality"
    LATENCY = "latency"
    COST = "cost"
    ERROR_RATE = "error_rate"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class MetricSample:
    """Single metric observation for a prompt version."""

    metric: MetricKind
    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CanaryConfig:
    """Configuration for a canary deployment."""

    initial_percentage: float = 5.0  # %
    ramp_steps: list[float] = field(
        default_factory=lambda: [5.0, 10.0, 25.0, 50.0, 100.0],
    )
    min_samples_per_step: int = 20
    quality_threshold: float = 0.7  # min acceptable quality (0-1)
    latency_threshold_ms: float = 5000.0
    cost_threshold: float = 0.50  # max cost per request ($)
    error_rate_threshold: float = 0.05  # 5 %


@dataclass
class PromptVersion:
    """Represents a specific prompt version."""

    version_id: str
    prompt_text: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict = field(default_factory=dict)


@dataclass
class CanaryDeployment:
    """State of a canary deployment."""

    deployment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    baseline_version: str = ""
    canary_version: str = ""
    status: CanaryStatus = CanaryStatus.PENDING
    current_percentage: float = 0.0
    current_step_index: int = 0
    config: CanaryConfig = field(default_factory=CanaryConfig)
    baseline_samples: list[MetricSample] = field(default_factory=list)
    canary_samples: list[MetricSample] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    rollback_reason: str = ""


@dataclass
class HealthCheck:
    """Result of a canary health check."""

    metric: MetricKind
    baseline_avg: float
    canary_avg: float
    threshold: float
    passed: bool
    degradation_pct: float  # how much worse canary is (negative = better)


@dataclass
class CanaryReport:
    """Full canary deployment report."""

    deployment_id: str
    status: CanaryStatus
    gate: GateDecision
    current_percentage: float
    health_checks: list[HealthCheck]
    baseline_sample_count: int
    canary_sample_count: int
    duration_seconds: float


@dataclass
class RollbackRecord:
    """Audit record for a rollback."""

    deployment_id: str
    rolled_back_version: str
    reverted_to_version: str
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class BatchCanaryReport:
    """Batch report across multiple canary deployments."""

    reports: list[CanaryReport]
    active_count: int
    promoted_count: int
    rolled_back_count: int


# ── Pure helpers ─────────────────────────────────────────────────────────

def _avg(values: list[float]) -> float:
    """Compute mean of a list, returning 0.0 for empty."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _route_to_canary(percentage: float) -> bool:
    """Decide whether a request should go to the canary version."""
    if percentage <= 0:
        return False
    if percentage >= 100:
        return True
    return random.random() * 100 < percentage  # noqa: S311


def _check_health(
    metric: MetricKind,
    baseline_values: list[float],
    canary_values: list[float],
    threshold: float,
    *,
    higher_is_better: bool = True,
) -> HealthCheck:
    """Compare canary to baseline for one metric."""
    b_avg = _avg(baseline_values)
    c_avg = _avg(canary_values)

    if b_avg == 0:
        degradation = 0.0
    elif higher_is_better:
        degradation = ((b_avg - c_avg) / b_avg) * 100
    else:
        degradation = ((c_avg - b_avg) / abs(b_avg)) * 100 if b_avg != 0 else 0.0

    passed = c_avg >= threshold if higher_is_better else c_avg <= threshold

    return HealthCheck(
        metric=metric,
        baseline_avg=b_avg,
        canary_avg=c_avg,
        threshold=threshold,
        passed=passed,
        degradation_pct=round(degradation, 2),
    )


def _compute_significance(baseline: list[float], canary: list[float]) -> float:
    """Simple z-test significance (0-1).  Returns p-value approximation."""
    if len(baseline) < 2 or len(canary) < 2:
        return 1.0  # not enough data
    b_mean = _avg(baseline)
    c_mean = _avg(canary)
    b_var = sum((x - b_mean) ** 2 for x in baseline) / (len(baseline) - 1)
    c_var = sum((x - c_mean) ** 2 for x in canary) / (len(canary) - 1)
    se = math.sqrt(b_var / len(baseline) + c_var / len(canary))
    if se == 0:
        return 1.0
    z = abs(b_mean - c_mean) / se
    # Approximate two-tailed p-value using logistic approximation
    p = 2 * (1 / (1 + math.exp(0.7 * z)))
    return round(min(p, 1.0), 4)


# ── Main class ───────────────────────────────────────────────────────────

class PromptCanaryDeployer:
    """Manages canary deployments for prompt version changes."""

    def __init__(self) -> None:
        self._deployments: dict[str, CanaryDeployment] = {}
        self._rollback_history: list[RollbackRecord] = []
        self._versions: dict[str, PromptVersion] = {}

    # ── Version management ───────────────────────────────────────────

    def register_version(self, version_id: str, prompt_text: str, **meta: object) -> PromptVersion:
        """Register a new prompt version."""
        v = PromptVersion(version_id=version_id, prompt_text=prompt_text, metadata=dict(meta))
        self._versions[version_id] = v
        logger.info("Registered prompt version %s", version_id)
        return v

    # ── Deployment lifecycle ─────────────────────────────────────────

    def create_deployment(
        self,
        baseline_version: str,
        canary_version: str,
        config: CanaryConfig | None = None,
    ) -> CanaryDeployment:
        """Create a new canary deployment."""
        cfg = config or CanaryConfig()
        dep = CanaryDeployment(
            baseline_version=baseline_version,
            canary_version=canary_version,
            config=cfg,
        )
        self._deployments[dep.deployment_id] = dep
        logger.info(
            "Created canary deployment %s: %s → %s",
            dep.deployment_id, baseline_version, canary_version,
        )
        return dep

    def start_deployment(self, deployment_id: str) -> CanaryDeployment:
        """Start a canary deployment — begin routing traffic."""
        dep = self._deployments[deployment_id]
        if dep.status != CanaryStatus.PENDING:
            msg = f"Cannot start deployment in status {dep.status}"
            raise ValueError(msg)
        dep.status = CanaryStatus.ACTIVE
        dep.current_percentage = dep.config.initial_percentage
        dep.current_step_index = 0
        dep.started_at = datetime.now(UTC)
        logger.info("Started canary deployment %s at %.1f%%", deployment_id, dep.current_percentage)
        return dep

    def route_request(self, deployment_id: str) -> str:
        """Route a request to baseline or canary version."""
        dep = self._deployments[deployment_id]
        if dep.status in {CanaryStatus.PROMOTED}:
            return dep.canary_version
        if dep.status in {CanaryStatus.ROLLED_BACK, CanaryStatus.PENDING}:
            return dep.baseline_version
        if _route_to_canary(dep.current_percentage):
            return dep.canary_version
        return dep.baseline_version

    def record_sample(
        self,
        deployment_id: str,
        version: str,
        metric: MetricKind,
        value: float,
    ) -> None:
        """Record a metric observation for a version."""
        dep = self._deployments[deployment_id]
        sample = MetricSample(metric=metric, value=value)
        if version == dep.canary_version:
            dep.canary_samples.append(sample)
        else:
            dep.baseline_samples.append(sample)

    def check_health(self, deployment_id: str) -> list[HealthCheck]:
        """Run health checks comparing canary to baseline."""
        dep = self._deployments[deployment_id]
        cfg = dep.config

        checks: list[HealthCheck] = []

        metric_config: list[tuple[MetricKind, float, bool]] = [
            (MetricKind.QUALITY, cfg.quality_threshold, True),
            (MetricKind.LATENCY, cfg.latency_threshold_ms, False),
            (MetricKind.COST, cfg.cost_threshold, False),
            (MetricKind.ERROR_RATE, cfg.error_rate_threshold, False),
        ]

        for mkind, threshold, higher_better in metric_config:
            b_vals = [s.value for s in dep.baseline_samples if s.metric == mkind]
            c_vals = [s.value for s in dep.canary_samples if s.metric == mkind]
            if c_vals:  # only check if we have canary data
                checks.append(_check_health(
                    mkind, b_vals, c_vals, threshold,
                    higher_is_better=higher_better,
                ))

        return checks

    def evaluate_gate(self, deployment_id: str) -> GateDecision:
        """Evaluate whether to promote, hold, or rollback."""
        dep = self._deployments[deployment_id]
        cfg = dep.config
        canary_count = len([s for s in dep.canary_samples])

        if canary_count < cfg.min_samples_per_step:
            return GateDecision.HOLD

        checks = self.check_health(deployment_id)
        if not checks:
            return GateDecision.HOLD

        failed = [c for c in checks if not c.passed]
        if failed:
            return GateDecision.ROLLBACK

        return GateDecision.PROMOTE

    def advance_or_rollback(self, deployment_id: str) -> CanaryDeployment:
        """Evaluate health and advance, hold, or rollback."""
        dep = self._deployments[deployment_id]
        gate = self.evaluate_gate(deployment_id)

        if gate == GateDecision.ROLLBACK:
            return self.rollback(deployment_id, reason="Health check failed")

        if gate == GateDecision.PROMOTE:
            steps = dep.config.ramp_steps
            next_idx = dep.current_step_index + 1
            if next_idx >= len(steps):
                return self.promote(deployment_id)
            dep.current_step_index = next_idx
            dep.current_percentage = steps[next_idx]
            dep.status = CanaryStatus.RAMPING
            # Clear samples for next step
            dep.canary_samples.clear()
            dep.baseline_samples.clear()
            logger.info(
                "Advanced deployment %s to %.1f%%", deployment_id, dep.current_percentage,
            )

        return dep

    def promote(self, deployment_id: str) -> CanaryDeployment:
        """Promote canary to full production."""
        dep = self._deployments[deployment_id]
        dep.status = CanaryStatus.PROMOTED
        dep.current_percentage = 100.0
        dep.completed_at = datetime.now(UTC)
        logger.info(
            "Promoted deployment %s — canary %s is now production",
            deployment_id, dep.canary_version,
        )
        return dep

    def rollback(self, deployment_id: str, reason: str = "") -> CanaryDeployment:
        """Rollback canary to baseline."""
        dep = self._deployments[deployment_id]
        dep.status = CanaryStatus.ROLLED_BACK
        dep.current_percentage = 0.0
        dep.rollback_reason = reason
        dep.completed_at = datetime.now(UTC)

        record = RollbackRecord(
            deployment_id=deployment_id,
            rolled_back_version=dep.canary_version,
            reverted_to_version=dep.baseline_version,
            reason=reason,
        )
        self._rollback_history.append(record)
        logger.info("Rolled back deployment %s: %s", deployment_id, reason)
        return dep

    # ── Reporting ────────────────────────────────────────────────────

    def get_report(self, deployment_id: str) -> CanaryReport:
        """Generate canary report."""
        dep = self._deployments[deployment_id]
        checks = self.check_health(deployment_id)
        gate = self.evaluate_gate(deployment_id)

        duration = 0.0
        if dep.started_at:
            end = dep.completed_at or datetime.now(UTC)
            duration = (end - dep.started_at).total_seconds()

        return CanaryReport(
            deployment_id=deployment_id,
            status=dep.status,
            gate=gate,
            current_percentage=dep.current_percentage,
            health_checks=checks,
            baseline_sample_count=len(dep.baseline_samples),
            canary_sample_count=len(dep.canary_samples),
            duration_seconds=duration,
        )

    def get_significance(self, deployment_id: str, metric: MetricKind) -> float:
        """Get statistical significance of difference for a metric."""
        dep = self._deployments[deployment_id]
        b_vals = [s.value for s in dep.baseline_samples if s.metric == metric]
        c_vals = [s.value for s in dep.canary_samples if s.metric == metric]
        return _compute_significance(b_vals, c_vals)

    def get_rollback_history(self) -> list[RollbackRecord]:
        """Get full rollback audit trail."""
        return list(self._rollback_history)

    def batch_report(self) -> BatchCanaryReport:
        """Report across all deployments."""
        reports = [self.get_report(did) for did in self._deployments]
        active = {CanaryStatus.ACTIVE, CanaryStatus.RAMPING}
        return BatchCanaryReport(
            reports=reports,
            active_count=sum(1 for r in reports if r.status in active),
            promoted_count=sum(
                1 for r in reports if r.status == CanaryStatus.PROMOTED
            ),
            rolled_back_count=sum(
                1 for r in reports if r.status == CanaryStatus.ROLLED_BACK
            ),
        )
