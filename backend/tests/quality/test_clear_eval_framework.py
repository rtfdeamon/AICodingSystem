"""Tests for CLEAR Evaluation Framework."""

from __future__ import annotations

import pytest

from app.quality.clear_eval_framework import (
    BatchCLEARReport,
    CLEAREvalFramework,
    CLEARScore,
    Dimension,
    DimensionScore,
    GateDecision,
    Trend,
    TrendAnalysis,
    _score_assurance,
    _score_cost,
    _score_efficacy,
    _score_latency,
    _score_reliability,
    _weighted_harmonic_mean,
)


# ── Scoring helpers ──────────────────────────────────────────────────────

class TestScoreCost:
    def test_zero_cost(self):
        assert _score_cost(0.0, 1.0) == 1.0

    def test_at_budget(self):
        assert _score_cost(1.0, 1.0) == pytest.approx(0.0)

    def test_over_budget(self):
        assert _score_cost(2.0, 1.0) == 0.0

    def test_half_budget(self):
        assert _score_cost(0.5, 1.0) == pytest.approx(0.5)

    def test_zero_budget(self):
        assert _score_cost(1.0, 0.0) == 0.0


class TestScoreLatency:
    def test_zero_latency(self):
        assert _score_latency(0.0, 5000.0) == 1.0

    def test_at_target(self):
        assert _score_latency(5000.0, 5000.0) == 1.0

    def test_double_target(self):
        assert _score_latency(10000.0, 5000.0) == pytest.approx(0.0)

    def test_over_double(self):
        assert _score_latency(20000.0, 5000.0) == 0.0

    def test_zero_target(self):
        assert _score_latency(100.0, 0.0) == 0.0


class TestScoreEfficacy:
    def test_perfect_accuracy(self):
        assert _score_efficacy(10, 10) == pytest.approx(1.0)

    def test_zero_accuracy(self):
        assert _score_efficacy(0, 10) == pytest.approx(0.0)

    def test_quality_score_only(self):
        assert _score_efficacy(0, 0, quality_score=0.8) == pytest.approx(0.8)

    def test_combined(self):
        score = _score_efficacy(8, 10, quality_score=0.9)
        assert 0.8 < score < 0.95

    def test_no_data(self):
        assert _score_efficacy(0, 0) == pytest.approx(0.5)


class TestScoreAssurance:
    def test_perfect(self):
        assert _score_assurance(1.0, 1.0, 1.0) == pytest.approx(1.0)

    def test_zero_safety(self):
        assert _score_assurance(0.0, 1.0, 1.0) < 1.0

    def test_partial(self):
        score = _score_assurance(0.8, 0.9, 0.7)
        assert 0.7 < score < 0.9


class TestScoreReliability:
    def test_perfect(self):
        assert _score_reliability(1.0, 1.0, 1.0) == pytest.approx(1.0)

    def test_zero_success(self):
        assert _score_reliability(0.0, 1.0, 1.0) < 1.0

    def test_success_weighted_double(self):
        # success_rate is weighted 2x in formula (s*2+c+e)/4
        s1 = _score_reliability(1.0, 0.5, 0.5)
        s2 = _score_reliability(0.5, 1.0, 1.0)
        assert s1 >= s2


class TestWeightedHarmonicMean:
    def test_equal_scores(self):
        scores = {d: 0.8 for d in Dimension}
        weights = {d: 1.0 for d in Dimension}
        assert _weighted_harmonic_mean(scores, weights) == pytest.approx(0.8)

    def test_zero_score(self):
        scores = {Dimension.COST: 0.0, Dimension.LATENCY: 1.0}
        weights = {Dimension.COST: 1.0, Dimension.LATENCY: 1.0}
        assert _weighted_harmonic_mean(scores, weights) == 0.0

    def test_weighted(self):
        scores = {Dimension.COST: 0.5, Dimension.LATENCY: 1.0}
        weights = {Dimension.COST: 2.0, Dimension.LATENCY: 1.0}
        result = _weighted_harmonic_mean(scores, weights)
        assert 0.5 < result < 1.0


# ── Framework evaluation ─────────────────────────────────────────────────

class TestCLEAREvaluation:
    def setup_method(self):
        self.framework = CLEAREvalFramework()

    def test_perfect_evaluation(self):
        result = self.framework.evaluate(
            cost_usd=0.0,
            budget_usd=1.0,
            latency_ms=1000.0,
            target_latency_ms=5000.0,
            correct=10,
            total=10,
            safety_pass_rate=1.0,
            success_rate=1.0,
        )
        assert isinstance(result, CLEARScore)
        assert result.composite_score > 0.8
        assert result.gate_decision == GateDecision.PASS
        assert len(result.failing_dimensions) == 0

    def test_all_dimensions_scored(self):
        result = self.framework.evaluate()
        assert len(result.dimensions) == 5
        for dim in Dimension:
            assert dim in result.dimensions

    def test_failing_cost(self):
        result = self.framework.evaluate(
            cost_usd=1.5,
            budget_usd=1.0,
        )
        cost_dim = result.dimensions[Dimension.COST]
        assert cost_dim.gate in (GateDecision.WARN, GateDecision.FAIL)

    def test_failing_latency(self):
        result = self.framework.evaluate(
            latency_ms=15000.0,
            target_latency_ms=5000.0,
        )
        lat_dim = result.dimensions[Dimension.LATENCY]
        assert lat_dim.gate in (GateDecision.WARN, GateDecision.FAIL)

    def test_failing_efficacy(self):
        result = self.framework.evaluate(
            correct=1,
            total=10,
            quality_score=0.1,
        )
        eff_dim = result.dimensions[Dimension.EFFICACY]
        assert eff_dim.gate in (GateDecision.WARN, GateDecision.FAIL)

    def test_failing_assurance(self):
        result = self.framework.evaluate(
            safety_pass_rate=0.2,
            compliance_rate=0.1,
            audit_coverage=0.1,
        )
        assert Dimension.ASSURANCE in result.failing_dimensions

    def test_failing_reliability(self):
        result = self.framework.evaluate(
            success_rate=0.1,
            consistency=0.1,
            error_recovery_rate=0.1,
        )
        assert Dimension.RELIABILITY in result.failing_dimensions

    def test_overall_fail_if_any_fails(self):
        result = self.framework.evaluate(
            safety_pass_rate=0.0,
            compliance_rate=0.0,
        )
        assert result.gate_decision == GateDecision.FAIL

    def test_agent_and_stage_stored(self):
        result = self.framework.evaluate(agent_id="agent-1", stage="review")
        assert result.agent_id == "agent-1"
        assert result.stage == "review"

    def test_id_unique(self):
        r1 = self.framework.evaluate()
        r2 = self.framework.evaluate()
        assert r1.id != r2.id

    def test_history_tracked(self):
        self.framework.evaluate()
        self.framework.evaluate()
        assert len(self.framework._history) == 2


class TestCustomWeights:
    def test_custom_weights(self):
        framework = CLEAREvalFramework(
            weights={
                Dimension.COST: 3.0,
                Dimension.LATENCY: 1.0,
                Dimension.EFFICACY: 1.0,
                Dimension.ASSURANCE: 1.0,
                Dimension.RELIABILITY: 1.0,
            },
        )
        result = framework.evaluate(cost_usd=0.0, budget_usd=1.0)
        assert result.composite_score > 0

    def test_custom_thresholds(self):
        framework = CLEAREvalFramework(
            pass_thresholds={d: 0.9 for d in Dimension},
            warn_thresholds={d: 0.7 for d in Dimension},
        )
        result = framework.evaluate(
            correct=7,
            total=10,
        )
        eff = result.dimensions[Dimension.EFFICACY]
        assert eff.gate in (GateDecision.WARN, GateDecision.FAIL)


# ── Trend analysis ───────────────────────────────────────────────────────

class TestTrendAnalysis:
    def test_no_trends_with_one_eval(self):
        fw = CLEAREvalFramework()
        fw.evaluate()
        trends = fw.analyze_trends()
        assert trends == []

    def test_improving_trend(self):
        fw = CLEAREvalFramework()
        # First batch: poor
        for _ in range(5):
            fw.evaluate(correct=3, total=10, success_rate=0.5)
        # Second batch: good
        for _ in range(5):
            fw.evaluate(correct=9, total=10, success_rate=0.95)
        trends = fw.analyze_trends(window=5)
        efficacy_trends = [t for t in trends if t.dimension == Dimension.EFFICACY]
        assert len(efficacy_trends) > 0
        assert efficacy_trends[0].trend == Trend.IMPROVING

    def test_degrading_trend(self):
        fw = CLEAREvalFramework()
        for _ in range(5):
            fw.evaluate(correct=9, total=10, success_rate=0.95)
        for _ in range(5):
            fw.evaluate(correct=3, total=10, success_rate=0.5)
        trends = fw.analyze_trends(window=5)
        efficacy_trends = [t for t in trends if t.dimension == Dimension.EFFICACY]
        assert len(efficacy_trends) > 0
        assert efficacy_trends[0].trend == Trend.DEGRADING

    def test_stable_trend(self):
        fw = CLEAREvalFramework()
        for _ in range(10):
            fw.evaluate(correct=8, total=10, success_rate=0.9)
        trends = fw.analyze_trends(window=5)
        for t in trends:
            assert t.trend == Trend.STABLE


# ── Batch report ─────────────────────────────────────────────────────────

class TestBatchReport:
    def test_empty_report(self):
        fw = CLEAREvalFramework()
        report = fw.batch_report()
        assert isinstance(report, BatchCLEARReport)
        assert report.total_evaluations == 0

    def test_report_with_data(self):
        fw = CLEAREvalFramework()
        fw.evaluate(correct=8, total=10, success_rate=0.9)
        fw.evaluate(correct=9, total=10, success_rate=0.95)
        report = fw.batch_report()
        assert report.total_evaluations == 2
        assert report.avg_composite > 0

    def test_weakest_strongest(self):
        fw = CLEAREvalFramework()
        fw.evaluate(
            cost_usd=0.9,
            budget_usd=1.0,
            correct=9,
            total=10,
            safety_pass_rate=1.0,
            success_rate=0.99,
        )
        report = fw.batch_report()
        assert report.weakest_dimension != report.strongest_dimension

    def test_gate_decision(self):
        fw = CLEAREvalFramework()
        fw.evaluate(correct=9, total=10, success_rate=0.95)
        report = fw.batch_report()
        assert report.gate_decision == GateDecision.PASS

    def test_fail_gate_propagated(self):
        fw = CLEAREvalFramework()
        fw.evaluate(safety_pass_rate=0.0, compliance_rate=0.0)
        report = fw.batch_report()
        assert report.gate_decision == GateDecision.FAIL

    def test_dimension_averages(self):
        fw = CLEAREvalFramework()
        fw.evaluate(correct=8, total=10)
        fw.evaluate(correct=6, total=10)
        report = fw.batch_report()
        for dim in Dimension:
            assert dim in report.dimension_averages
            assert 0 <= report.dimension_averages[dim] <= 1.0
