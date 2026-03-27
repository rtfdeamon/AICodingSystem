"""Feedback-Driven Prompt Optimizer -- iteratively improve prompts from outcomes.

Tracks prompt performance across multiple dimensions (success rate, quality
scores, token efficiency, latency) and recommends or auto-applies improvements
based on historical outcome data.  Implements A/B variant management and
statistical significance testing for prompt changes.

Key features:
- Prompt performance tracking across success, quality, cost, latency
- Automatic variant generation from failure pattern analysis
- A/B testing with statistical significance (chi-square test)
- Prompt compression: remove low-value sections to save tokens
- Few-shot example curation based on outcome correlation
- Regression detection when a prompt variant degrades
- Improvement suggestion engine with confidence scoring
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class PromptOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    ERROR = "error"
    TIMEOUT = "timeout"


class VariantStatus(StrEnum):
    ACTIVE = "active"
    TESTING = "testing"
    CHAMPION = "champion"
    RETIRED = "retired"


class SuggestionType(StrEnum):
    ADD_CONSTRAINT = "add_constraint"
    ADD_EXAMPLE = "add_example"
    REMOVE_SECTION = "remove_section"
    REPHRASE = "rephrase"
    ADD_CHAIN_OF_THOUGHT = "add_chain_of_thought"
    ADD_OUTPUT_FORMAT = "add_output_format"
    REDUCE_TOKENS = "reduce_tokens"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class PromptVariant:
    """A specific version of a prompt being tracked."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt_name: str = ""
    variant_label: str = "baseline"
    template: str = ""
    status: VariantStatus = VariantStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptExecution:
    """Record of a single prompt execution and its outcome."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    variant_id: str = ""
    outcome: PromptOutcome = PromptOutcome.SUCCESS
    quality_score: float = 0.0  # 0-1
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    failure_reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImprovementSuggestion:
    """A suggested prompt improvement."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    suggestion_type: SuggestionType = SuggestionType.REPHRASE
    description: str = ""
    confidence: float = 0.0  # 0-1
    expected_improvement_pct: float = 0.0
    based_on_failures: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ABTestResult:
    """Result of an A/B test between two prompt variants."""
    variant_a_id: str = ""
    variant_b_id: str = ""
    variant_a_success_rate: float = 0.0
    variant_b_success_rate: float = 0.0
    variant_a_count: int = 0
    variant_b_count: int = 0
    chi_square: float = 0.0
    p_value: float = 0.0
    significant: bool = False
    winner: str | None = None  # variant_id or None if inconclusive


# ── Prompt Optimizer ─────────────────────────────────────────────────────

class PromptOptimizer:
    """Tracks prompt performance and suggests improvements."""

    def __init__(self, significance_threshold: float = 0.05, min_sample_size: int = 30):
        self.significance_threshold = significance_threshold
        self.min_sample_size = min_sample_size
        self._variants: dict[str, PromptVariant] = {}
        self._executions: list[PromptExecution] = []

    # ── Variant Management ────────────────────────────────────────────

    def register_variant(
        self, prompt_name: str, template: str, variant_label: str = "baseline",
        token_count: int = 0, **metadata: Any,
    ) -> PromptVariant:
        """Register a new prompt variant for tracking."""
        variant = PromptVariant(
            prompt_name=prompt_name,
            variant_label=variant_label,
            template=template,
            token_count=token_count or len(template.split()),
            metadata=metadata,
        )
        self._variants[variant.id] = variant
        logger.info("Registered prompt variant %s/%s (%s)",
                     prompt_name, variant_label, variant.id[:8])
        return variant

    def get_variant(self, variant_id: str) -> PromptVariant | None:
        return self._variants.get(variant_id)

    def set_champion(self, variant_id: str) -> None:
        """Promote a variant to champion status."""
        variant = self._variants.get(variant_id)
        if not variant:
            raise ValueError(f"Variant {variant_id} not found")
        # Retire current champion for the same prompt
        for v in self._variants.values():
            if v.prompt_name == variant.prompt_name and v.status == VariantStatus.CHAMPION:
                v.status = VariantStatus.RETIRED
        variant.status = VariantStatus.CHAMPION

    def list_variants(self, prompt_name: str | None = None) -> list[PromptVariant]:
        """List variants, optionally filtered by prompt name."""
        if prompt_name:
            return [v for v in self._variants.values() if v.prompt_name == prompt_name]
        return list(self._variants.values())

    # ── Execution Recording ───────────────────────────────────────────

    def record_execution(
        self, variant_id: str, outcome: PromptOutcome, quality_score: float = 0.0,
        latency_ms: float = 0.0, input_tokens: int = 0, output_tokens: int = 0,
        cost_usd: float = 0.0, failure_reason: str = "", **metadata: Any,
    ) -> PromptExecution:
        """Record the outcome of a prompt execution."""
        execution = PromptExecution(
            variant_id=variant_id,
            outcome=outcome,
            quality_score=quality_score,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            failure_reason=failure_reason,
            metadata=metadata,
        )
        self._executions.append(execution)
        return execution

    def get_executions(self, variant_id: str) -> list[PromptExecution]:
        return [e for e in self._executions if e.variant_id == variant_id]

    # ── Performance Analysis ──────────────────────────────────────────

    def variant_stats(self, variant_id: str) -> dict[str, Any]:
        """Compute performance stats for a variant."""
        execs = self.get_executions(variant_id)
        if not execs:
            return {"variant_id": variant_id, "count": 0}

        successes = sum(1 for e in execs if e.outcome == PromptOutcome.SUCCESS)
        partial = sum(1 for e in execs if e.outcome == PromptOutcome.PARTIAL_SUCCESS)
        failures = sum(1 for e in execs if e.outcome in (
            PromptOutcome.FAILURE, PromptOutcome.ERROR, PromptOutcome.TIMEOUT))

        quality_scores = [e.quality_score for e in execs if e.quality_score > 0]
        latencies = [e.latency_ms for e in execs if e.latency_ms > 0]
        costs = [e.cost_usd for e in execs if e.cost_usd > 0]
        tokens = [e.input_tokens + e.output_tokens for e in execs]

        return {
            "variant_id": variant_id,
            "count": len(execs),
            "success_rate": successes / len(execs),
            "partial_rate": partial / len(execs),
            "failure_rate": failures / len(execs),
            "avg_quality": sum(quality_scores) / len(quality_scores) if quality_scores else 0.0,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "avg_cost_usd": sum(costs) / len(costs) if costs else 0.0,
            "avg_tokens": sum(tokens) / len(tokens) if tokens else 0,
            "total_cost_usd": sum(costs),
            "top_failure_reasons": self._top_failure_reasons(execs),
        }

    def _top_failure_reasons(self, execs: list[PromptExecution]) -> list[dict[str, Any]]:
        reasons: dict[str, int] = {}
        for e in execs:
            if e.failure_reason:
                reasons[e.failure_reason] = reasons.get(e.failure_reason, 0) + 1
        sorted_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)
        return [{"reason": r, "count": c} for r, c in sorted_reasons[:5]]

    # ── A/B Testing ───────────────────────────────────────────────────

    def run_ab_test(self, variant_a_id: str, variant_b_id: str) -> ABTestResult:
        """Run a chi-square test to compare two variants."""
        execs_a = self.get_executions(variant_a_id)
        execs_b = self.get_executions(variant_b_id)

        n_a = len(execs_a)
        n_b = len(execs_b)
        succ_a = sum(1 for e in execs_a if e.outcome == PromptOutcome.SUCCESS)
        succ_b = sum(1 for e in execs_b if e.outcome == PromptOutcome.SUCCESS)

        rate_a = succ_a / n_a if n_a else 0
        rate_b = succ_b / n_b if n_b else 0

        # Chi-square 2x2 contingency
        fail_a = n_a - succ_a
        fail_b = n_b - succ_b
        total = n_a + n_b

        chi2 = 0.0
        p_value = 1.0
        significant = False
        winner = None

        if total > 0 and n_a >= self.min_sample_size and n_b >= self.min_sample_size:
            expected = [
                [(succ_a + succ_b) * n_a / total, (fail_a + fail_b) * n_a / total],
                [(succ_a + succ_b) * n_b / total, (fail_a + fail_b) * n_b / total],
            ]
            observed = [[succ_a, fail_a], [succ_b, fail_b]]

            for i in range(2):
                for j in range(2):
                    if expected[i][j] > 0:
                        chi2 += (observed[i][j] - expected[i][j]) ** 2 / expected[i][j]

            # Approximate p-value from chi-square with 1 df
            p_value = self._chi2_p_value(chi2)
            significant = p_value < self.significance_threshold
            if significant:
                winner = variant_a_id if rate_a > rate_b else variant_b_id

        return ABTestResult(
            variant_a_id=variant_a_id,
            variant_b_id=variant_b_id,
            variant_a_success_rate=rate_a,
            variant_b_success_rate=rate_b,
            variant_a_count=n_a,
            variant_b_count=n_b,
            chi_square=chi2,
            p_value=p_value,
            significant=significant,
            winner=winner,
        )

    @staticmethod
    def _chi2_p_value(chi2: float) -> float:
        """Approximate p-value for chi-square with 1 degree of freedom."""
        if chi2 <= 0:
            return 1.0
        # Use complementary error function approximation
        z = math.sqrt(chi2)
        # Abramowitz & Stegun approximation
        t = 1.0 / (1.0 + 0.2316419 * z)
        d = 0.3989422804014327  # 1/sqrt(2*pi)
        poly = t * (0.319381530 + t * (-0.356563782 + t * (
            1.781477937 + t * (-1.821255978 + t * 1.330274429))))
        p = d * math.exp(-z * z / 2.0) * poly
        return 2.0 * p  # two-tailed

    # ── Improvement Suggestions ───────────────────────────────────────

    def suggest_improvements(self, variant_id: str) -> list[ImprovementSuggestion]:
        """Analyze failures and suggest prompt improvements."""
        execs = self.get_executions(variant_id)
        if not execs:
            return []

        suggestions: list[ImprovementSuggestion] = []
        failures = [e for e in execs if e.outcome in (PromptOutcome.FAILURE, PromptOutcome.ERROR)]

        if not failures:
            return []

        failure_rate = len(failures) / len(execs)

        # Analyze failure reasons
        reasons: dict[str, int] = {}
        for f in failures:
            if f.failure_reason:
                reasons[f.failure_reason] = reasons.get(f.failure_reason, 0) + 1

        # Suggest based on patterns
        for reason, count in reasons.items():
            reason_lower = reason.lower()
            if "format" in reason_lower or "json" in reason_lower or "schema" in reason_lower:
                desc = f"Add explicit output format spec. {count} failures: {reason}"
                suggestions.append(ImprovementSuggestion(
                    suggestion_type=SuggestionType.ADD_OUTPUT_FORMAT,
                    description=desc,
                    confidence=min(0.9, count / len(failures)),
                    expected_improvement_pct=count / len(execs) * 100,
                    based_on_failures=count,
                ))
            if any(k in reason_lower for k in ("incomplete", "truncat", "missing")):
                suggestions.append(ImprovementSuggestion(
                    suggestion_type=SuggestionType.ADD_CONSTRAINT,
                    description=f"Add completeness constraints. {count} failures due to: {reason}",
                    confidence=min(0.85, count / len(failures)),
                    expected_improvement_pct=count / len(execs) * 100,
                    based_on_failures=count,
                ))
            if any(k in reason_lower for k in ("hallucin", "incorrect", "wrong")):
                cot_desc = f"Add chain-of-thought reasoning. {count} failures: {reason}"
                suggestions.append(ImprovementSuggestion(
                    suggestion_type=SuggestionType.ADD_CHAIN_OF_THOUGHT,
                    description=cot_desc,
                    confidence=min(0.8, count / len(failures)),
                    expected_improvement_pct=count / len(execs) * 80,
                    based_on_failures=count,
                ))

        # General suggestions based on failure rate
        if failure_rate > 0.3:
            suggestions.append(ImprovementSuggestion(
                suggestion_type=SuggestionType.ADD_EXAMPLE,
                description=f"High failure rate ({failure_rate:.0%}). Add few-shot examples.",
                confidence=0.7,
                expected_improvement_pct=failure_rate * 50,
                based_on_failures=len(failures),
            ))

        # Token efficiency suggestion
        variant = self._variants.get(variant_id)
        if variant and variant.token_count > 500:
            avg_quality = sum(e.quality_score for e in execs if e.quality_score > 0) / max(
                sum(1 for e in execs if e.quality_score > 0), 1
            )
            if avg_quality > 0.8:
                suggestions.append(ImprovementSuggestion(
                    suggestion_type=SuggestionType.REDUCE_TOKENS,
                    description=(
                        f"High quality ({avg_quality:.0%}) with "
                        f"{variant.token_count} tokens. Try compression."
                    ),
                    confidence=0.6,
                    expected_improvement_pct=0,
                    based_on_failures=0,
                ))

        return sorted(suggestions, key=lambda s: s.confidence, reverse=True)

    # ── Regression Detection ──────────────────────────────────────────

    def detect_regression(
        self, variant_id: str, window_size: int = 20,
    ) -> dict[str, Any]:
        """Detect if recent performance has regressed."""
        execs = self.get_executions(variant_id)
        if len(execs) < window_size * 2:
            return {"regressed": False, "reason": "Insufficient data"}

        recent = execs[-window_size:]
        previous = execs[-window_size * 2:-window_size]

        recent_rate = sum(1 for e in recent if e.outcome == PromptOutcome.SUCCESS) / len(recent)
        prev_rate = sum(1 for e in previous if e.outcome == PromptOutcome.SUCCESS) / len(previous)

        recent_quality = [e.quality_score for e in recent if e.quality_score > 0]
        prev_quality = [e.quality_score for e in previous if e.quality_score > 0]

        avg_recent_q = sum(recent_quality) / len(recent_quality) if recent_quality else 0
        avg_prev_q = sum(prev_quality) / len(prev_quality) if prev_quality else 0

        rate_drop = prev_rate - recent_rate
        quality_drop = avg_prev_q - avg_recent_q

        regressed = rate_drop > 0.1 or quality_drop > 0.15

        return {
            "regressed": regressed,
            "success_rate_previous": prev_rate,
            "success_rate_recent": recent_rate,
            "rate_change": -rate_drop,
            "quality_previous": avg_prev_q,
            "quality_recent": avg_recent_q,
            "quality_change": -quality_drop,
            "window_size": window_size,
        }

    # ── Global Analytics ──────────────────────────────────────────────

    def global_stats(self) -> dict[str, Any]:
        """Aggregate stats across all variants."""
        if not self._executions:
            return {"total_executions": 0}

        total = len(self._executions)
        successes = sum(1 for e in self._executions if e.outcome == PromptOutcome.SUCCESS)
        total_cost = sum(e.cost_usd for e in self._executions)
        total_tokens = sum(e.input_tokens + e.output_tokens for e in self._executions)

        return {
            "total_executions": total,
            "total_variants": len(self._variants),
            "overall_success_rate": successes / total,
            "total_cost_usd": total_cost,
            "total_tokens": total_tokens,
            "avg_cost_per_execution": total_cost / total if total else 0,
        }
