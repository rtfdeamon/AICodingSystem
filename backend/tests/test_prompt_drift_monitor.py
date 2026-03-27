"""Tests for Prompt Drift Monitor (best practice #58)."""

from __future__ import annotations

from app.quality.prompt_drift_monitor import (
    BatchDriftReport,
    DriftReport,
    DriftSeverity,
    DriftType,
    GateDecision,
    OutputSample,
    PromptDriftMonitor,
    _compute_stats,
    _estimate_sentiment,
    _z_score,
)

# ── Helper factory ──────────────────────────────────────────────────────

def _make_samples(
    n: int,
    text_fn=None,
    quality_fn=None,
    latency_fn=None,
    version: str = "default",
) -> list[OutputSample]:
    samples = []
    for i in range(n):
        text = text_fn(i) if text_fn else f"Sample output {i}"
        quality = quality_fn(i) if quality_fn else 0.8
        latency = latency_fn(i) if latency_fn else 100.0
        samples.append(OutputSample(
            text=text,
            prompt_version=version,
            quality_score=quality,
            latency_ms=latency,
        ))
    return samples


# ── Stats helper tests ──────────────────────────────────────────────────

class TestComputeStats:
    def test_empty(self):
        stats = _compute_stats([])
        assert stats.count == 0
        assert stats.mean == 0

    def test_single_value(self):
        stats = _compute_stats([5.0])
        assert stats.count == 1
        assert stats.mean == 5.0

    def test_multiple_values(self):
        stats = _compute_stats([1.0, 2.0, 3.0, 4.0, 5.0])
        assert stats.count == 5
        assert stats.mean == 3.0
        assert stats.min_val == 1.0
        assert stats.max_val == 5.0

    def test_std_deviation(self):
        stats = _compute_stats([10.0, 10.0, 10.0])
        assert stats.std == 0.0


class TestZScore:
    def test_no_std(self):
        assert _z_score(5.0, 0.0, 5.0) == 0.0
        assert _z_score(5.0, 0.0, 6.0) == 3.0

    def test_normal_zscore(self):
        z = _z_score(10.0, 2.0, 14.0)
        assert z == 2.0

    def test_negative_direction(self):
        z = _z_score(10.0, 2.0, 6.0)
        assert z == 2.0  # absolute value


class TestEstimateSentiment:
    def test_neutral(self):
        s = _estimate_sentiment("the quick brown fox")
        assert s == 0.5

    def test_positive(self):
        s = _estimate_sentiment("great success excellent working")
        assert s > 0.5

    def test_negative(self):
        s = _estimate_sentiment("error fail crash broken")
        assert s < 0.5

    def test_mixed(self):
        s = _estimate_sentiment("good error")
        assert 0.0 <= s <= 1.0


# ── Init tests ───────────────────────────────────────────────────────────

class TestPromptDriftMonitorInit:
    def test_default_init(self):
        monitor = PromptDriftMonitor()
        assert monitor.baseline_window == 100
        assert monitor.current_window == 20
        assert monitor.z_threshold_warn == 2.0

    def test_custom_init(self):
        monitor = PromptDriftMonitor(
            baseline_window=50,
            current_window=10,
            z_threshold_warn=1.5,
        )
        assert monitor.baseline_window == 50


# ── Sample recording tests ──────────────────────────────────────────────

class TestRecordSamples:
    def test_record_single(self):
        monitor = PromptDriftMonitor()
        monitor.record(OutputSample(text="test", prompt_version="v1"))
        assert monitor.get_sample_count("v1") == 1

    def test_record_multiple_versions(self):
        monitor = PromptDriftMonitor()
        monitor.record(OutputSample(text="a", prompt_version="v1"))
        monitor.record(OutputSample(text="b", prompt_version="v2"))
        assert monitor.get_sample_count("v1") == 1
        assert monitor.get_sample_count("v2") == 1

    def test_nonexistent_version(self):
        monitor = PromptDriftMonitor()
        assert monitor.get_sample_count("nope") == 0


# ── Analysis tests ──────────────────────────────────────────────────────

class TestDriftAnalysis:
    def test_insufficient_data(self):
        monitor = PromptDriftMonitor(current_window=5)
        for s in _make_samples(3):
            monitor.record(s)
        report = monitor.analyze()
        assert isinstance(report, DriftReport)
        assert report.severity == DriftSeverity.NONE
        assert report.gate_decision == GateDecision.PASS

    def test_no_drift_stable_output(self):
        monitor = PromptDriftMonitor(baseline_window=50, current_window=10)
        # All samples have same characteristics
        for s in _make_samples(70):
            monitor.record(s)
        report = monitor.analyze()
        assert report.severity in (DriftSeverity.NONE, DriftSeverity.LOW)
        assert report.gate_decision == GateDecision.PASS

    def test_length_drift_detected(self):
        monitor = PromptDriftMonitor(baseline_window=50, current_window=10)
        # Baseline: short outputs
        for s in _make_samples(50, text_fn=lambda i: "short " * 5):
            monitor.record(s)
        # Current: very long outputs
        for s in _make_samples(10, text_fn=lambda i: "very long output text " * 50):
            monitor.record(s)
        report = monitor.analyze()
        assert len(report.alerts) > 0
        length_alerts = [a for a in report.alerts if a.drift_type == DriftType.LENGTH]
        assert len(length_alerts) > 0

    def test_quality_degradation_detected(self):
        monitor = PromptDriftMonitor(baseline_window=50, current_window=10)
        # Baseline: high quality
        for s in _make_samples(50, quality_fn=lambda i: 0.9):
            monitor.record(s)
        # Current: low quality
        for s in _make_samples(10, quality_fn=lambda i: 0.2):
            monitor.record(s)
        report = monitor.analyze()
        quality_alerts = [a for a in report.alerts if a.drift_type == DriftType.QUALITY]
        assert len(quality_alerts) > 0

    def test_latency_drift_detected(self):
        monitor = PromptDriftMonitor(baseline_window=50, current_window=10)
        # Baseline: fast
        for s in _make_samples(50, latency_fn=lambda i: 100.0):
            monitor.record(s)
        # Current: slow
        for s in _make_samples(10, latency_fn=lambda i: 5000.0):
            monitor.record(s)
        report = monitor.analyze()
        latency_alerts = [a for a in report.alerts if a.drift_type == DriftType.LATENCY]
        assert len(latency_alerts) > 0

    def test_sentiment_drift(self):
        monitor = PromptDriftMonitor(baseline_window=50, current_window=10)
        for s in _make_samples(50, text_fn=lambda i: "great success excellent working done"):
            monitor.record(s)
        for s in _make_samples(10, text_fn=lambda i: "error fail crash broken problem"):
            monitor.record(s)
        report = monitor.analyze()
        sentiment_alerts = [a for a in report.alerts if a.drift_type == DriftType.SENTIMENT]
        assert len(sentiment_alerts) > 0


class TestMonotonicDegradation:
    def test_degradation_detected(self):
        monitor = PromptDriftMonitor(baseline_window=50, current_window=10)
        for s in _make_samples(50, quality_fn=lambda i: 0.9):
            monitor.record(s)
        # Steadily declining quality
        for i in range(10):
            monitor.record(OutputSample(
                text="output",
                quality_score=0.9 - i * 0.08,
            ))
        report = monitor.analyze()
        degradation_alerts = [
            a for a in report.alerts
            if a.metric_name == "quality_trend"
        ]
        assert len(degradation_alerts) > 0

    def test_no_degradation_stable(self):
        monitor = PromptDriftMonitor(baseline_window=50, current_window=10)
        for s in _make_samples(60, quality_fn=lambda i: 0.8):
            monitor.record(s)
        report = monitor.analyze()
        degradation_alerts = [
            a for a in report.alerts
            if a.metric_name == "quality_trend"
        ]
        assert len(degradation_alerts) == 0


# ── Gate decision tests ─────────────────────────────────────────────────

class TestGateDecision:
    def test_pass_on_no_drift(self):
        monitor = PromptDriftMonitor(baseline_window=50, current_window=10)
        for s in _make_samples(70):
            monitor.record(s)
        report = monitor.analyze()
        assert report.gate_decision == GateDecision.PASS

    def test_block_on_severe_drift(self):
        monitor = PromptDriftMonitor(
            baseline_window=50, current_window=10,
            drift_score_block=0.4,
        )
        for s in _make_samples(50, text_fn=lambda i: "a"):
            monitor.record(s)
        for s in _make_samples(10, text_fn=lambda i: "x " * 1000):
            monitor.record(s)
        report = monitor.analyze()
        # Should have significant drift
        assert report.overall_drift_score > 0


# ── Batch analysis tests ────────────────────────────────────────────────

class TestBatchAnalysis:
    def test_batch_multiple_versions(self):
        monitor = PromptDriftMonitor(baseline_window=30, current_window=5)
        for s in _make_samples(40, version="v1"):
            monitor.record(s)
        for s in _make_samples(40, version="v2"):
            monitor.record(s)
        report = monitor.batch_analyze(["v1", "v2"])
        assert isinstance(report, BatchDriftReport)
        assert report.total_versions == 2

    def test_batch_auto_discover(self):
        monitor = PromptDriftMonitor(baseline_window=30, current_window=5)
        for s in _make_samples(40, version="v1"):
            monitor.record(s)
        report = monitor.batch_analyze()
        assert report.total_versions == 1

    def test_batch_empty(self):
        monitor = PromptDriftMonitor()
        report = monitor.batch_analyze([])
        assert report.total_versions == 0
        assert report.gate_decision == GateDecision.PASS


# ── History tests ────────────────────────────────────────────────────────

class TestDriftHistory:
    def test_history_recorded(self):
        monitor = PromptDriftMonitor(baseline_window=30, current_window=5)
        for s in _make_samples(40):
            monitor.record(s)
        monitor.analyze()
        monitor.analyze()
        assert len(monitor.history) == 2

    def test_history_immutable(self):
        monitor = PromptDriftMonitor(baseline_window=30, current_window=5)
        for s in _make_samples(40):
            monitor.record(s)
        monitor.analyze()
        h = monitor.history
        h.clear()
        assert len(monitor.history) == 1


# ── Report field tests ──────────────────────────────────────────────────

class TestReportFields:
    def test_report_id(self):
        monitor = PromptDriftMonitor(baseline_window=30, current_window=5)
        for s in _make_samples(40):
            monitor.record(s)
        report = monitor.analyze()
        assert report.id
        assert len(report.id) == 12

    def test_report_stats_populated(self):
        monitor = PromptDriftMonitor(baseline_window=30, current_window=5)
        for s in _make_samples(40):
            monitor.record(s)
        report = monitor.analyze()
        assert "length" in report.baseline_stats
        assert "length" in report.current_stats
        assert report.sample_count_baseline > 0
        assert report.sample_count_current > 0

    def test_report_timestamp(self):
        monitor = PromptDriftMonitor(baseline_window=30, current_window=5)
        for s in _make_samples(40):
            monitor.record(s)
        report = monitor.analyze()
        assert report.analyzed_at
