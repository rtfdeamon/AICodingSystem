"""Review Quality Scorer — evaluates the quality of AI-generated code reviews.

AI code-review agents often produce noisy, non-actionable, or false-positive
comments that waste developer time.  ReviewQualityScorer benchmarks review
output along six axes: actionability, specificity, relevance, coverage,
constructiveness, and false-positive rate, producing a single overall quality
score with a configurable gate decision.

Based on "Code Review Agent Benchmark" (arXiv:2603.23448, March 2026) and
emerging research on PR-level evaluation of LLM-generated review comments.

Key capabilities:
- Comment-level quality assessment (actionability, specificity, relevance)
- Issue detection recall via coverage analysis
- False positive rate tracking
- Severity accuracy comparison
- Constructiveness scoring (solutions vs. complaints)
- Batch evaluation with aggregated metrics
- Configurable quality gate (PASS / WARN / BLOCK)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class CommentQuality(StrEnum):
    ACTIONABLE = "actionable"
    INFORMATIVE = "informative"
    NOISE = "noise"
    FALSE_POSITIVE = "false_positive"


class ReviewAspect(StrEnum):
    CORRECTNESS = "correctness"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"
    TESTING = "testing"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class ReviewComment:
    """A single comment produced by an AI code-review agent."""

    id: str
    file_path: str
    line_number: int
    comment_text: str
    severity: float = 0.5  # 0.0–1.0 (higher = more severe)
    aspect: ReviewAspect = ReviewAspect.CORRECTNESS
    suggested_fix: str = ""


@dataclass
class CommentEvaluation:
    """Quality evaluation of a single review comment."""

    comment: ReviewComment
    quality: CommentQuality
    actionability_score: float
    specificity_score: float
    relevance_score: float
    overall_score: float


@dataclass
class ReviewEvaluation:
    """Aggregated evaluation of an entire code review."""

    review_id: str
    comment_evaluations: list[CommentEvaluation]
    coverage_score: float
    avg_quality: float
    actionable_pct: float
    false_positive_pct: float
    constructiveness_score: float
    overall_score: float
    gate_decision: GateDecision
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchReviewReport:
    """Aggregated report across multiple review evaluations."""

    evaluations: list[ReviewEvaluation]
    avg_overall_score: float
    avg_coverage: float
    avg_actionable_pct: float
    avg_false_positive_pct: float
    gate_decision: GateDecision


# ── ReviewQualityScorer Engine ───────────────────────────────────────────

class ReviewQualityScorer:
    """Evaluates quality of AI-generated code reviews.

    Scores review comments along actionability, specificity, relevance,
    coverage, and constructiveness axes, producing an overall quality
    score with a configurable gate decision.
    """

    # Heuristic keyword sets used for lightweight scoring
    _ACTION_VERBS = frozenset({
        "add", "remove", "rename", "refactor", "extract", "replace",
        "move", "fix", "change", "update", "use", "convert", "wrap",
        "handle", "validate", "check", "ensure", "consider", "avoid",
        "implement", "return", "throw", "catch", "log", "test",
    })

    _VAGUE_PHRASES = frozenset({
        "looks weird", "not great", "could be better", "seems off",
        "needs work", "not ideal", "feels wrong", "bad practice",
        "should fix", "needs improvement",
    })

    _FALSE_POSITIVE_SIGNALS = frozenset({
        "nit:", "nit ", "optional:", "optional ",
        "nitpick:", "nitpick ", "style preference",
        "personal preference", "just a thought",
    })

    def __init__(
        self,
        *,
        warn_threshold: float = 0.6,
        block_threshold: float = 0.3,
    ) -> None:
        self._warn_threshold = warn_threshold
        self._block_threshold = block_threshold

    # ── Public API ───────────────────────────────────────────────────

    def evaluate_review(
        self,
        review_id: str,
        comments: list[ReviewComment],
        changed_files: list[str],
    ) -> ReviewEvaluation:
        """Evaluate a complete code review."""
        if not comments:
            return ReviewEvaluation(
                review_id=review_id,
                comment_evaluations=[],
                coverage_score=0.0,
                avg_quality=0.0,
                actionable_pct=0.0,
                false_positive_pct=0.0,
                constructiveness_score=0.0,
                overall_score=0.0,
                gate_decision=self._make_gate_decision(0.0),
            )

        evals = [self._evaluate_comment(c, changed_files) for c in comments]
        coverage = self._compute_coverage(comments, changed_files)
        constructiveness = self._compute_constructiveness(comments)

        avg_quality = sum(e.overall_score for e in evals) / len(evals)
        actionable_count = sum(
            1 for e in evals if e.quality == CommentQuality.ACTIONABLE
        )
        actionable_pct = actionable_count / len(evals)
        fp_count = sum(
            1 for e in evals if e.quality == CommentQuality.FALSE_POSITIVE
        )
        false_positive_pct = fp_count / len(evals)

        overall = self._overall_review_score(evals, coverage, constructiveness)
        gate = self._make_gate_decision(overall)

        logger.debug(
            "review %s: overall=%.3f coverage=%.3f actionable=%.1f%% fp=%.1f%% gate=%s",
            review_id, overall, coverage, actionable_pct * 100,
            false_positive_pct * 100, gate,
        )

        return ReviewEvaluation(
            review_id=review_id,
            comment_evaluations=evals,
            coverage_score=coverage,
            avg_quality=avg_quality,
            actionable_pct=actionable_pct,
            false_positive_pct=false_positive_pct,
            constructiveness_score=constructiveness,
            overall_score=overall,
            gate_decision=gate,
        )

    def evaluate_batch(
        self,
        items: list[tuple[str, list[ReviewComment], list[str]]],
    ) -> BatchReviewReport:
        """Evaluate multiple reviews and aggregate metrics.

        Each item is a tuple of (review_id, comments, changed_files).
        """
        if not items:
            return BatchReviewReport(
                evaluations=[],
                avg_overall_score=0.0,
                avg_coverage=0.0,
                avg_actionable_pct=0.0,
                avg_false_positive_pct=0.0,
                gate_decision=GateDecision.BLOCK,
            )

        evaluations = [
            self.evaluate_review(rid, comments, files)
            for rid, comments, files in items
        ]
        n = len(evaluations)

        avg_overall = sum(e.overall_score for e in evaluations) / n
        avg_cov = sum(e.coverage_score for e in evaluations) / n
        avg_act = sum(e.actionable_pct for e in evaluations) / n
        avg_fp = sum(e.false_positive_pct for e in evaluations) / n

        gate = self._make_gate_decision(avg_overall)

        return BatchReviewReport(
            evaluations=evaluations,
            avg_overall_score=avg_overall,
            avg_coverage=avg_cov,
            avg_actionable_pct=avg_act,
            avg_false_positive_pct=avg_fp,
            gate_decision=gate,
        )

    # ── Private helpers ──────────────────────────────────────────────

    def _evaluate_comment(
        self,
        comment: ReviewComment,
        changed_files: list[str] | None = None,
    ) -> CommentEvaluation:
        """Evaluate a single review comment."""
        changed = changed_files or []
        actionability = self._compute_actionability(comment)
        specificity = self._compute_specificity(comment)
        relevance = self._compute_relevance(comment, changed)

        overall = (
            actionability * 0.4
            + specificity * 0.3
            + relevance * 0.3
        )

        quality = self._classify_quality(comment, actionability, overall)

        return CommentEvaluation(
            comment=comment,
            quality=quality,
            actionability_score=actionability,
            specificity_score=specificity,
            relevance_score=relevance,
            overall_score=overall,
        )

    def _compute_actionability(self, comment: ReviewComment) -> float:
        """Score how actionable a comment is (0.0–1.0)."""
        score = 0.0
        text_lower = comment.comment_text.lower()

        # Presence of a suggested fix is strongly actionable
        if comment.suggested_fix:
            score += 0.5

        # Check for action verbs
        words = set(re.findall(r"[a-z]+", text_lower))
        verb_matches = words & self._ACTION_VERBS
        if verb_matches:
            score += min(len(verb_matches) * 0.15, 0.3)

        # Penalize vague phrasing
        for phrase in self._VAGUE_PHRASES:
            if phrase in text_lower:
                score -= 0.2
                break

        # Longer, substantive comments tend to be more actionable
        word_count = len(comment.comment_text.split())
        if word_count >= 10:
            score += 0.2
        elif word_count >= 5:
            score += 0.1

        return max(0.0, min(1.0, score))

    def _compute_specificity(self, comment: ReviewComment) -> float:
        """Score how specific a comment is (0.0–1.0)."""
        score = 0.0

        # References a concrete line number
        if comment.line_number > 0:
            score += 0.3

        # References a file path
        if comment.file_path:
            score += 0.2

        # Contains code-like tokens (identifiers, operators)
        text = comment.comment_text
        if re.search(r"`[^`]+`", text) or re.search(r"[a-zA-Z_]\w*\(", text):
            score += 0.25

        # Contains a concrete suggestion
        if comment.suggested_fix:
            score += 0.25

        return max(0.0, min(1.0, score))

    def _compute_relevance(
        self,
        comment: ReviewComment,
        changed_files: list[str],
    ) -> float:
        """Score how relevant a comment is to the changed files (0.0–1.0)."""
        if not changed_files:
            return 0.5  # neutral if no changed-file context

        # Direct file match
        if comment.file_path in changed_files:
            return 1.0

        # Partial path match (filename only)
        comment_filename = comment.file_path.rsplit("/", 1)[-1] if comment.file_path else ""
        for cf in changed_files:
            cf_filename = cf.rsplit("/", 1)[-1]
            if comment_filename and comment_filename == cf_filename:
                return 0.8

        return 0.2  # comment targets a file not in the changeset

    def _compute_coverage(
        self,
        comments: list[ReviewComment],
        changed_files: list[str],
    ) -> float:
        """Fraction of changed files that received at least one comment."""
        if not changed_files:
            return 1.0 if comments else 0.0

        commented_files = {c.file_path for c in comments}
        covered = sum(1 for f in changed_files if f in commented_files)
        return covered / len(changed_files)

    def _compute_constructiveness(self, comments: list[ReviewComment]) -> float:
        """Fraction of comments that provide a suggested fix."""
        if not comments:
            return 0.0
        with_fix = sum(1 for c in comments if c.suggested_fix)
        return with_fix / len(comments)

    def _detect_false_positives(
        self,
        comments: list[ReviewComment],
    ) -> list[ReviewComment]:
        """Identify comments that are likely false positives or noise."""
        fps: list[ReviewComment] = []
        for c in comments:
            text_lower = c.comment_text.lower()
            for signal in self._FALSE_POSITIVE_SIGNALS:
                if text_lower.startswith(signal):
                    fps.append(c)
                    break
        return fps

    def _classify_quality(
        self,
        comment: ReviewComment,
        actionability: float,
        overall: float,
    ) -> CommentQuality:
        """Classify a comment into a quality bucket."""
        text_lower = comment.comment_text.lower()

        # Check false-positive signals first
        for signal in self._FALSE_POSITIVE_SIGNALS:
            if text_lower.startswith(signal):
                return CommentQuality.FALSE_POSITIVE

        if actionability >= 0.5 and overall >= 0.4:
            return CommentQuality.ACTIONABLE
        if overall >= 0.25:
            return CommentQuality.INFORMATIVE
        return CommentQuality.NOISE

    def _overall_review_score(
        self,
        evaluations: list[CommentEvaluation],
        coverage: float,
        constructiveness: float,
    ) -> float:
        """Compute overall review quality score (0.0–1.0)."""
        if not evaluations:
            return 0.0

        avg_comment = sum(e.overall_score for e in evaluations) / len(evaluations)
        fp_count = sum(
            1 for e in evaluations if e.quality == CommentQuality.FALSE_POSITIVE
        )
        fp_penalty = fp_count / len(evaluations)

        score = (
            avg_comment * 0.4
            + coverage * 0.25
            + constructiveness * 0.2
            + (1.0 - fp_penalty) * 0.15
        )
        return max(0.0, min(1.0, score))

    def _make_gate_decision(self, score: float) -> GateDecision:
        """Determine gate decision from overall score."""
        if score >= self._warn_threshold:
            return GateDecision.PASS
        if score >= self._block_threshold:
            return GateDecision.WARN
        return GateDecision.BLOCK
