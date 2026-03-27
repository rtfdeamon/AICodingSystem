"""Tests for LLM-as-Judge Evaluation."""

from __future__ import annotations

from app.observability.llm_judge import (
    ComparisonResult,
    EvalDimension,
    EvalVerdict,
    LLMJudge,
    ScoringRubric,
)

# ── Helpers ──────────────────────────────────────────────────────────────

def make_judge(**kwargs) -> LLMJudge:
    return LLMJudge(**kwargs)


def high_scores() -> dict[EvalDimension, float]:
    return {
        EvalDimension.CORRECTNESS: 5.0,
        EvalDimension.RELEVANCE: 5.0,
        EvalDimension.SAFETY: 5.0,
        EvalDimension.CODE_STYLE: 5.0,
        EvalDimension.COMPLETENESS: 5.0,
    }


def low_scores() -> dict[EvalDimension, float]:
    return {
        EvalDimension.CORRECTNESS: 1.0,
        EvalDimension.RELEVANCE: 1.0,
        EvalDimension.SAFETY: 1.0,
        EvalDimension.CODE_STYLE: 1.0,
        EvalDimension.COMPLETENESS: 1.0,
    }


def medium_scores() -> dict[EvalDimension, float]:
    return {
        EvalDimension.CORRECTNESS: 3.0,
        EvalDimension.RELEVANCE: 3.0,
        EvalDimension.SAFETY: 4.0,
        EvalDimension.CODE_STYLE: 3.0,
        EvalDimension.COMPLETENESS: 3.0,
    }


# ── Basic Evaluation ─────────────────────────────────────────────────────

class TestBasicEvaluation:
    def test_high_scores_approved(self):
        judge = make_judge()
        result = judge.evaluate("prompt", "output", high_scores())
        assert result.verdict == EvalVerdict.APPROVE
        assert result.weighted_score > 0.9

    def test_low_scores_rejected(self):
        judge = make_judge()
        result = judge.evaluate("prompt", "output", low_scores())
        assert result.verdict in (EvalVerdict.REJECT, EvalVerdict.ESCALATE)

    def test_medium_scores_needs_review(self):
        judge = make_judge()
        result = judge.evaluate("prompt", "output", medium_scores())
        assert result.verdict == EvalVerdict.NEEDS_REVIEW

    def test_safety_escalation(self):
        judge = make_judge(escalate_on_safety_below=3.0)
        scores = high_scores()
        scores[EvalDimension.SAFETY] = 2.0
        result = judge.evaluate("prompt", "output", scores)
        assert result.verdict == EvalVerdict.ESCALATE

    def test_safety_above_threshold_no_escalation(self):
        judge = make_judge(escalate_on_safety_below=3.0)
        scores = high_scores()
        scores[EvalDimension.SAFETY] = 4.0
        result = judge.evaluate("prompt", "output", scores)
        assert result.verdict == EvalVerdict.APPROVE

    def test_scores_clamped_to_range(self):
        judge = make_judge()
        scores = {EvalDimension.CORRECTNESS: 10.0}  # above max 5.0
        result = judge.evaluate("prompt", "output", scores)
        corr = next(s for s in result.scores if s.dimension == EvalDimension.CORRECTNESS)
        assert corr.score == 5.0

    def test_scores_clamped_below_zero(self):
        judge = make_judge()
        scores = {EvalDimension.CORRECTNESS: -5.0}
        result = judge.evaluate("prompt", "output", scores)
        corr = next(s for s in result.scores if s.dimension == EvalDimension.CORRECTNESS)
        assert corr.score == 0.0

    def test_missing_dimension_defaults_to_zero(self):
        judge = make_judge()
        result = judge.evaluate("prompt", "output", {})
        assert all(s.score == 0.0 for s in result.scores)

    def test_hash_generation(self):
        judge = make_judge()
        result = judge.evaluate("prompt", "output", high_scores())
        assert len(result.prompt_hash) == 16
        assert len(result.output_hash) == 16

    def test_metadata_stored(self):
        judge = make_judge()
        result = judge.evaluate("prompt", "output", high_scores(), metadata={"key": "val"})
        assert result.metadata == {"key": "val"}

    def test_evaluated_model_stored(self):
        judge = make_judge()
        result = judge.evaluate("prompt", "output", high_scores(), evaluated_model="claude-3")
        assert result.evaluated_model == "claude-3"


# ── Custom Thresholds ────────────────────────────────────────────────────

class TestThresholds:
    def test_custom_approve_threshold(self):
        judge = make_judge(approve_threshold=0.95)
        # 4/5 = 0.8 weighted -> should NOT approve
        scores = {d: 4.0 for d in EvalDimension}
        scores[EvalDimension.SAFETY] = 4.0  # above escalation
        result = judge.evaluate("p", "o", scores)
        assert result.verdict != EvalVerdict.APPROVE

    def test_custom_reject_threshold(self):
        judge = make_judge(reject_threshold=0.5)
        scores = {d: 1.0 for d in EvalDimension}
        scores[EvalDimension.SAFETY] = 4.0  # avoid escalation
        result = judge.evaluate("p", "o", scores)
        assert result.verdict == EvalVerdict.REJECT


# ── Rubric Management ────────────────────────────────────────────────────

class TestRubrics:
    def test_set_rubric(self):
        judge = make_judge()
        rubric = ScoringRubric(
            dimension=EvalDimension.EFFICIENCY,
            weight=3.0,
            max_score=10.0,
        )
        judge.set_rubric(rubric)
        assert EvalDimension.EFFICIENCY in judge.dimensions

    def test_remove_rubric(self):
        judge = make_judge()
        assert judge.remove_rubric(EvalDimension.CODE_STYLE) is True
        assert EvalDimension.CODE_STYLE not in judge.dimensions

    def test_remove_nonexistent_rubric(self):
        judge = make_judge()
        assert judge.remove_rubric(EvalDimension.EFFICIENCY) is False

    def test_default_dimensions(self):
        judge = make_judge()
        assert EvalDimension.CORRECTNESS in judge.dimensions
        assert EvalDimension.SAFETY in judge.dimensions


# ── Pairwise Evaluation ─────────────────────────────────────────────────

class TestPairwise:
    def test_a_better(self):
        judge = make_judge()
        result = judge.evaluate_pairwise("p", "a", "b", high_scores(), low_scores())
        assert result.result == ComparisonResult.A_BETTER

    def test_b_better(self):
        judge = make_judge()
        result = judge.evaluate_pairwise("p", "a", "b", low_scores(), high_scores())
        assert result.result == ComparisonResult.B_BETTER

    def test_tie(self):
        judge = make_judge()
        result = judge.evaluate_pairwise("p", "a", "b", high_scores(), high_scores())
        assert result.result == ComparisonResult.TIE

    def test_pairwise_history(self):
        judge = make_judge()
        judge.evaluate_pairwise("p", "a", "b", high_scores(), low_scores())
        assert len(judge.pairwise_history) == 1

    def test_pairwise_hashes(self):
        judge = make_judge()
        result = judge.evaluate_pairwise("p", "a", "b", high_scores(), low_scores())
        assert len(result.output_a_hash) == 16
        assert len(result.output_b_hash) == 16
        assert result.output_a_hash != result.output_b_hash


# ── Calibration ──────────────────────────────────────────────────────────

class TestCalibration:
    def test_record_calibration(self):
        judge = make_judge()
        rec = judge.record_calibration(EvalDimension.CORRECTNESS, 4.0, 3.5)
        assert rec.delta == 0.5

    def test_calibration_bias(self):
        judge = make_judge()
        judge.record_calibration(EvalDimension.CORRECTNESS, 4.0, 3.0)
        judge.record_calibration(EvalDimension.CORRECTNESS, 5.0, 4.0)
        bias = judge.calibration_bias(EvalDimension.CORRECTNESS)
        assert bias == 1.0  # judge consistently scores 1 higher

    def test_calibration_bias_none(self):
        judge = make_judge()
        assert judge.calibration_bias(EvalDimension.CORRECTNESS) is None

    def test_calibration_agreement(self):
        judge = make_judge()
        judge.record_calibration(EvalDimension.CORRECTNESS, 4.0, 3.5)  # delta 0.5
        judge.record_calibration(EvalDimension.CORRECTNESS, 4.0, 2.0)  # delta 2.0
        agreement = judge.calibration_agreement(EvalDimension.CORRECTNESS, tolerance=1.0)
        assert agreement == 0.5  # 1 of 2 within tolerance

    def test_calibration_agreement_none(self):
        judge = make_judge()
        assert judge.calibration_agreement(EvalDimension.CORRECTNESS) is None


# ── Analytics ────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_approval_rate(self):
        judge = make_judge()
        judge.evaluate("p", "o1", high_scores())
        judge.evaluate("p", "o2", high_scores())
        judge.evaluate("p", "o3", low_scores())
        rate = judge.approval_rate()
        assert rate is not None
        assert rate > 0.5

    def test_approval_rate_empty(self):
        judge = make_judge()
        assert judge.approval_rate() is None

    def test_avg_score_by_dimension(self):
        judge = make_judge()
        judge.evaluate("p", "o1", high_scores())
        judge.evaluate("p", "o2", low_scores())
        avgs = judge.avg_score_by_dimension()
        assert EvalDimension.CORRECTNESS in avgs
        assert avgs[EvalDimension.CORRECTNESS] == 3.0

    def test_clear_history(self):
        judge = make_judge()
        judge.evaluate("p", "o", high_scores())
        judge.evaluate_pairwise("p", "a", "b", high_scores(), low_scores())
        count = judge.clear_history()
        assert count == 2
        assert len(judge.history) == 0
        assert len(judge.pairwise_history) == 0

    def test_summary(self):
        judge = make_judge()
        judge.evaluate("p", "o", high_scores())
        s = judge.summary()
        assert s["total_evaluations"] == 1
        assert s["judge_model"] == "gpt-4o"
        assert s["avg_weighted_score"] is not None
        assert "verdicts" in s

    def test_summary_empty(self):
        judge = make_judge()
        s = judge.summary()
        assert s["total_evaluations"] == 0
        assert s["avg_weighted_score"] is None
