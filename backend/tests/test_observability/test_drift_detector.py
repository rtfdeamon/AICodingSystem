"""Tests for output drift detection and behavioral baseline monitor."""

from __future__ import annotations

import pytest

from app.observability.drift_detector import (
    BehavioralBaseline,
    DriftAlert,
    DriftReport,
    DriftSeverity,
    DriftType,
    clear_drift_data,
    compute_code_ratio,
    compute_health_status,
    count_constructs,
    detect_behavioral_drift,
    detect_performance_drift,
    drift_report_to_json,
    get_drift_report,
    get_recent_alerts,
    record_sample,
    register_baseline,
)


@pytest.fixture(autouse=True)
def _clean() -> None:
    clear_drift_data()


# ── Baseline Registration ────────────────────────────────────────────


class TestRegisterBaseline:
    def test_register_returns_baseline(self) -> None:
        bl = register_baseline(
            model_id="claude-sonnet",
            prompt_version="v1",
            avg_length=500.0,
            avg_code_ratio=0.6,
            construct_counts={"try_except": 2.0},
            acceptance_rate=0.95,
            sample_count=100,
        )
        assert isinstance(bl, BehavioralBaseline)
        assert bl.model_id == "claude-sonnet"
        assert bl.prompt_version == "v1"
        assert bl.avg_response_length == 500.0
        assert bl.avg_code_ratio == 0.6
        assert bl.avg_construct_counts == {"try_except": 2.0}
        assert bl.acceptance_rate == 0.95
        assert bl.sample_count == 100

    def test_register_overwrites_previous(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5)
        bl = register_baseline("m1", "v2", 200.0, 0.7)
        assert bl.prompt_version == "v2"
        assert bl.avg_response_length == 200.0

    def test_register_defaults(self) -> None:
        bl = register_baseline("m1", "v1", 100.0, 0.5)
        assert bl.acceptance_rate == 1.0
        assert bl.sample_count == 0
        assert bl.avg_construct_counts == {}


# ── Sample Recording ─────────────────────────────────────────────────


class TestRecordSample:
    def test_record_basic_sample(self) -> None:
        sample = record_sample("m1", "v1", "def foo():\n    return 42\n", True)
        assert sample.model_id == "m1"
        assert sample.prompt_version == "v1"
        assert sample.response_length == len("def foo():\n    return 42\n")
        assert sample.accepted is True
        assert sample.code_ratio > 0.0

    def test_record_rejected_sample(self) -> None:
        sample = record_sample("m1", "v1", "bad output", False)
        assert sample.accepted is False

    def test_record_empty_response(self) -> None:
        sample = record_sample("m1", "v1", "", True)
        assert sample.response_length == 0
        assert sample.code_ratio == 0.0


# ── Code Ratio Computation ───────────────────────────────────────────


class TestComputeCodeRatio:
    def test_pure_code(self) -> None:
        code = "def foo():\n    return 42\n    x = 1\n"
        ratio = compute_code_ratio(code)
        assert ratio > 0.5

    def test_pure_prose(self) -> None:
        text = "This is plain text.\nNo code here.\nJust words."
        ratio = compute_code_ratio(text)
        assert ratio < 0.3

    def test_empty_string(self) -> None:
        assert compute_code_ratio("") == 0.0

    def test_whitespace_only(self) -> None:
        assert compute_code_ratio("   \n  \n") == 0.0

    def test_mixed_content(self) -> None:
        mixed = "Here is some text.\ndef hello():\n    print('hi')\nMore text."
        ratio = compute_code_ratio(mixed)
        assert 0.0 < ratio < 1.0


# ── Construct Counting ───────────────────────────────────────────────


class TestCountConstructs:
    def test_counts_all_constructs(self) -> None:
        code = (
            "import os\n"
            "from sys import path\n"
            "# A comment\n"
            "class MyClass:\n"
            "def my_func(x: int) -> str:\n"
            "    try:\n"
            "        pass\n"
            "    except ValueError:\n"
            "        pass\n"
        )
        counts = count_constructs(code)
        assert counts["imports"] == 2
        assert counts["comments"] == 1
        assert counts["class_def"] == 1
        assert counts["function_def"] == 1
        assert counts["try_except"] == 2  # try: + except

    def test_type_annotations(self) -> None:
        code = "def foo(x: int, y: str) -> bool:\n    name: str = 'hello'\n"
        counts = count_constructs(code)
        assert counts["type_annotations"] >= 1

    def test_empty_code(self) -> None:
        counts = count_constructs("")
        assert all(v == 0 for v in counts.values())


# ── Behavioral Drift Detection ───────────────────────────────────────


class TestBehavioralDrift:
    def test_no_baseline_returns_empty(self) -> None:
        alerts = detect_behavioral_drift("unknown_model")
        assert alerts == []

    def test_no_samples_returns_empty(self) -> None:
        register_baseline("m1", "v1", 500.0, 0.6)
        alerts = detect_behavioral_drift("m1")
        assert alerts == []

    def test_detects_length_drift(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5)
        # Record samples with much longer responses (~200 chars)
        for _ in range(5):
            record_sample("m1", "v1", "x" * 200, True)

        alerts = detect_behavioral_drift("m1", threshold_pct=20.0)
        length_alerts = [a for a in alerts if a.metric_name == "response_length"]
        assert len(length_alerts) == 1
        assert length_alerts[0].deviation_pct > 20.0
        assert length_alerts[0].drift_type == DriftType.BEHAVIORAL

    def test_detects_code_ratio_drift(self) -> None:
        register_baseline("m1", "v1", 50.0, 0.8)
        # Record samples with low code ratio (plain text)
        for _ in range(5):
            text = "This is just plain text with no code patterns at all."
            record_sample("m1", "v1", text, True)

        alerts = detect_behavioral_drift("m1", threshold_pct=20.0)
        ratio_alerts = [a for a in alerts if a.metric_name == "code_ratio"]
        assert len(ratio_alerts) >= 1
        assert ratio_alerts[0].deviation_pct < 0  # dropped

    def test_no_drift_within_threshold(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5)
        # Record samples close to baseline
        for _ in range(5):
            # ~100 chars, mix of code and text
            record_sample("m1", "v1", "x" * 100, True)

        alerts = detect_behavioral_drift("m1", threshold_pct=50.0)
        length_alerts = [a for a in alerts if a.metric_name == "response_length"]
        assert len(length_alerts) == 0


# ── Performance Drift Detection ──────────────────────────────────────


class TestPerformanceDrift:
    def test_no_baseline_returns_empty(self) -> None:
        alerts = detect_performance_drift("unknown")
        assert alerts == []

    def test_detects_acceptance_drop(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5, acceptance_rate=0.9)
        # 10 samples, only 3 accepted = 0.30 rate (big drop from 0.9)
        for i in range(10):
            record_sample("m1", "v1", "response", accepted=(i < 3))

        alerts = detect_performance_drift("m1", threshold_pct=10.0)
        assert len(alerts) == 1
        assert alerts[0].metric_name == "acceptance_rate"
        assert alerts[0].drift_type == DriftType.PERFORMANCE
        assert alerts[0].deviation_pct < 0

    def test_no_alert_when_rate_stable(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5, acceptance_rate=0.9)
        # 10 samples, 9 accepted = 0.9 rate (matches baseline)
        for i in range(10):
            record_sample("m1", "v1", "response", accepted=(i < 9))

        alerts = detect_performance_drift("m1", threshold_pct=10.0)
        assert alerts == []

    def test_no_alert_on_rate_increase(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5, acceptance_rate=0.7)
        # All accepted = 1.0 rate (increase, not a problem)
        for _ in range(10):
            record_sample("m1", "v1", "response", accepted=True)

        alerts = detect_performance_drift("m1", threshold_pct=10.0)
        assert alerts == []


# ── Health Status ────────────────────────────────────────────────────


class TestHealthStatus:
    def test_no_alerts_healthy(self) -> None:
        assert compute_health_status([]) == "healthy"

    def test_critical_alert(self) -> None:
        alert = DriftAlert(severity=DriftSeverity.CRITICAL)
        assert compute_health_status([alert]) == "critical"

    def test_high_alert_degraded(self) -> None:
        alert = DriftAlert(severity=DriftSeverity.HIGH)
        assert compute_health_status([alert]) == "degraded"

    def test_medium_alert_warning(self) -> None:
        alert = DriftAlert(severity=DriftSeverity.MEDIUM)
        assert compute_health_status([alert]) == "warning"

    def test_low_alert_warning(self) -> None:
        alert = DriftAlert(severity=DriftSeverity.LOW)
        assert compute_health_status([alert]) == "warning"

    def test_many_low_alerts_warning(self) -> None:
        alerts = [DriftAlert(severity=DriftSeverity.LOW) for _ in range(4)]
        assert compute_health_status(alerts) == "warning"


# ── Drift Report ─────────────────────────────────────────────────────


class TestDriftReport:
    def test_report_healthy_model(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5, acceptance_rate=0.9)
        for _ in range(5):
            record_sample("m1", "v1", "x" * 100, True)

        report = get_drift_report("m1", period_hours=24)
        assert isinstance(report, DriftReport)
        assert report.model_id == "m1"
        assert report.total_samples == 5

    def test_report_with_drift(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5, acceptance_rate=0.9)
        # Big length drift
        for _ in range(5):
            record_sample("m1", "v1", "x" * 500, accepted=False)

        report = get_drift_report("m1", period_hours=24)
        assert len(report.alerts) > 0
        assert report.overall_health != "healthy"

    def test_report_no_baseline(self) -> None:
        report = get_drift_report("unknown_model")
        assert report.total_samples == 0
        assert report.alerts == []
        assert report.overall_health == "healthy"


# ── Alert Severity Levels ────────────────────────────────────────────


class TestAlertSeverity:
    def test_severity_from_large_deviation(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5)
        # 5x baseline length -> ~400% deviation -> CRITICAL
        for _ in range(5):
            record_sample("m1", "v1", "x" * 500, True)

        alerts = detect_behavioral_drift("m1", threshold_pct=10.0)
        length_alerts = [a for a in alerts if a.metric_name == "response_length"]
        assert length_alerts[0].severity == DriftSeverity.CRITICAL

    def test_severity_medium_deviation(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5)
        # ~40% increase -> MEDIUM
        for _ in range(5):
            record_sample("m1", "v1", "x" * 140, True)

        alerts = detect_behavioral_drift("m1", threshold_pct=20.0)
        length_alerts = [a for a in alerts if a.metric_name == "response_length"]
        assert len(length_alerts) == 1
        assert length_alerts[0].severity == DriftSeverity.MEDIUM


# ── JSON Serialization ───────────────────────────────────────────────


class TestJsonSerialization:
    def test_serialize_empty_report(self) -> None:
        report = DriftReport(model_id="m1", period_hours=24)
        data = drift_report_to_json(report)
        assert data["model_id"] == "m1"
        assert data["period_hours"] == 24
        assert data["alerts"] == []
        assert data["alert_count"] == 0

    def test_serialize_report_with_alerts(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5, acceptance_rate=0.9)
        for _ in range(5):
            record_sample("m1", "v1", "x" * 500, accepted=False)

        report = get_drift_report("m1")
        data = drift_report_to_json(report)

        assert data["model_id"] == "m1"
        assert data["total_samples"] == 5
        assert len(data["alerts"]) > 0
        assert data["alert_count"] == len(data["alerts"])

        alert_data = data["alerts"][0]
        assert "id" in alert_data
        assert "drift_type" in alert_data
        assert "severity" in alert_data
        assert "deviation_pct" in alert_data
        assert "detected_at" in alert_data


# ── Recent Alerts ────────────────────────────────────────────────────


class TestRecentAlerts:
    def test_get_recent_alerts_empty(self) -> None:
        assert get_recent_alerts() == []

    def test_get_recent_alerts_after_drift(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5)
        for _ in range(5):
            record_sample("m1", "v1", "x" * 500, True)

        detect_behavioral_drift("m1", threshold_pct=10.0)
        alerts = get_recent_alerts(hours=1)
        assert len(alerts) > 0


# ── Edge Cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    def test_zero_baseline_length(self) -> None:
        register_baseline("m1", "v1", 0.0, 0.0)
        record_sample("m1", "v1", "something", True)
        # Should not crash
        alerts = detect_behavioral_drift("m1", threshold_pct=20.0)
        assert isinstance(alerts, list)

    def test_single_sample(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5)
        record_sample("m1", "v1", "x" * 200, True)
        alerts = detect_behavioral_drift("m1", threshold_pct=20.0)
        assert isinstance(alerts, list)

    def test_clear_drift_data(self) -> None:
        register_baseline("m1", "v1", 100.0, 0.5)
        record_sample("m1", "v1", "test", True)
        clear_drift_data()
        assert detect_behavioral_drift("m1") == []
        assert get_recent_alerts() == []
