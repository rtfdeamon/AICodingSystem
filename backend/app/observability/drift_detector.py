"""Output Drift Detection and Behavioral Baseline Monitor.

Detects when AI model outputs drift from established behavioral baselines:
- Semantic drift: changes in response structure or content patterns
- Behavioral drift: shifts in code ratio, response length, construct usage
- Performance drift: declining acceptance rates over time

Compares recent output samples against stored baselines to generate
drift alerts with severity levels.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

logger = logging.getLogger(__name__)


class DriftType(StrEnum):
    SEMANTIC = "semantic"
    BEHAVIORAL = "behavioral"
    PERFORMANCE = "performance"


class DriftSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class BehavioralBaseline:
    """Stored behavioral baseline for a model + prompt version."""

    model_id: str
    prompt_version: str
    avg_response_length: float
    avg_code_ratio: float
    avg_construct_counts: dict[str, float] = field(default_factory=dict)
    acceptance_rate: float = 1.0
    sample_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class DriftAlert:
    """A single drift alert raised when a metric deviates from baseline."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    drift_type: DriftType = DriftType.BEHAVIORAL
    severity: DriftSeverity = DriftSeverity.LOW
    model_id: str = ""
    metric_name: str = ""
    baseline_value: float = 0.0
    current_value: float = 0.0
    deviation_pct: float = 0.0
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    description: str = ""


@dataclass
class OutputSample:
    """A recorded output sample from a model run."""

    model_id: str = ""
    prompt_version: str = ""
    response: str = ""
    response_length: int = 0
    code_ratio: float = 0.0
    accepted: bool = True
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class DriftReport:
    """Aggregated drift report for a model over a time period."""

    model_id: str = ""
    period_hours: int = 24
    total_samples: int = 0
    alerts: list[DriftAlert] = field(default_factory=list)
    overall_health: str = "healthy"


# ── In-memory stores ─────────────────────────────────────────────────

_baselines: dict[str, BehavioralBaseline] = {}
_samples: list[OutputSample] = []
_alerts: list[DriftAlert] = []


def clear_drift_data() -> None:
    """Clear all stored drift data (for testing)."""
    _baselines.clear()
    _samples.clear()
    _alerts.clear()


# ── Baseline Management ──────────────────────────────────────────────


def register_baseline(
    model_id: str,
    prompt_version: str,
    avg_length: float,
    avg_code_ratio: float,
    construct_counts: dict[str, float] | None = None,
    acceptance_rate: float = 1.0,
    sample_count: int = 0,
) -> BehavioralBaseline:
    """Register a behavioral baseline for a model."""
    baseline = BehavioralBaseline(
        model_id=model_id,
        prompt_version=prompt_version,
        avg_response_length=avg_length,
        avg_code_ratio=avg_code_ratio,
        avg_construct_counts=construct_counts or {},
        acceptance_rate=acceptance_rate,
        sample_count=sample_count,
    )
    _baselines[model_id] = baseline
    logger.info(
        "Registered baseline: model=%s prompt=%s avg_length=%.1f",
        model_id,
        prompt_version,
        avg_length,
    )
    return baseline


# ── Sample Recording ─────────────────────────────────────────────────


def record_sample(
    model_id: str,
    prompt_version: str,
    response: str,
    accepted: bool = True,
) -> OutputSample:
    """Record an output sample from a model run."""
    sample = OutputSample(
        model_id=model_id,
        prompt_version=prompt_version,
        response=response,
        response_length=len(response),
        code_ratio=compute_code_ratio(response),
        accepted=accepted,
    )
    _samples.append(sample)
    logger.debug(
        "Recorded sample: model=%s length=%d code_ratio=%.2f",
        model_id,
        sample.response_length,
        sample.code_ratio,
    )
    return sample


# ── Analysis Utilities ───────────────────────────────────────────────

# Patterns that indicate a line is code rather than prose
_CODE_PATTERNS = re.compile(
    r"^\s{2,}\S"  # indented lines
    r"|[=(){}\[\];]"  # common code characters
    r"|^\s*(def |class |import |from |if |for |while |return |raise )"
    r"|^\s*#"  # comments
    r"|^\s*@"  # decorators
)


def compute_code_ratio(text: str) -> float:
    """Compute the ratio of lines that appear to be code.

    Returns a float between 0.0 and 1.0.
    """
    if not text.strip():
        return 0.0

    lines = text.splitlines()
    if not lines:
        return 0.0

    code_lines = sum(1 for line in lines if _CODE_PATTERNS.search(line))
    return code_lines / len(lines)


def count_constructs(code: str) -> dict[str, int]:
    """Count code constructs in a text block.

    Counts:
    - try_except: try/except blocks
    - type_annotations: type annotation patterns (: type, -> type)
    - comments: lines starting with #
    - imports: import/from ... import lines
    - class_def: class definitions
    - function_def: function/method definitions
    """
    counts: dict[str, int] = {
        "try_except": 0,
        "type_annotations": 0,
        "comments": 0,
        "imports": 0,
        "class_def": 0,
        "function_def": 0,
    }

    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("try:") or stripped.startswith("except"):
            counts["try_except"] += 1
        if re.search(r":\s*\w+[\w\[\], |]*\s*[=)]", line) or re.search(
            r"->\s*\w+", line
        ):
            counts["type_annotations"] += 1
        if stripped.startswith("#"):
            counts["comments"] += 1
        if stripped.startswith("import ") or stripped.startswith("from "):
            counts["imports"] += 1
        if stripped.startswith("class "):
            counts["class_def"] += 1
        if stripped.startswith("def "):
            counts["function_def"] += 1

    return counts


# ── Drift Detection ──────────────────────────────────────────────────


def _severity_from_deviation(deviation_pct: float) -> DriftSeverity:
    """Map a deviation percentage to a severity level."""
    abs_dev = abs(deviation_pct)
    if abs_dev >= 100.0:
        return DriftSeverity.CRITICAL
    if abs_dev >= 50.0:
        return DriftSeverity.HIGH
    if abs_dev >= 25.0:
        return DriftSeverity.MEDIUM
    return DriftSeverity.LOW


def _compute_deviation(baseline_val: float, current_val: float) -> float:
    """Compute percentage deviation from baseline."""
    if baseline_val == 0.0:
        return 0.0 if current_val == 0.0 else 100.0
    return ((current_val - baseline_val) / baseline_val) * 100.0


def detect_behavioral_drift(
    model_id: str,
    window_hours: int = 6,
    threshold_pct: float = 20.0,
) -> list[DriftAlert]:
    """Detect behavioral drift by comparing recent samples to baseline.

    Checks response length and code ratio against the registered baseline.
    """
    baseline = _baselines.get(model_id)
    if baseline is None:
        logger.warning("No baseline for model %s — skipping drift check", model_id)
        return []

    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    recent = [
        s for s in _samples if s.model_id == model_id and s.timestamp >= cutoff
    ]

    if not recent:
        return []

    alerts: list[DriftAlert] = []

    # Check response length drift
    avg_length = sum(s.response_length for s in recent) / len(recent)
    length_dev = _compute_deviation(baseline.avg_response_length, avg_length)
    if abs(length_dev) > threshold_pct:
        severity = _severity_from_deviation(length_dev)
        alert = DriftAlert(
            drift_type=DriftType.BEHAVIORAL,
            severity=severity,
            model_id=model_id,
            metric_name="response_length",
            baseline_value=baseline.avg_response_length,
            current_value=avg_length,
            deviation_pct=length_dev,
            description=(
                f"Response length drifted {length_dev:+.1f}% from baseline "
                f"({baseline.avg_response_length:.0f} -> {avg_length:.0f})"
            ),
        )
        alerts.append(alert)
        _alerts.append(alert)

    # Check code ratio drift
    avg_ratio = sum(s.code_ratio for s in recent) / len(recent)
    ratio_dev = _compute_deviation(baseline.avg_code_ratio, avg_ratio)
    if abs(ratio_dev) > threshold_pct:
        severity = _severity_from_deviation(ratio_dev)
        alert = DriftAlert(
            drift_type=DriftType.BEHAVIORAL,
            severity=severity,
            model_id=model_id,
            metric_name="code_ratio",
            baseline_value=baseline.avg_code_ratio,
            current_value=avg_ratio,
            deviation_pct=ratio_dev,
            description=(
                f"Code ratio drifted {ratio_dev:+.1f}% from baseline "
                f"({baseline.avg_code_ratio:.2f} -> {avg_ratio:.2f})"
            ),
        )
        alerts.append(alert)
        _alerts.append(alert)

    if alerts:
        logger.warning(
            "Behavioral drift detected: model=%s alerts=%d",
            model_id,
            len(alerts),
        )

    return alerts


def detect_performance_drift(
    model_id: str,
    window_hours: int = 168,
    threshold_pct: float = 10.0,
) -> list[DriftAlert]:
    """Detect performance drift by comparing acceptance rate to baseline."""
    baseline = _baselines.get(model_id)
    if baseline is None:
        logger.warning("No baseline for model %s — skipping perf check", model_id)
        return []

    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    recent = [
        s for s in _samples if s.model_id == model_id and s.timestamp >= cutoff
    ]

    if not recent:
        return []

    alerts: list[DriftAlert] = []

    current_rate = sum(1 for s in recent if s.accepted) / len(recent)
    rate_dev = _compute_deviation(baseline.acceptance_rate, current_rate)

    # Only alert on drops (negative deviation)
    if rate_dev < -threshold_pct:
        severity = _severity_from_deviation(rate_dev)
        alert = DriftAlert(
            drift_type=DriftType.PERFORMANCE,
            severity=severity,
            model_id=model_id,
            metric_name="acceptance_rate",
            baseline_value=baseline.acceptance_rate,
            current_value=current_rate,
            deviation_pct=rate_dev,
            description=(
                f"Acceptance rate dropped {abs(rate_dev):.1f}% from baseline "
                f"({baseline.acceptance_rate:.2f} -> {current_rate:.2f})"
            ),
        )
        alerts.append(alert)
        _alerts.append(alert)
        logger.warning(
            "Performance drift detected: model=%s acceptance_rate=%.2f (baseline=%.2f)",
            model_id,
            current_rate,
            baseline.acceptance_rate,
        )

    return alerts


# ── Health Status ────────────────────────────────────────────────────


def compute_health_status(alerts: list[DriftAlert]) -> str:
    """Compute overall health status from a list of alerts.

    Returns one of: "healthy", "warning", "degraded", "critical".
    """
    if not alerts:
        return "healthy"

    severities = [a.severity for a in alerts]

    if DriftSeverity.CRITICAL in severities:
        return "critical"
    if DriftSeverity.HIGH in severities:
        return "degraded"
    if DriftSeverity.MEDIUM in severities or len(alerts) >= 3:
        return "warning"
    return "warning" if alerts else "healthy"


# ── Reporting ────────────────────────────────────────────────────────


def get_drift_report(model_id: str, period_hours: int = 24) -> DriftReport:
    """Generate a full drift report for a model.

    Runs both behavioral and performance drift detection and returns
    a consolidated report.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=period_hours)
    recent_samples = [
        s for s in _samples if s.model_id == model_id and s.timestamp >= cutoff
    ]

    # Run detections
    behavioral_alerts = detect_behavioral_drift(model_id, window_hours=period_hours)
    performance_alerts = detect_performance_drift(model_id, window_hours=period_hours)
    all_alerts = behavioral_alerts + performance_alerts

    health = compute_health_status(all_alerts)

    report = DriftReport(
        model_id=model_id,
        period_hours=period_hours,
        total_samples=len(recent_samples),
        alerts=all_alerts,
        overall_health=health,
    )

    logger.info(
        "Drift report: model=%s samples=%d alerts=%d health=%s",
        model_id,
        report.total_samples,
        len(report.alerts),
        report.overall_health,
    )

    return report


def get_recent_alerts(hours: int = 24) -> list[DriftAlert]:
    """Get drift alerts from the last N hours."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    return [a for a in _alerts if a.detected_at >= cutoff]


# ── Serialization ────────────────────────────────────────────────────


def drift_report_to_json(report: DriftReport) -> dict:
    """Serialize a DriftReport to a JSON-compatible dict."""
    return {
        "model_id": report.model_id,
        "period_hours": report.period_hours,
        "total_samples": report.total_samples,
        "overall_health": report.overall_health,
        "alerts": [
            {
                "id": a.id,
                "drift_type": a.drift_type.value,
                "severity": a.severity.value,
                "model_id": a.model_id,
                "metric_name": a.metric_name,
                "baseline_value": a.baseline_value,
                "current_value": a.current_value,
                "deviation_pct": round(a.deviation_pct, 2),
                "detected_at": a.detected_at.isoformat(),
                "description": a.description,
            }
            for a in report.alerts
        ],
        "alert_count": len(report.alerts),
    }
