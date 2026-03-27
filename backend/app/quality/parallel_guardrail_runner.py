"""Parallel Guardrail Runner — execute multiple guardrail checks concurrently
to minimize latency stacking.

Traditional sequential guardrail pipelines suffer from additive latency:
if toxicity detection takes 80ms, PII scanning 60ms, and injection detection
70ms, the total is 210ms. Running them in parallel reduces this to ~80ms
(the longest single check).

Based on Authority Partners "AI Agent Guardrails: Production Guide for 2026"
and Galileo AI parallelized runtime check architecture. Also informed by
Guardrails AI framework design (guardrails-ai/guardrails on GitHub).

Key capabilities:
- Parallel execution of independent guardrail checks
- Short-circuit on critical failures (stop early on blocked results)
- Per-guardrail timeout with graceful degradation
- Weighted aggregation of guardrail results
- Quality gate: configurable pass/warn/block thresholds
- Guardrail registration with priority and category
- Execution metrics: latency per guardrail, total wall-clock time
- Batch evaluation across multiple inputs
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class GuardrailVerdict(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"
    ERROR = "error"
    TIMEOUT = "timeout"


class GuardrailCategory(StrEnum):
    TOXICITY = "toxicity"
    PII = "pii"
    INJECTION = "injection"
    HALLUCINATION = "hallucination"
    OFF_TOPIC = "off_topic"
    FORMAT = "format"
    COMPLIANCE = "compliance"
    SAFETY = "safety"
    CUSTOM = "custom"


class AggregateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class GuardrailCheck:
    """A single guardrail check function registration."""

    name: str
    category: GuardrailCategory
    check_fn: Callable[[str, dict[str, Any]], GuardrailResult]
    weight: float = 1.0
    timeout_ms: int = 5000
    critical: bool = False  # If True, BLOCK result triggers short-circuit
    enabled: bool = True


@dataclass
class GuardrailResult:
    """Result from a single guardrail check."""

    guardrail_name: str
    category: str
    verdict: GuardrailVerdict
    score: float  # 0-1, higher = more problematic
    details: str = ""
    latency_ms: float = 0.0


@dataclass
class ParallelGuardrailReport:
    """Aggregated report from parallel guardrail execution."""

    id: str
    results: list[GuardrailResult]
    decision: AggregateDecision
    total_checks: int
    passed: int
    warned: int
    blocked: int
    errors: int
    timeouts: int
    aggregate_score: float  # 0-1
    wall_clock_ms: float
    sequential_estimate_ms: float  # What it would have cost sequentially
    speedup_factor: float
    short_circuited: bool = False
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchGuardrailReport:
    """Report across multiple inputs."""

    reports: list[ParallelGuardrailReport]
    total_inputs: int
    avg_score: float
    total_blocked: int
    decision: AggregateDecision


# ── Built-in guardrail checks ──────────────────────────────────────────

def _check_pii(text: str, _ctx: dict[str, Any]) -> GuardrailResult:
    """Check for PII patterns."""
    import re
    patterns = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "credit_card": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
    }
    found: list[str] = []
    for name, pat in patterns.items():
        if re.search(pat, text):
            found.append(name)

    if found:
        score = min(len(found) * 0.3, 1.0)
        is_critical = "ssn" in found or "credit_card" in found
        verdict = GuardrailVerdict.BLOCK if is_critical else GuardrailVerdict.WARN
        return GuardrailResult(
            guardrail_name="pii_scanner",
            category=GuardrailCategory.PII,
            verdict=verdict,
            score=score,
            details=f"PII detected: {', '.join(found)}",
        )
    return GuardrailResult(
        guardrail_name="pii_scanner",
        category=GuardrailCategory.PII,
        verdict=GuardrailVerdict.PASS,
        score=0.0,
    )


def _check_injection(text: str, _ctx: dict[str, Any]) -> GuardrailResult:
    """Check for prompt injection patterns."""
    import re
    injection_patterns = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"you\s+are\s+now\s+(a|an)\s+",
        r"system\s*:\s*",
        r"<\|im_start\|>",
        r"\[INST\]",
        r"jailbreak",
        r"do\s+anything\s+now",
        r"override\s+(safety|guardrail|filter)",
    ]
    matches: list[str] = []
    for pat in injection_patterns:
        if re.search(pat, text, re.IGNORECASE):
            matches.append(pat)

    if matches:
        score = min(len(matches) * 0.4, 1.0)
        return GuardrailResult(
            guardrail_name="injection_detector",
            category=GuardrailCategory.INJECTION,
            verdict=GuardrailVerdict.BLOCK,
            score=score,
            details=f"Injection patterns detected: {len(matches)} match(es)",
        )
    return GuardrailResult(
        guardrail_name="injection_detector",
        category=GuardrailCategory.INJECTION,
        verdict=GuardrailVerdict.PASS,
        score=0.0,
    )


def _check_toxicity(text: str, _ctx: dict[str, Any]) -> GuardrailResult:
    """Check for toxic language patterns."""
    import re
    toxic_indicators = [
        r"\b(hate|kill|attack|destroy|harm)\b.*\b(people|person|group|race)\b",
        r"\b(racist|sexist|homophobic|xenophobic)\b",
        r"\bslur\b",
    ]
    found = 0
    for pat in toxic_indicators:
        if re.search(pat, text, re.IGNORECASE):
            found += 1

    if found:
        score = min(found * 0.5, 1.0)
        return GuardrailResult(
            guardrail_name="toxicity_detector",
            category=GuardrailCategory.TOXICITY,
            verdict=GuardrailVerdict.BLOCK if found >= 2 else GuardrailVerdict.WARN,
            score=score,
            details=f"Toxic content indicators: {found}",
        )
    return GuardrailResult(
        guardrail_name="toxicity_detector",
        category=GuardrailCategory.TOXICITY,
        verdict=GuardrailVerdict.PASS,
        score=0.0,
    )


def _check_format(text: str, ctx: dict[str, Any]) -> GuardrailResult:
    """Check output format compliance."""
    expected_format = ctx.get("expected_format")
    if not expected_format:
        return GuardrailResult(
            guardrail_name="format_checker",
            category=GuardrailCategory.FORMAT,
            verdict=GuardrailVerdict.PASS,
            score=0.0,
        )

    import json
    if expected_format == "json":
        try:
            json.loads(text)
            return GuardrailResult(
                guardrail_name="format_checker",
                category=GuardrailCategory.FORMAT,
                verdict=GuardrailVerdict.PASS,
                score=0.0,
            )
        except (json.JSONDecodeError, ValueError):
            return GuardrailResult(
                guardrail_name="format_checker",
                category=GuardrailCategory.FORMAT,
                verdict=GuardrailVerdict.WARN,
                score=0.5,
                details="Expected JSON but output is not valid JSON",
            )

    return GuardrailResult(
        guardrail_name="format_checker",
        category=GuardrailCategory.FORMAT,
        verdict=GuardrailVerdict.PASS,
        score=0.0,
    )


# ── Main class ──────────────────────────────────────────────────────────

class ParallelGuardrailRunner:
    """Execute multiple guardrail checks in parallel.

    Registers guardrail check functions and runs them concurrently,
    aggregating results with weighted scoring and short-circuit support.
    """

    def __init__(
        self,
        max_workers: int = 8,
        block_threshold: float = 0.6,
        warn_threshold: float = 0.3,
        default_timeout_ms: int = 5000,
        include_builtins: bool = True,
    ) -> None:
        self.max_workers = max_workers
        self.block_threshold = block_threshold
        self.warn_threshold = warn_threshold
        self.default_timeout_ms = default_timeout_ms
        self._guardrails: list[GuardrailCheck] = []
        self._history: list[ParallelGuardrailReport] = []

        if include_builtins:
            self._register_builtins()

    def _register_builtins(self) -> None:
        """Register built-in guardrail checks."""
        self.register(GuardrailCheck(
            name="pii_scanner",
            category=GuardrailCategory.PII,
            check_fn=_check_pii,
            weight=1.2,
            critical=True,
        ))
        self.register(GuardrailCheck(
            name="injection_detector",
            category=GuardrailCategory.INJECTION,
            check_fn=_check_injection,
            weight=1.5,
            critical=True,
        ))
        self.register(GuardrailCheck(
            name="toxicity_detector",
            category=GuardrailCategory.TOXICITY,
            check_fn=_check_toxicity,
            weight=1.0,
        ))
        self.register(GuardrailCheck(
            name="format_checker",
            category=GuardrailCategory.FORMAT,
            check_fn=_check_format,
            weight=0.5,
        ))

    def register(self, check: GuardrailCheck) -> None:
        """Register a guardrail check."""
        self._guardrails.append(check)

    def unregister(self, name: str) -> bool:
        """Remove a guardrail by name."""
        before = len(self._guardrails)
        self._guardrails = [g for g in self._guardrails if g.name != name]
        return len(self._guardrails) < before

    @property
    def registered_guardrails(self) -> list[str]:
        return [g.name for g in self._guardrails if g.enabled]

    # ── Single check execution ──────────────────────────────────────────

    def _run_single(
        self,
        check: GuardrailCheck,
        text: str,
        context: dict[str, Any],
    ) -> GuardrailResult:
        """Run a single guardrail check with timing."""
        start = time.monotonic()
        try:
            result = check.check_fn(text, context)
            result.latency_ms = round((time.monotonic() - start) * 1000, 2)
            return result
        except Exception as exc:
            latency = round((time.monotonic() - start) * 1000, 2)
            logger.warning("Guardrail %s failed: %s", check.name, exc)
            return GuardrailResult(
                guardrail_name=check.name,
                category=check.category,
                verdict=GuardrailVerdict.ERROR,
                score=0.0,
                details=f"Error: {exc!s}",
                latency_ms=latency,
            )

    # ── Parallel execution ──────────────────────────────────────────────

    def run(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> ParallelGuardrailReport:
        """Run all enabled guardrails in parallel."""
        ctx = context or {}
        enabled = [g for g in self._guardrails if g.enabled]

        if not enabled:
            return ParallelGuardrailReport(
                id=uuid.uuid4().hex[:12],
                results=[],
                decision=AggregateDecision.PASS,
                total_checks=0,
                passed=0,
                warned=0,
                blocked=0,
                errors=0,
                timeouts=0,
                aggregate_score=0.0,
                wall_clock_ms=0.0,
                sequential_estimate_ms=0.0,
                speedup_factor=1.0,
            )

        results: list[GuardrailResult] = []
        short_circuited = False
        wall_start = time.monotonic()

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(enabled))) as pool:
            futures = {
                pool.submit(self._run_single, check, text, ctx): check
                for check in enabled
            }
            for future in as_completed(futures):
                check = futures[future]
                try:
                    timeout_s = check.timeout_ms / 1000
                    result = future.result(timeout=timeout_s)
                except TimeoutError:
                    result = GuardrailResult(
                        guardrail_name=check.name,
                        category=check.category,
                        verdict=GuardrailVerdict.TIMEOUT,
                        score=0.0,
                        details="Check timed out",
                        latency_ms=check.timeout_ms,
                    )
                except Exception as exc:
                    result = GuardrailResult(
                        guardrail_name=check.name,
                        category=check.category,
                        verdict=GuardrailVerdict.ERROR,
                        score=0.0,
                        details=f"Unexpected error: {exc!s}",
                    )

                results.append(result)

                # Short-circuit on critical block
                if check.critical and result.verdict == GuardrailVerdict.BLOCK:
                    short_circuited = True
                    # Cancel remaining futures
                    for f in futures:
                        f.cancel()
                    break

        wall_ms = round((time.monotonic() - wall_start) * 1000, 2)
        sequential_ms = round(sum(r.latency_ms for r in results), 2)
        speedup = sequential_ms / wall_ms if wall_ms > 0 else 1.0

        report = self._aggregate(results, wall_ms, sequential_ms, speedup, short_circuited)
        self._history.append(report)
        return report

    # ── Synchronous (non-parallel) for testing ──────────────────────────

    def run_sync(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> ParallelGuardrailReport:
        """Run all guardrails sequentially (useful for testing)."""
        ctx = context or {}
        enabled = [g for g in self._guardrails if g.enabled]
        results: list[GuardrailResult] = []
        short_circuited = False

        wall_start = time.monotonic()
        for check in enabled:
            result = self._run_single(check, text, ctx)
            results.append(result)
            if check.critical and result.verdict == GuardrailVerdict.BLOCK:
                short_circuited = True
                break

        wall_ms = round((time.monotonic() - wall_start) * 1000, 2)
        sequential_ms = wall_ms  # same for sync

        report = self._aggregate(results, wall_ms, sequential_ms, 1.0, short_circuited)
        self._history.append(report)
        return report

    # ── Aggregation ─────────────────────────────────────────────────────

    def _aggregate(
        self,
        results: list[GuardrailResult],
        wall_ms: float,
        sequential_ms: float,
        speedup: float,
        short_circuited: bool,
    ) -> ParallelGuardrailReport:
        """Aggregate results into a report."""
        passed = warned = blocked = errors = timeouts = 0
        for r in results:
            if r.verdict == GuardrailVerdict.PASS:
                passed += 1
            elif r.verdict == GuardrailVerdict.WARN:
                warned += 1
            elif r.verdict == GuardrailVerdict.BLOCK:
                blocked += 1
            elif r.verdict == GuardrailVerdict.ERROR:
                errors += 1
            elif r.verdict == GuardrailVerdict.TIMEOUT:
                timeouts += 1

        # Weighted score
        total_weight = 0.0
        weighted_score = 0.0
        for r in results:
            check = next(
                (g for g in self._guardrails if g.name == r.guardrail_name),
                None,
            )
            w = check.weight if check else 1.0
            total_weight += w
            weighted_score += r.score * w

        aggregate_score = round(weighted_score / total_weight, 4) if total_weight > 0 else 0.0

        # Decision
        if blocked > 0 or aggregate_score >= self.block_threshold:
            decision = AggregateDecision.BLOCK
        elif warned > 0 or aggregate_score >= self.warn_threshold:
            decision = AggregateDecision.WARN
        else:
            decision = AggregateDecision.PASS

        return ParallelGuardrailReport(
            id=uuid.uuid4().hex[:12],
            results=results,
            decision=decision,
            total_checks=len(results),
            passed=passed,
            warned=warned,
            blocked=blocked,
            errors=errors,
            timeouts=timeouts,
            aggregate_score=aggregate_score,
            wall_clock_ms=wall_ms,
            sequential_estimate_ms=sequential_ms,
            speedup_factor=round(speedup, 2),
            short_circuited=short_circuited,
        )

    # ── Batch ───────────────────────────────────────────────────────────

    def batch_run(
        self,
        inputs: list[tuple[str, dict[str, Any] | None]],
    ) -> BatchGuardrailReport:
        """Run guardrails on multiple inputs."""
        reports = [self.run_sync(text, ctx) for text, ctx in inputs]
        avg_score = (
            sum(r.aggregate_score for r in reports) / len(reports)
            if reports else 0.0
        )
        total_blocked = sum(r.blocked for r in reports)

        decisions = [r.decision for r in reports]
        if AggregateDecision.BLOCK in decisions:
            decision = AggregateDecision.BLOCK
        elif AggregateDecision.WARN in decisions:
            decision = AggregateDecision.WARN
        else:
            decision = AggregateDecision.PASS

        return BatchGuardrailReport(
            reports=reports,
            total_inputs=len(reports),
            avg_score=round(avg_score, 4),
            total_blocked=total_blocked,
            decision=decision,
        )

    @property
    def history(self) -> list[ParallelGuardrailReport]:
        return list(self._history)
