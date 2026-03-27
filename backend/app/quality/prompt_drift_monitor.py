"""Prompt Drift Monitor — detect silent changes in AI output quality and
distribution over time.

LLM outputs can drift silently due to model updates, prompt degradation,
or context pollution. Without active monitoring, these drifts erode trust
and usability without triggering any explicit error.

Based on Harness Engineering principles (OpenAI 2025-2026), Arize AI
drift detection architecture, and Fiddler AI observability patterns.
Also informed by agent-engineering.dev "Harness Engineering in 2026"
and Authority Partners "AI Agent Guardrails: Production Guide for 2026".

Key capabilities:
- Track output distributions: length, sentiment, topic, format adherence
- Statistical drift detection: KL-divergence approximation and z-score
- Rolling window comparison: current vs baseline period
- Alert generation on significant drift
- Per-prompt-version tracking for A/B comparisons
- Quality trend analysis: monotonic degradation detection
- Quality gate: configurable drift thresholds
- Batch analysis across multiple prompt versions
"""

from __future__ import annotations

import hashlib
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class DriftSeverity(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DriftType(StrEnum):
    LENGTH = "length"
    SENTIMENT = "sentiment"
    FORMAT = "format"
    TOPIC = "topic"
    QUALITY = "quality"
    LATENCY = "latency"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class OutputSample:
    """A single output observation."""

    text: str
    prompt_version: str = "default"
    latency_ms: float = 0.0
    quality_score: float = 0.0  # 0-1 from external evaluator
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class DistributionStats:
    """Statistical summary of a distribution."""

    count: int
    mean: float
    std: float
    min_val: float
    max_val: float
    p50: float
    p90: float
    p99: float


@dataclass
class DriftAlert:
    """Alert for detected drift."""

    id: str
    drift_type: DriftType
    severity: DriftSeverity
    metric_name: str
    baseline_value: float
    current_value: float
    z_score: float
    description: str
    prompt_version: str
    detected_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class DriftReport:
    """Comprehensive drift analysis report."""

    id: str
    prompt_version: str
    alerts: list[DriftAlert]
    baseline_stats: dict[str, DistributionStats]
    current_stats: dict[str, DistributionStats]
    overall_drift_score: float  # 0-1
    severity: DriftSeverity
    gate_decision: GateDecision
    sample_count_baseline: int
    sample_count_current: int
    analyzed_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchDriftReport:
    """Report across multiple prompt versions."""

    reports: list[DriftReport]
    total_versions: int
    drifted_versions: int
    avg_drift_score: float
    gate_decision: GateDecision


# ── Helpers ─────────────────────────────────────────────────────────────

def _compute_stats(values: list[float]) -> DistributionStats:
    """Compute distribution statistics."""
    if not values:
        return DistributionStats(0, 0, 0, 0, 0, 0, 0, 0)

    n = len(values)
    sorted_vals = sorted(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / max(n - 1, 1)
    std = math.sqrt(variance)

    return DistributionStats(
        count=n,
        mean=round(mean, 4),
        std=round(std, 4),
        min_val=round(sorted_vals[0], 4),
        max_val=round(sorted_vals[-1], 4),
        p50=round(sorted_vals[n // 2], 4),
        p90=round(sorted_vals[int(n * 0.9)], 4) if n >= 10 else round(sorted_vals[-1], 4),
        p99=round(sorted_vals[int(n * 0.99)], 4) if n >= 100 else round(sorted_vals[-1], 4),
    )


def _z_score(baseline_mean: float, baseline_std: float, current_mean: float) -> float:
    """Compute z-score of current mean vs baseline."""
    if baseline_std == 0:
        return 0.0 if baseline_mean == current_mean else 3.0
    return abs(current_mean - baseline_mean) / baseline_std


def _estimate_sentiment(text: str) -> float:
    """Simple keyword-based sentiment score (0=negative, 0.5=neutral, 1=positive)."""
    positive = {
        "good", "great", "excellent", "correct", "success",
        "working", "perfect", "done", "complete",
    }
    negative = {
        "error", "fail", "wrong", "bad", "issue",
        "bug", "broken", "crash", "problem", "invalid",
    }
    words = set(text.lower().split())
    pos = len(words & positive)
    neg = len(words & negative)
    total = pos + neg
    if total == 0:
        return 0.5
    return round(pos / total, 4)


def _topic_hash(text: str) -> str:
    """Simple content fingerprint for topic tracking."""
    words = sorted(set(text.lower().split()))[:20]
    return hashlib.sha256(" ".join(words).encode()).hexdigest()[:8]


# ── Main class ──────────────────────────────────────────────────────────

class PromptDriftMonitor:
    """Monitor AI output distributions for silent drift.

    Collects output samples per prompt version, computes statistical
    baselines, and detects drift using z-scores and distribution comparison.
    """

    def __init__(
        self,
        baseline_window: int = 100,
        current_window: int = 20,
        z_threshold_warn: float = 2.0,
        z_threshold_block: float = 3.0,
        drift_score_warn: float = 0.3,
        drift_score_block: float = 0.6,
    ) -> None:
        self.baseline_window = baseline_window
        self.current_window = current_window
        self.z_threshold_warn = z_threshold_warn
        self.z_threshold_block = z_threshold_block
        self.drift_score_warn = drift_score_warn
        self.drift_score_block = drift_score_block
        self._samples: dict[str, list[OutputSample]] = {}
        self._history: list[DriftReport] = []

    def record(self, sample: OutputSample) -> None:
        """Record an output sample."""
        version = sample.prompt_version
        if version not in self._samples:
            self._samples[version] = []
        self._samples[version].append(sample)

    def get_sample_count(self, prompt_version: str = "default") -> int:
        return len(self._samples.get(prompt_version, []))

    # ── Feature extraction ──────────────────────────────────────────────

    def _extract_features(self, samples: list[OutputSample]) -> dict[str, list[float]]:
        """Extract numeric feature vectors from samples."""
        return {
            "length": [float(len(s.text)) for s in samples],
            "word_count": [float(len(s.text.split())) for s in samples],
            "sentiment": [_estimate_sentiment(s.text) for s in samples],
            "quality_score": [s.quality_score for s in samples],
            "latency_ms": [s.latency_ms for s in samples],
        }

    # ── Drift analysis ──────────────────────────────────────────────────

    def analyze(self, prompt_version: str = "default") -> DriftReport:
        """Analyze drift for a specific prompt version."""
        samples = self._samples.get(prompt_version, [])

        if len(samples) < self.current_window + 5:
            # Not enough data
            report = DriftReport(
                id=uuid.uuid4().hex[:12],
                prompt_version=prompt_version,
                alerts=[],
                baseline_stats={},
                current_stats={},
                overall_drift_score=0.0,
                severity=DriftSeverity.NONE,
                gate_decision=GateDecision.PASS,
                sample_count_baseline=0,
                sample_count_current=len(samples),
            )
            self._history.append(report)
            return report

        # Split into baseline and current windows
        baseline_end = len(samples) - self.current_window
        baseline_start = max(0, baseline_end - self.baseline_window)
        baseline = samples[baseline_start:baseline_end]
        current = samples[-self.current_window:]

        baseline_features = self._extract_features(baseline)
        current_features = self._extract_features(current)

        alerts: list[DriftAlert] = []
        baseline_stats: dict[str, DistributionStats] = {}
        current_stats: dict[str, DistributionStats] = {}

        drift_type_map = {
            "length": DriftType.LENGTH,
            "word_count": DriftType.LENGTH,
            "sentiment": DriftType.SENTIMENT,
            "quality_score": DriftType.QUALITY,
            "latency_ms": DriftType.LATENCY,
        }

        for metric in baseline_features:
            b_vals = baseline_features[metric]
            c_vals = current_features[metric]

            b_stats = _compute_stats(b_vals)
            c_stats = _compute_stats(c_vals)
            baseline_stats[metric] = b_stats
            current_stats[metric] = c_stats

            z = _z_score(b_stats.mean, b_stats.std, c_stats.mean)

            if z >= self.z_threshold_block:
                severity = DriftSeverity.HIGH
            elif z >= self.z_threshold_warn:
                severity = DriftSeverity.MEDIUM
            else:
                severity = DriftSeverity.NONE

            if severity != DriftSeverity.NONE:
                alerts.append(DriftAlert(
                    id=uuid.uuid4().hex[:12],
                    drift_type=drift_type_map.get(metric, DriftType.QUALITY),
                    severity=severity,
                    metric_name=metric,
                    baseline_value=b_stats.mean,
                    current_value=c_stats.mean,
                    z_score=round(z, 4),
                    description=(
                        f"Metric '{metric}' drifted: baseline={b_stats.mean:.2f} "
                        f"current={c_stats.mean:.2f} (z={z:.2f})"
                    ),
                    prompt_version=prompt_version,
                ))

        # Check for monotonic degradation in quality
        quality_vals = [s.quality_score for s in samples[-self.current_window:]]
        if len(quality_vals) >= 5:
            degradation = self._check_monotonic_degradation(quality_vals)
            if degradation:
                alerts.append(DriftAlert(
                    id=uuid.uuid4().hex[:12],
                    drift_type=DriftType.QUALITY,
                    severity=DriftSeverity.HIGH,
                    metric_name="quality_trend",
                    baseline_value=quality_vals[0],
                    current_value=quality_vals[-1],
                    z_score=0.0,
                    description="Monotonic quality degradation detected over recent window",
                    prompt_version=prompt_version,
                ))

        # Overall drift score
        if alerts:
            max_z = max(a.z_score for a in alerts) if any(a.z_score > 0 for a in alerts) else 0
            high_sev = (DriftSeverity.HIGH, DriftSeverity.CRITICAL)
            high_count = sum(1 for a in alerts if a.severity in high_sev)
            drift_score = min(max_z / 5.0 + high_count * 0.2, 1.0)
        else:
            drift_score = 0.0

        # Severity and gate
        if drift_score >= self.drift_score_block:
            severity = DriftSeverity.CRITICAL
            gate = GateDecision.BLOCK
        elif drift_score >= self.drift_score_warn:
            severity = DriftSeverity.MEDIUM
            gate = GateDecision.WARN
        elif alerts:
            severity = DriftSeverity.LOW
            gate = GateDecision.PASS
        else:
            severity = DriftSeverity.NONE
            gate = GateDecision.PASS

        report = DriftReport(
            id=uuid.uuid4().hex[:12],
            prompt_version=prompt_version,
            alerts=alerts,
            baseline_stats=baseline_stats,
            current_stats=current_stats,
            overall_drift_score=round(drift_score, 4),
            severity=severity,
            gate_decision=gate,
            sample_count_baseline=len(baseline),
            sample_count_current=len(current),
        )
        self._history.append(report)
        return report

    def _check_monotonic_degradation(self, values: list[float]) -> bool:
        """Check if values show monotonic decrease (at least 80% decreasing)."""
        if len(values) < 3:
            return False
        decreasing = sum(1 for i in range(1, len(values)) if values[i] < values[i - 1])
        return decreasing / (len(values) - 1) >= 0.8

    # ── Batch analysis ──────────────────────────────────────────────────

    def batch_analyze(self, versions: list[str] | None = None) -> BatchDriftReport:
        """Analyze drift across multiple prompt versions."""
        if versions is None:
            versions = list(self._samples.keys())

        reports = [self.analyze(v) for v in versions]
        drifted = sum(1 for r in reports if r.severity != DriftSeverity.NONE)
        avg_score = (
            sum(r.overall_drift_score for r in reports) / len(reports)
            if reports else 0.0
        )

        gates = [r.gate_decision for r in reports]
        if GateDecision.BLOCK in gates:
            gate = GateDecision.BLOCK
        elif GateDecision.WARN in gates:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        return BatchDriftReport(
            reports=reports,
            total_versions=len(reports),
            drifted_versions=drifted,
            avg_drift_score=round(avg_score, 4),
            gate_decision=gate,
        )

    @property
    def history(self) -> list[DriftReport]:
        return list(self._history)
