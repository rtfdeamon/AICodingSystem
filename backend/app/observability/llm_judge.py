"""LLM-as-Judge Evaluation -- secondary model scoring of primary outputs.

Uses a separate LLM to evaluate the quality, correctness, safety, and
relevance of outputs from the primary coding model.  Supports multiple
evaluation dimensions with rubric-based scoring and calibration.

Key features:
- Multi-dimension evaluation (correctness, relevance, safety, style, completeness)
- Configurable rubrics with scoring criteria per dimension
- Pairwise comparison for A/B evaluations
- Score calibration and inter-rater reliability tracking
- Evaluation history and aggregate analytics
- Threshold-based auto-approval and escalation
"""

from __future__ import annotations

import hashlib
import logging
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class EvalDimension(StrEnum):
    CORRECTNESS = "correctness"
    RELEVANCE = "relevance"
    SAFETY = "safety"
    CODE_STYLE = "code_style"
    COMPLETENESS = "completeness"
    EFFICIENCY = "efficiency"
    SECURITY = "security"
    CLARITY = "clarity"


class EvalVerdict(StrEnum):
    APPROVE = "approve"
    NEEDS_REVIEW = "needs_review"
    REJECT = "reject"
    ESCALATE = "escalate"


class ComparisonResult(StrEnum):
    A_BETTER = "a_better"
    B_BETTER = "b_better"
    TIE = "tie"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class ScoringRubric:
    """Defines how to score a specific evaluation dimension."""
    dimension: EvalDimension
    weight: float = 1.0
    min_score: float = 0.0
    max_score: float = 5.0
    criteria: dict[int, str] = field(default_factory=dict)
    # e.g. {1: "Completely wrong", 3: "Partially correct", 5: "Perfect"}


@dataclass
class DimensionScore:
    """Score for a single evaluation dimension."""
    dimension: EvalDimension
    score: float
    max_score: float = 5.0
    rationale: str = ""
    confidence: float = 1.0  # 0-1


@dataclass
class EvalResult:
    """Complete evaluation result from judge model."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt_hash: str = ""
    output_hash: str = ""
    scores: list[DimensionScore] = field(default_factory=list)
    weighted_score: float = 0.0
    verdict: EvalVerdict = EvalVerdict.NEEDS_REVIEW
    explanation: str = ""
    judge_model: str = ""
    evaluated_model: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PairwiseEval:
    """Result of comparing two model outputs."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt_hash: str = ""
    result: ComparisonResult = ComparisonResult.TIE
    output_a_hash: str = ""
    output_b_hash: str = ""
    scores_a: list[DimensionScore] = field(default_factory=list)
    scores_b: list[DimensionScore] = field(default_factory=list)
    rationale: str = ""
    judge_model: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class CalibrationRecord:
    """Tracks judge calibration against human reviewers."""
    dimension: EvalDimension
    judge_score: float
    human_score: float
    delta: float = 0.0


# ── Judge ────────────────────────────────────────────────────────────────

class LLMJudge:
    """Evaluates LLM outputs using a secondary model with rubric-based scoring."""

    DEFAULT_RUBRICS: dict[EvalDimension, ScoringRubric] = {
        EvalDimension.CORRECTNESS: ScoringRubric(
            dimension=EvalDimension.CORRECTNESS,
            weight=2.0,
            criteria={
                1: "Completely incorrect or non-functional code",
                2: "Major errors, partially works",
                3: "Mostly correct with minor issues",
                4: "Correct with edge case gaps",
                5: "Fully correct, handles edge cases",
            },
        ),
        EvalDimension.RELEVANCE: ScoringRubric(
            dimension=EvalDimension.RELEVANCE,
            weight=1.5,
            criteria={
                1: "Unrelated to the prompt",
                3: "Partially addresses the request",
                5: "Directly and fully addresses the request",
            },
        ),
        EvalDimension.SAFETY: ScoringRubric(
            dimension=EvalDimension.SAFETY,
            weight=2.0,
            criteria={
                1: "Contains security vulnerabilities or unsafe patterns",
                3: "No obvious issues but lacks safety best practices",
                5: "Follows security best practices throughout",
            },
        ),
        EvalDimension.CODE_STYLE: ScoringRubric(
            dimension=EvalDimension.CODE_STYLE,
            weight=0.5,
            criteria={
                1: "Unreadable, no structure",
                3: "Readable but inconsistent style",
                5: "Clean, idiomatic, well-structured",
            },
        ),
        EvalDimension.COMPLETENESS: ScoringRubric(
            dimension=EvalDimension.COMPLETENESS,
            weight=1.0,
            criteria={
                1: "Missing most requirements",
                3: "Covers main requirements, misses some",
                5: "All requirements addressed with extras",
            },
        ),
    }

    def __init__(
        self,
        *,
        judge_model: str = "gpt-4o",
        rubrics: dict[EvalDimension, ScoringRubric] | None = None,
        approve_threshold: float = 0.75,
        reject_threshold: float = 0.4,
        escalate_on_safety_below: float = 3.0,
    ) -> None:
        self._judge_model = judge_model
        self._rubrics = rubrics or dict(self.DEFAULT_RUBRICS)
        self._approve_threshold = approve_threshold
        self._reject_threshold = reject_threshold
        self._escalate_safety = escalate_on_safety_below
        self._history: list[EvalResult] = []
        self._pairwise_history: list[PairwiseEval] = []
        self._calibration: list[CalibrationRecord] = []

    # ── Configuration ────────────────────────────────────────────────

    def set_rubric(self, rubric: ScoringRubric) -> None:
        self._rubrics[rubric.dimension] = rubric

    def remove_rubric(self, dimension: EvalDimension) -> bool:
        return self._rubrics.pop(dimension, None) is not None

    @property
    def dimensions(self) -> list[EvalDimension]:
        return list(self._rubrics.keys())

    # ── Evaluation ───────────────────────────────────────────────────

    def evaluate(
        self,
        prompt: str,
        output: str,
        dimension_scores: dict[EvalDimension, float],
        *,
        evaluated_model: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> EvalResult:
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        output_hash = hashlib.sha256(output.encode()).hexdigest()[:16]

        scores: list[DimensionScore] = []
        for dim, rubric in self._rubrics.items():
            raw_score = dimension_scores.get(dim, 0.0)
            clamped = max(rubric.min_score, min(rubric.max_score, raw_score))
            scores.append(DimensionScore(
                dimension=dim,
                score=clamped,
                max_score=rubric.max_score,
            ))

        weighted = self._compute_weighted(scores)
        verdict = self._determine_verdict(scores, weighted)

        result = EvalResult(
            prompt_hash=prompt_hash,
            output_hash=output_hash,
            scores=scores,
            weighted_score=round(weighted, 4),
            verdict=verdict,
            judge_model=self._judge_model,
            evaluated_model=evaluated_model,
            metadata=metadata or {},
        )
        self._history.append(result)
        return result

    def evaluate_pairwise(
        self,
        prompt: str,
        output_a: str,
        output_b: str,
        scores_a: dict[EvalDimension, float],
        scores_b: dict[EvalDimension, float],
    ) -> PairwiseEval:
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        hash_a = hashlib.sha256(output_a.encode()).hexdigest()[:16]
        hash_b = hashlib.sha256(output_b.encode()).hexdigest()[:16]

        dim_scores_a = self._build_scores(scores_a)
        dim_scores_b = self._build_scores(scores_b)

        weighted_a = self._compute_weighted(dim_scores_a)
        weighted_b = self._compute_weighted(dim_scores_b)

        if abs(weighted_a - weighted_b) < 0.05:
            result = ComparisonResult.TIE
        elif weighted_a > weighted_b:
            result = ComparisonResult.A_BETTER
        else:
            result = ComparisonResult.B_BETTER

        pw = PairwiseEval(
            prompt_hash=prompt_hash,
            result=result,
            output_a_hash=hash_a,
            output_b_hash=hash_b,
            scores_a=dim_scores_a,
            scores_b=dim_scores_b,
            judge_model=self._judge_model,
        )
        self._pairwise_history.append(pw)
        return pw

    # ── Calibration ──────────────────────────────────────────────────

    def record_calibration(
        self,
        dimension: EvalDimension,
        judge_score: float,
        human_score: float,
    ) -> CalibrationRecord:
        rec = CalibrationRecord(
            dimension=dimension,
            judge_score=judge_score,
            human_score=human_score,
            delta=round(judge_score - human_score, 4),
        )
        self._calibration.append(rec)
        return rec

    def calibration_bias(self, dimension: EvalDimension) -> float | None:
        relevant = [c for c in self._calibration if c.dimension == dimension]
        if not relevant:
            return None
        return round(statistics.mean(c.delta for c in relevant), 4)

    def calibration_agreement(
        self, dimension: EvalDimension, tolerance: float = 1.0,
    ) -> float | None:
        relevant = [c for c in self._calibration if c.dimension == dimension]
        if not relevant:
            return None
        agreed = sum(1 for c in relevant if abs(c.delta) <= tolerance)
        return round(agreed / len(relevant), 4)

    # ── Internal ─────────────────────────────────────────────────────

    def _build_scores(
        self, raw: dict[EvalDimension, float]
    ) -> list[DimensionScore]:
        scores: list[DimensionScore] = []
        for dim, rubric in self._rubrics.items():
            val = raw.get(dim, 0.0)
            clamped = max(rubric.min_score, min(rubric.max_score, val))
            scores.append(DimensionScore(
                dimension=dim,
                score=clamped,
                max_score=rubric.max_score,
            ))
        return scores

    def _compute_weighted(self, scores: list[DimensionScore]) -> float:
        total_weight = 0.0
        weighted_sum = 0.0
        for ds in scores:
            rubric = self._rubrics.get(ds.dimension)
            w = rubric.weight if rubric else 1.0
            normalised = ds.score / ds.max_score if ds.max_score else 0.0
            weighted_sum += normalised * w
            total_weight += w
        if total_weight <= 0:
            return 0.0
        return weighted_sum / total_weight

    def _determine_verdict(
        self,
        scores: list[DimensionScore],
        weighted: float,
    ) -> EvalVerdict:
        # Safety escalation
        for ds in scores:
            if ds.dimension == EvalDimension.SAFETY and ds.score < self._escalate_safety:
                    return EvalVerdict.ESCALATE

        if weighted >= self._approve_threshold:
            return EvalVerdict.APPROVE
        if weighted <= self._reject_threshold:
            return EvalVerdict.REJECT
        return EvalVerdict.NEEDS_REVIEW

    # ── Analytics ────────────────────────────────────────────────────

    @property
    def history(self) -> list[EvalResult]:
        return list(self._history)

    @property
    def pairwise_history(self) -> list[PairwiseEval]:
        return list(self._pairwise_history)

    def clear_history(self) -> int:
        count = len(self._history) + len(self._pairwise_history)
        self._history.clear()
        self._pairwise_history.clear()
        return count

    def approval_rate(self) -> float | None:
        if not self._history:
            return None
        approved = sum(1 for r in self._history if r.verdict == EvalVerdict.APPROVE)
        return round(approved / len(self._history), 4)

    def avg_score_by_dimension(self) -> dict[EvalDimension, float]:
        dim_scores: dict[EvalDimension, list[float]] = {}
        for result in self._history:
            for ds in result.scores:
                dim_scores.setdefault(ds.dimension, []).append(ds.score)
        return {
            dim: round(statistics.mean(vals), 4)
            for dim, vals in dim_scores.items()
            if vals
        }

    def summary(self) -> dict[str, Any]:
        total = len(self._history)
        verdicts: dict[str, int] = {}
        for r in self._history:
            verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
        return {
            "total_evaluations": total,
            "verdicts": verdicts,
            "approval_rate": self.approval_rate(),
            "avg_weighted_score": (
                round(statistics.mean(r.weighted_score for r in self._history), 4)
                if self._history else None
            ),
            "avg_by_dimension": self.avg_score_by_dimension(),
            "pairwise_evaluations": len(self._pairwise_history),
            "calibration_records": len(self._calibration),
            "judge_model": self._judge_model,
        }
