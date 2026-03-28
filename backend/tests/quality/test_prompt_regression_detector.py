"""Tests for Prompt Regression Detector."""

from __future__ import annotations

from app.quality.prompt_regression_detector import (
    BatchRegressionReport,
    GateDecision,
    PromptRegressionDetector,
    PromptTestResult,
    RegressionConfig,
    RegressionReport,
    RegressionSeverity,
    _classify_severity,
    _compute_mean,
    _gate_from_severity,
    _z_test_proportions,
)

# ── _compute_mean ───────────────────────────────────────────────────────

class TestComputeMean:
    def test_basic(self):
        assert _compute_mean([1.0, 2.0, 3.0]) == 2.0

    def test_empty(self):
        assert _compute_mean([]) == 0.0

    def test_single(self):
        assert _compute_mean([5.0]) == 5.0


# ── _classify_severity ──────────────────────────────────────────────────

class TestClassifySeverity:
    def test_no_regression(self):
        cfg = RegressionConfig()
        assert _classify_severity(0.0, cfg) == RegressionSeverity.NONE

    def test_negative_improvement(self):
        cfg = RegressionConfig()
        assert _classify_severity(-0.1, cfg) == RegressionSeverity.NONE

    def test_minor(self):
        cfg = RegressionConfig()
        assert _classify_severity(0.05, cfg) == RegressionSeverity.MINOR

    def test_major(self):
        cfg = RegressionConfig()
        assert _classify_severity(0.12, cfg) == RegressionSeverity.MAJOR

    def test_critical(self):
        cfg = RegressionConfig()
        assert _classify_severity(0.20, cfg) == RegressionSeverity.CRITICAL

    def test_below_minor_threshold(self):
        cfg = RegressionConfig()
        assert _classify_severity(0.02, cfg) == RegressionSeverity.NONE


# ── _gate_from_severity ─────────────────────────────────────────────────

class TestGateFromSeverity:
    def test_none_passes(self):
        assert _gate_from_severity(RegressionSeverity.NONE) == GateDecision.PASS

    def test_minor_passes(self):
        assert _gate_from_severity(RegressionSeverity.MINOR) == GateDecision.PASS

    def test_major_warns(self):
        assert _gate_from_severity(RegressionSeverity.MAJOR) == GateDecision.WARN

    def test_critical_blocks(self):
        assert _gate_from_severity(RegressionSeverity.CRITICAL) == GateDecision.BLOCK


# ── _z_test_proportions ─────────────────────────────────────────────────

class TestZTestProportions:
    def test_identical_proportions(self):
        z, p = _z_test_proportions(0.5, 100, 0.5, 100)
        assert z == 0.0

    def test_different_proportions(self):
        z, p = _z_test_proportions(0.9, 100, 0.5, 100)
        assert z > 0  # baseline better

    def test_zero_samples(self):
        z, p = _z_test_proportions(0.5, 0, 0.5, 100)
        assert z == 0.0
        assert p == 1.0

    def test_extreme_proportions(self):
        z, p = _z_test_proportions(1.0, 100, 1.0, 100)
        assert z == 0.0


# ── PromptRegressionDetector ────────────────────────────────────────────

class TestPromptRegressionDetector:
    def test_record_result(self):
        det = PromptRegressionDetector()
        result = det.record_result("family1", "v1", "test input", 0.9, 100.0, 0.01)
        assert isinstance(result, PromptTestResult)
        assert result.prompt_version == "v1"
        assert result.quality_score == 0.9

    def test_clamp_quality(self):
        det = PromptRegressionDetector()
        r = det.record_result("f", "v1", quality_score=1.5)
        assert r.quality_score == 1.0
        r2 = det.record_result("f", "v1", quality_score=-0.5)
        assert r2.quality_score == 0.0

    def test_no_regression(self):
        det = PromptRegressionDetector()
        for _ in range(10):
            det.record_result("family1", "v1", "input", 0.85, 100.0)
            det.record_result("family1", "v2", "input", 0.87, 95.0)
        report = det.compare_versions("family1", "v1", "v2")
        assert isinstance(report, RegressionReport)
        assert report.overall_severity == RegressionSeverity.NONE
        assert report.gate == GateDecision.PASS

    def test_quality_regression(self):
        det = PromptRegressionDetector()
        for _ in range(10):
            det.record_result("family1", "v1", "input", 0.90, 100.0)
            det.record_result("family1", "v2", "input", 0.50, 100.0)
        report = det.compare_versions("family1", "v1", "v2")
        assert report.overall_severity in {RegressionSeverity.MAJOR, RegressionSeverity.CRITICAL}
        assert report.gate in {GateDecision.WARN, GateDecision.BLOCK}

    def test_latency_regression(self):
        det = PromptRegressionDetector()
        for _ in range(5):
            det.record_result("f", "v1", latency_ms=100.0)
            det.record_result("f", "v2", latency_ms=200.0)  # 100% increase
        report = det.compare_versions("f", "v1", "v2")
        lat_comp = next(c for c in report.metric_comparisons if c.metric_name == "latency_ms")
        assert lat_comp.is_regression is True

    def test_cost_regression(self):
        det = PromptRegressionDetector()
        for _ in range(5):
            det.record_result("f", "v1", cost_usd=0.01)
            det.record_result("f", "v2", cost_usd=0.02)
        report = det.compare_versions("f", "v1", "v2")
        cost_comp = next(c for c in report.metric_comparisons if c.metric_name == "cost_usd")
        assert cost_comp.is_regression is True

    def test_safety_regression(self):
        det = PromptRegressionDetector()
        for _ in range(5):
            det.record_result("f", "v1", safety_passed=True)
        for _ in range(5):
            det.record_result("f", "v2", safety_passed=False)
        report = det.compare_versions("f", "v1", "v2")
        safety_comp = next(c for c in report.metric_comparisons if c.metric_name == "safety_rate")
        assert safety_comp.is_regression is True
        assert safety_comp.severity == RegressionSeverity.CRITICAL

    def test_per_test_case_tracking(self):
        det = PromptRegressionDetector()
        det.record_result("f", "v1", "case_A", quality_score=0.90)
        det.record_result("f", "v1", "case_B", quality_score=0.85)
        det.record_result("f", "v2", "case_A", quality_score=0.40)
        det.record_result("f", "v2", "case_B", quality_score=0.88)
        report = det.compare_versions("f", "v1", "v2")
        assert report.regressed_cases >= 1

    def test_improved_cases(self):
        det = PromptRegressionDetector()
        det.record_result("f", "v1", "case_A", quality_score=0.50)
        det.record_result("f", "v2", "case_A", quality_score=0.90)
        report = det.compare_versions("f", "v1", "v2")
        assert report.improved_cases >= 1

    def test_metric_comparisons_count(self):
        det = PromptRegressionDetector()
        det.record_result("f", "v1", quality_score=0.8)
        det.record_result("f", "v2", quality_score=0.8)
        report = det.compare_versions("f", "v1", "v2")
        assert len(report.metric_comparisons) == 4  # quality, latency, cost, safety

    def test_batch_compare(self):
        det = PromptRegressionDetector()
        for _ in range(5):
            det.record_result("f1", "v1", quality_score=0.9)
            det.record_result("f1", "v2", quality_score=0.9)
            det.record_result("f2", "v1", quality_score=0.9)
            det.record_result("f2", "v2", quality_score=0.3)
        report = det.batch_compare("v1", "v2")
        assert isinstance(report, BatchRegressionReport)
        assert report.total_families == 2
        assert report.total_regressions >= 1

    def test_batch_all_pass(self):
        det = PromptRegressionDetector()
        for _ in range(5):
            det.record_result("f1", "v1", quality_score=0.8)
            det.record_result("f1", "v2", quality_score=0.82)
        report = det.batch_compare("v1", "v2")
        assert report.overall_gate == GateDecision.PASS

    def test_batch_critical_blocks(self):
        det = PromptRegressionDetector()
        for _ in range(5):
            det.record_result("f1", "v1", safety_passed=True)
            det.record_result("f1", "v2", safety_passed=False)
        report = det.batch_compare("v1", "v2")
        assert report.overall_gate == GateDecision.BLOCK

    def test_empty_family(self):
        det = PromptRegressionDetector()
        report = det.compare_versions("nonexistent", "v1", "v2")
        assert report.baseline_count == 0
        assert report.candidate_count == 0

    def test_custom_config(self):
        cfg = RegressionConfig(minor_threshold=0.01, major_threshold=0.02)
        det = PromptRegressionDetector(config=cfg)
        for _ in range(5):
            det.record_result("f", "v1", quality_score=0.90)
            det.record_result("f", "v2", quality_score=0.87)
        report = det.compare_versions("f", "v1", "v2")
        # 3.3% drop is major with this config
        assert report.overall_severity != RegressionSeverity.NONE

    def test_statistical_significance(self):
        det = PromptRegressionDetector()
        for _ in range(50):
            det.record_result("f", "v1", quality_score=0.90)
            det.record_result("f", "v2", quality_score=0.50)
        report = det.compare_versions("f", "v1", "v2")
        # Large sample, big difference → significant
        assert report.z_score > 0
