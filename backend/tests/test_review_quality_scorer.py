"""Tests for Review Quality Scorer engine."""

from __future__ import annotations

import pytest

from app.quality.review_quality_scorer import (
    BatchReviewReport,
    CommentQuality,
    GateDecision,
    ReviewAspect,
    ReviewComment,
    ReviewEvaluation,
    ReviewQualityScorer,
)


@pytest.fixture
def scorer() -> ReviewQualityScorer:
    return ReviewQualityScorer()


@pytest.fixture
def changed_files() -> list[str]:
    return ["src/auth.py", "src/models.py", "src/utils.py"]


def _make_comment(
    *,
    id: str = "c1",
    file_path: str = "src/auth.py",
    line_number: int = 42,
    text: str = "Add input validation to prevent SQL injection here.",
    severity: float = 0.7,
    aspect: ReviewAspect = ReviewAspect.SECURITY,
    suggested_fix: str = "",
) -> ReviewComment:
    return ReviewComment(
        id=id,
        file_path=file_path,
        line_number=line_number,
        comment_text=text,
        severity=severity,
        aspect=aspect,
        suggested_fix=suggested_fix,
    )


def _make_actionable_comment(id: str = "a1") -> ReviewComment:
    return _make_comment(
        id=id,
        text="Replace the raw SQL query with a parameterized query to prevent injection.",
        suggested_fix="cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
    )


def _make_noise_comment(id: str = "n1") -> ReviewComment:
    return _make_comment(
        id=id,
        text="Hmm.",
        line_number=0,
        file_path="",
        suggested_fix="",
        severity=0.1,
    )


def _make_false_positive_comment(id: str = "fp1") -> ReviewComment:
    return _make_comment(
        id=id,
        text="nit: consider renaming this variable",
        severity=0.1,
        suggested_fix="",
    )


# ── Enum tests ───────────────────────────────────────────────────────────

class TestEnums:
    def test_comment_quality_values(self) -> None:
        assert CommentQuality.ACTIONABLE == "actionable"
        assert CommentQuality.FALSE_POSITIVE == "false_positive"

    def test_review_aspect_values(self) -> None:
        assert ReviewAspect.CORRECTNESS == "correctness"
        assert ReviewAspect.TESTING == "testing"

    def test_gate_decision_values(self) -> None:
        assert GateDecision.PASS == "pass"
        assert GateDecision.BLOCK == "block"


# ── Comment evaluation tests ─────────────────────────────────────────────

class TestCommentEvaluation:
    def test_actionable_comment_scores_high(self, scorer: ReviewQualityScorer) -> None:
        c = _make_actionable_comment()
        ev = scorer._evaluate_comment(c, ["src/auth.py"])
        assert ev.actionability_score >= 0.5
        assert ev.quality == CommentQuality.ACTIONABLE

    def test_noise_comment_scores_low(self, scorer: ReviewQualityScorer) -> None:
        c = _make_noise_comment()
        ev = scorer._evaluate_comment(c, ["src/auth.py"])
        assert ev.overall_score < 0.4

    def test_false_positive_classified(self, scorer: ReviewQualityScorer) -> None:
        c = _make_false_positive_comment()
        ev = scorer._evaluate_comment(c, ["src/auth.py"])
        assert ev.quality == CommentQuality.FALSE_POSITIVE

    def test_comment_with_suggested_fix_boosts_actionability(
        self, scorer: ReviewQualityScorer,
    ) -> None:
        without_fix = _make_comment(id="nf", suggested_fix="")
        with_fix = _make_comment(id="wf", suggested_fix="use parameterized query")
        ev_without = scorer._evaluate_comment(without_fix, [])
        ev_with = scorer._evaluate_comment(with_fix, [])
        assert ev_with.actionability_score > ev_without.actionability_score

    def test_specificity_with_line_and_file(self, scorer: ReviewQualityScorer) -> None:
        c = _make_comment(line_number=10, file_path="src/auth.py")
        ev = scorer._evaluate_comment(c, ["src/auth.py"])
        assert ev.specificity_score >= 0.5

    def test_specificity_without_line(self, scorer: ReviewQualityScorer) -> None:
        c = _make_comment(line_number=0, file_path="")
        ev = scorer._evaluate_comment(c, [])
        assert ev.specificity_score < 0.5

    def test_relevance_matching_file(self, scorer: ReviewQualityScorer) -> None:
        c = _make_comment(file_path="src/auth.py")
        ev = scorer._evaluate_comment(c, ["src/auth.py"])
        assert ev.relevance_score == 1.0

    def test_relevance_unrelated_file(self, scorer: ReviewQualityScorer) -> None:
        c = _make_comment(file_path="src/unrelated.py")
        ev = scorer._evaluate_comment(c, ["src/auth.py"])
        assert ev.relevance_score < 0.5

    def test_relevance_no_changed_files(self, scorer: ReviewQualityScorer) -> None:
        c = _make_comment()
        ev = scorer._evaluate_comment(c, [])
        assert ev.relevance_score == 0.5

    def test_overall_score_bounded(self, scorer: ReviewQualityScorer) -> None:
        c = _make_comment()
        ev = scorer._evaluate_comment(c, ["src/auth.py"])
        assert 0.0 <= ev.overall_score <= 1.0


# ── Coverage and constructiveness ────────────────────────────────────────

class TestCoverageAndConstructiveness:
    def test_full_coverage(self, scorer: ReviewQualityScorer) -> None:
        comments = [
            _make_comment(id="c1", file_path="src/auth.py"),
            _make_comment(id="c2", file_path="src/models.py"),
            _make_comment(id="c3", file_path="src/utils.py"),
        ]
        cov = scorer._compute_coverage(comments, ["src/auth.py", "src/models.py", "src/utils.py"])
        assert cov == 1.0

    def test_partial_coverage(self, scorer: ReviewQualityScorer) -> None:
        comments = [_make_comment(id="c1", file_path="src/auth.py")]
        cov = scorer._compute_coverage(comments, ["src/auth.py", "src/models.py"])
        assert cov == 0.5

    def test_zero_coverage(self, scorer: ReviewQualityScorer) -> None:
        comments = [_make_comment(id="c1", file_path="src/other.py")]
        cov = scorer._compute_coverage(comments, ["src/auth.py"])
        assert cov == 0.0

    def test_coverage_no_changed_files(self, scorer: ReviewQualityScorer) -> None:
        comments = [_make_comment()]
        cov = scorer._compute_coverage(comments, [])
        assert cov == 1.0

    def test_constructiveness_all_have_fixes(self, scorer: ReviewQualityScorer) -> None:
        comments = [
            _make_comment(id="c1", suggested_fix="fix A"),
            _make_comment(id="c2", suggested_fix="fix B"),
        ]
        assert scorer._compute_constructiveness(comments) == 1.0

    def test_constructiveness_none_have_fixes(self, scorer: ReviewQualityScorer) -> None:
        comments = [_make_comment(id="c1"), _make_comment(id="c2")]
        assert scorer._compute_constructiveness(comments) == 0.0

    def test_constructiveness_empty(self, scorer: ReviewQualityScorer) -> None:
        assert scorer._compute_constructiveness([]) == 0.0


# ── False positive detection ─────────────────────────────────────────────

class TestFalsePositiveDetection:
    def test_detect_nit_comments(self, scorer: ReviewQualityScorer) -> None:
        comments = [
            _make_false_positive_comment("fp1"),
            _make_actionable_comment("a1"),
        ]
        fps = scorer._detect_false_positives(comments)
        assert len(fps) == 1
        assert fps[0].id == "fp1"

    def test_no_false_positives(self, scorer: ReviewQualityScorer) -> None:
        comments = [_make_actionable_comment()]
        fps = scorer._detect_false_positives(comments)
        assert len(fps) == 0


# ── Review evaluation ────────────────────────────────────────────────────

class TestReviewEvaluation:
    def test_evaluate_review_basic(
        self, scorer: ReviewQualityScorer, changed_files: list[str],
    ) -> None:
        comments = [_make_actionable_comment("a1"), _make_actionable_comment("a2")]
        ev = scorer.evaluate_review("r1", comments, changed_files)
        assert isinstance(ev, ReviewEvaluation)
        assert ev.review_id == "r1"
        assert ev.actionable_pct > 0.0
        assert "T" in ev.evaluated_at

    def test_evaluate_review_empty_comments(
        self, scorer: ReviewQualityScorer, changed_files: list[str],
    ) -> None:
        ev = scorer.evaluate_review("r2", [], changed_files)
        assert ev.overall_score == 0.0
        assert ev.gate_decision == GateDecision.BLOCK

    def test_high_quality_review_passes_gate(
        self, scorer: ReviewQualityScorer,
    ) -> None:
        files = ["src/auth.py"]
        comments = [
            ReviewComment(
                id="c1", file_path="src/auth.py", line_number=10,
                comment_text="Replace raw SQL with parameterized query "
                "to prevent injection attacks.",
                severity=0.8, aspect=ReviewAspect.SECURITY,
                suggested_fix="cursor.execute('SELECT * FROM users WHERE id = ?', (uid,))",
            ),
        ]
        ev = scorer.evaluate_review("r3", comments, files)
        assert ev.gate_decision == GateDecision.PASS

    def test_noisy_review_gets_warn_or_block(
        self, scorer: ReviewQualityScorer, changed_files: list[str],
    ) -> None:
        comments = [_make_noise_comment("n1"), _make_noise_comment("n2")]
        ev = scorer.evaluate_review("r4", comments, changed_files)
        assert ev.gate_decision in (GateDecision.WARN, GateDecision.BLOCK)

    def test_false_positive_pct(
        self, scorer: ReviewQualityScorer, changed_files: list[str],
    ) -> None:
        comments = [
            _make_false_positive_comment("fp1"),
            _make_actionable_comment("a1"),
        ]
        ev = scorer.evaluate_review("r5", comments, changed_files)
        assert ev.false_positive_pct == 0.5

    def test_overall_score_bounded(
        self, scorer: ReviewQualityScorer, changed_files: list[str],
    ) -> None:
        comments = [_make_comment()]
        ev = scorer.evaluate_review("r6", comments, changed_files)
        assert 0.0 <= ev.overall_score <= 1.0


# ── Batch evaluation ─────────────────────────────────────────────────────

class TestBatchEvaluation:
    def test_batch_single_item(self, scorer: ReviewQualityScorer) -> None:
        items = [("r1", [_make_actionable_comment()], ["src/auth.py"])]
        report = scorer.evaluate_batch(items)
        assert isinstance(report, BatchReviewReport)
        assert len(report.evaluations) == 1

    def test_batch_multiple_items(self, scorer: ReviewQualityScorer) -> None:
        items = [
            ("r1", [_make_actionable_comment("a1")], ["src/auth.py"]),
            ("r2", [_make_noise_comment("n1")], ["src/models.py"]),
        ]
        report = scorer.evaluate_batch(items)
        assert len(report.evaluations) == 2
        assert 0.0 <= report.avg_overall_score <= 1.0

    def test_batch_empty(self, scorer: ReviewQualityScorer) -> None:
        report = scorer.evaluate_batch([])
        assert report.avg_overall_score == 0.0
        assert report.gate_decision == GateDecision.BLOCK

    def test_batch_aggregates_coverage(self, scorer: ReviewQualityScorer) -> None:
        items = [
            ("r1", [_make_comment(id="c1", file_path="a.py")], ["a.py"]),
            ("r2", [_make_comment(id="c2", file_path="x.py")], ["b.py"]),
        ]
        report = scorer.evaluate_batch(items)
        assert report.avg_coverage == 0.5


# ── Gate decision logic ──────────────────────────────────────────────────

class TestGateDecision:
    def test_high_score_passes(self, scorer: ReviewQualityScorer) -> None:
        assert scorer._make_gate_decision(0.8) == GateDecision.PASS

    def test_medium_score_warns(self, scorer: ReviewQualityScorer) -> None:
        assert scorer._make_gate_decision(0.5) == GateDecision.WARN

    def test_low_score_blocks(self, scorer: ReviewQualityScorer) -> None:
        assert scorer._make_gate_decision(0.2) == GateDecision.BLOCK

    def test_exact_warn_threshold(self, scorer: ReviewQualityScorer) -> None:
        assert scorer._make_gate_decision(0.6) == GateDecision.PASS

    def test_exact_block_threshold(self, scorer: ReviewQualityScorer) -> None:
        assert scorer._make_gate_decision(0.3) == GateDecision.WARN

    def test_custom_thresholds(self) -> None:
        s = ReviewQualityScorer(warn_threshold=0.8, block_threshold=0.5)
        assert s._make_gate_decision(0.9) == GateDecision.PASS
        assert s._make_gate_decision(0.7) == GateDecision.WARN
        assert s._make_gate_decision(0.4) == GateDecision.BLOCK
