"""Tests for Feedback-Driven Prompt Optimizer."""

from __future__ import annotations

import pytest

from app.quality.prompt_optimizer import (
    PromptOptimizer,
    PromptOutcome,
    SuggestionType,
    VariantStatus,
)

# ── Variant Management ────────────────────────────────────────────────────

class TestVariantManagement:
    def test_register_variant(self):
        opt = PromptOptimizer()
        v = opt.register_variant("code_review", "Review this code: {code}")
        assert v.prompt_name == "code_review"
        assert v.variant_label == "baseline"
        assert v.status == VariantStatus.ACTIVE

    def test_get_variant(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        found = opt.get_variant(v.id)
        assert found is not None
        assert found.id == v.id

    def test_get_missing_variant(self):
        opt = PromptOptimizer()
        assert opt.get_variant("missing") is None

    def test_set_champion(self):
        opt = PromptOptimizer()
        v1 = opt.register_variant("test", "v1", variant_label="v1")
        v2 = opt.register_variant("test", "v2", variant_label="v2")
        opt.set_champion(v1.id)
        assert opt.get_variant(v1.id).status == VariantStatus.CHAMPION
        opt.set_champion(v2.id)
        assert opt.get_variant(v1.id).status == VariantStatus.RETIRED
        assert opt.get_variant(v2.id).status == VariantStatus.CHAMPION

    def test_set_champion_nonexistent(self):
        opt = PromptOptimizer()
        with pytest.raises(ValueError):
            opt.set_champion("missing")

    def test_list_variants(self):
        opt = PromptOptimizer()
        opt.register_variant("a", "template_a")
        opt.register_variant("b", "template_b")
        opt.register_variant("a", "template_a2", variant_label="v2")
        assert len(opt.list_variants()) == 3
        assert len(opt.list_variants("a")) == 2

    def test_token_count_auto(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "one two three four")
        assert v.token_count == 4

    def test_token_count_explicit(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template", token_count=100)
        assert v.token_count == 100


# ── Execution Recording ──────────────────────────────────────────────────

class TestExecutionRecording:
    def test_record_execution(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        ex = opt.record_execution(v.id, PromptOutcome.SUCCESS, quality_score=0.9)
        assert ex.variant_id == v.id
        assert ex.outcome == PromptOutcome.SUCCESS

    def test_get_executions(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        opt.record_execution(v.id, PromptOutcome.SUCCESS)
        opt.record_execution(v.id, PromptOutcome.FAILURE)
        execs = opt.get_executions(v.id)
        assert len(execs) == 2

    def test_get_executions_empty(self):
        opt = PromptOptimizer()
        assert opt.get_executions("missing") == []


# ── Variant Stats ─────────────────────────────────────────────────────────

class TestVariantStats:
    def test_basic_stats(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        for _ in range(7):
            opt.record_execution(v.id, PromptOutcome.SUCCESS, quality_score=0.8, latency_ms=100)
        for _ in range(3):
            opt.record_execution(v.id, PromptOutcome.FAILURE, failure_reason="format error")
        stats = opt.variant_stats(v.id)
        assert stats["count"] == 10
        assert stats["success_rate"] == 0.7
        assert stats["failure_rate"] == 0.3

    def test_empty_stats(self):
        opt = PromptOptimizer()
        stats = opt.variant_stats("missing")
        assert stats["count"] == 0

    def test_top_failure_reasons(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        for _ in range(5):
            opt.record_execution(v.id, PromptOutcome.FAILURE, failure_reason="json parse error")
        for _ in range(3):
            opt.record_execution(v.id, PromptOutcome.FAILURE, failure_reason="incomplete output")
        stats = opt.variant_stats(v.id)
        reasons = stats["top_failure_reasons"]
        assert reasons[0]["reason"] == "json parse error"
        assert reasons[0]["count"] == 5


# ── A/B Testing ───────────────────────────────────────────────────────────

class TestABTesting:
    def test_significant_difference(self):
        opt = PromptOptimizer(min_sample_size=30)
        va = opt.register_variant("test", "v_a", variant_label="a")
        vb = opt.register_variant("test", "v_b", variant_label="b")
        # A: 90% success, B: 50% success
        for _ in range(27):
            opt.record_execution(va.id, PromptOutcome.SUCCESS)
        for _ in range(3):
            opt.record_execution(va.id, PromptOutcome.FAILURE)
        for _ in range(15):
            opt.record_execution(vb.id, PromptOutcome.SUCCESS)
        for _ in range(15):
            opt.record_execution(vb.id, PromptOutcome.FAILURE)
        result = opt.run_ab_test(va.id, vb.id)
        assert result.significant is True
        assert result.winner == va.id

    def test_insufficient_samples(self):
        opt = PromptOptimizer(min_sample_size=30)
        va = opt.register_variant("test", "v_a")
        vb = opt.register_variant("test", "v_b")
        for _ in range(5):
            opt.record_execution(va.id, PromptOutcome.SUCCESS)
            opt.record_execution(vb.id, PromptOutcome.FAILURE)
        result = opt.run_ab_test(va.id, vb.id)
        assert result.significant is False

    def test_similar_performance(self):
        opt = PromptOptimizer(min_sample_size=30)
        va = opt.register_variant("test", "v_a")
        vb = opt.register_variant("test", "v_b")
        for _ in range(25):
            opt.record_execution(va.id, PromptOutcome.SUCCESS)
            opt.record_execution(vb.id, PromptOutcome.SUCCESS)
        for _ in range(5):
            opt.record_execution(va.id, PromptOutcome.FAILURE)
            opt.record_execution(vb.id, PromptOutcome.FAILURE)
        result = opt.run_ab_test(va.id, vb.id)
        assert result.significant is False

    def test_chi2_p_value_zero(self):
        assert PromptOptimizer._chi2_p_value(0) == 1.0


# ── Improvement Suggestions ──────────────────────────────────────────────

class TestImprovementSuggestions:
    def test_format_failure_suggests_output_format(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        for _ in range(5):
            opt.record_execution(v.id, PromptOutcome.FAILURE, failure_reason="json format error")
        suggestions = opt.suggest_improvements(v.id)
        types = [s.suggestion_type for s in suggestions]
        assert SuggestionType.ADD_OUTPUT_FORMAT in types

    def test_hallucination_suggests_cot(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        for _ in range(5):
            opt.record_execution(
                v.id, PromptOutcome.FAILURE, failure_reason="hallucinated API call",
            )
        suggestions = opt.suggest_improvements(v.id)
        types = [s.suggestion_type for s in suggestions]
        assert SuggestionType.ADD_CHAIN_OF_THOUGHT in types

    def test_incomplete_suggests_constraint(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        for _ in range(5):
            opt.record_execution(v.id, PromptOutcome.FAILURE, failure_reason="incomplete response")
        suggestions = opt.suggest_improvements(v.id)
        types = [s.suggestion_type for s in suggestions]
        assert SuggestionType.ADD_CONSTRAINT in types

    def test_high_failure_suggests_examples(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        for _ in range(4):
            opt.record_execution(v.id, PromptOutcome.FAILURE, failure_reason="various errors")
        for _ in range(6):
            opt.record_execution(v.id, PromptOutcome.SUCCESS)
        suggestions = opt.suggest_improvements(v.id)
        types = [s.suggestion_type for s in suggestions]
        assert SuggestionType.ADD_EXAMPLE in types

    def test_no_suggestions_on_success(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        for _ in range(10):
            opt.record_execution(v.id, PromptOutcome.SUCCESS)
        suggestions = opt.suggest_improvements(v.id)
        assert len(suggestions) == 0

    def test_no_suggestions_no_executions(self):
        opt = PromptOptimizer()
        assert opt.suggest_improvements("missing") == []

    def test_token_reduction_suggestion(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", " ".join(["word"] * 600), token_count=600)
        for _ in range(5):
            opt.record_execution(v.id, PromptOutcome.SUCCESS, quality_score=0.9)
        for _ in range(5):
            opt.record_execution(v.id, PromptOutcome.FAILURE, failure_reason="timeout")
        suggestions = opt.suggest_improvements(v.id)
        types = [s.suggestion_type for s in suggestions]
        assert SuggestionType.REDUCE_TOKENS in types


# ── Regression Detection ─────────────────────────────────────────────────

class TestRegressionDetection:
    def test_detect_regression(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        # 20 good, then 20 bad
        for _ in range(20):
            opt.record_execution(v.id, PromptOutcome.SUCCESS)
        for _ in range(20):
            opt.record_execution(v.id, PromptOutcome.FAILURE)
        result = opt.detect_regression(v.id, window_size=20)
        assert result["regressed"] is True

    def test_no_regression(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        for _ in range(40):
            opt.record_execution(v.id, PromptOutcome.SUCCESS)
        result = opt.detect_regression(v.id, window_size=20)
        assert result["regressed"] is False

    def test_insufficient_data(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        for _ in range(5):
            opt.record_execution(v.id, PromptOutcome.SUCCESS)
        result = opt.detect_regression(v.id, window_size=20)
        assert result["regressed"] is False
        assert "Insufficient" in result["reason"]


# ── Global Stats ──────────────────────────────────────────────────────────

class TestGlobalStats:
    def test_global_stats(self):
        opt = PromptOptimizer()
        v = opt.register_variant("test", "template")
        opt.record_execution(v.id, PromptOutcome.SUCCESS, cost_usd=0.01)
        opt.record_execution(v.id, PromptOutcome.FAILURE, cost_usd=0.02)
        stats = opt.global_stats()
        assert stats["total_executions"] == 2
        assert stats["overall_success_rate"] == 0.5
        assert stats["total_cost_usd"] == pytest.approx(0.03)

    def test_global_stats_empty(self):
        opt = PromptOptimizer()
        stats = opt.global_stats()
        assert stats["total_executions"] == 0
