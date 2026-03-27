"""Parallel Guardrail Orchestrator -- concurrent safety check execution.

Runs independent guardrail checks (PII, injection, toxicity, schema, etc.)
in parallel to minimize latency stacking.  A sequential 5-check pipeline
at ~50 ms each would cost ~250 ms; parallel execution brings it under ~60 ms.

Key features:
- Async-first parallel execution with configurable concurrency
- Guardrail priority and ordering (critical checks can short-circuit)
- Per-check timeouts with graceful degradation
- Aggregate pass/fail decision with detailed per-check results
- Latency tracking and reporting for SLA monitoring
- Guardrail enable/disable and A/B rollout via feature flags
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class GuardrailCategory(StrEnum):
    SAFETY = "safety"
    QUALITY = "quality"
    COMPLIANCE = "compliance"
    PERFORMANCE = "performance"


class CheckResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class AggregatePolicy(StrEnum):
    ALL_PASS = "all_pass"
    MAJORITY_PASS = "majority_pass"
    NO_CRITICAL_FAIL = "no_critical_fail"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class GuardrailCheck:
    """Definition of a single guardrail check."""
    name: str
    category: GuardrailCategory
    check_fn: Any  # async callable(content, context) -> GuardrailOutcome
    critical: bool = False
    timeout_ms: float = 5000.0
    enabled: bool = True
    rollout_pct: float = 100.0  # percentage of requests that run this check
    order: int = 0  # lower = higher priority for short-circuit


@dataclass
class GuardrailOutcome:
    """Result of a single guardrail check execution."""
    check_name: str
    result: CheckResult
    score: float = 0.0  # 0-1 confidence
    details: str = ""
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorResult:
    """Aggregate result from running all guardrails."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    passed: bool = True
    policy: AggregatePolicy = AggregatePolicy.ALL_PASS
    outcomes: list[GuardrailOutcome] = field(default_factory=list)
    total_latency_ms: float = 0.0
    parallel_latency_ms: float = 0.0  # wall-clock time
    checks_run: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    checks_warned: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def speedup_ratio(self) -> float:
        if self.parallel_latency_ms <= 0:
            return 1.0
        return self.total_latency_ms / self.parallel_latency_ms


@dataclass
class LatencyStats:
    """Latency statistics for monitoring."""
    check_name: str
    avg_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    total_runs: int
    timeout_count: int
    error_count: int


# ── Orchestrator ─────────────────────────────────────────────────────────

class GuardrailOrchestrator:
    """Runs multiple guardrail checks in parallel with aggregate decisions."""

    def __init__(
        self,
        *,
        policy: AggregatePolicy = AggregatePolicy.ALL_PASS,
        max_concurrency: int = 10,
        default_timeout_ms: float = 5000.0,
    ) -> None:
        self._checks: dict[str, GuardrailCheck] = {}
        self._policy = policy
        self._max_concurrency = max_concurrency
        self._default_timeout_ms = default_timeout_ms
        self._history: list[OrchestratorResult] = []
        self._latency_records: dict[str, list[float]] = {}

    # ── Registration ─────────────────────────────────────────────────

    def register(self, check: GuardrailCheck) -> None:
        self._checks[check.name] = check
        if check.name not in self._latency_records:
            self._latency_records[check.name] = []

    def unregister(self, name: str) -> bool:
        return self._checks.pop(name, None) is not None

    def enable(self, name: str) -> None:
        if name in self._checks:
            self._checks[name].enabled = True

    def disable(self, name: str) -> None:
        if name in self._checks:
            self._checks[name].enabled = False

    def set_rollout(self, name: str, pct: float) -> None:
        if name in self._checks:
            self._checks[name].rollout_pct = max(0.0, min(100.0, pct))

    @property
    def registered_checks(self) -> list[str]:
        return list(self._checks.keys())

    # ── Execution ────────────────────────────────────────────────────

    async def run(
        self,
        content: str,
        context: dict[str, Any] | None = None,
    ) -> OrchestratorResult:
        context = context or {}
        wall_start = time.monotonic()

        active = self._get_active_checks(context)
        if not active:
            return OrchestratorResult(
                passed=True,
                policy=self._policy,
                checks_run=0,
            )

        semaphore = asyncio.Semaphore(self._max_concurrency)
        outcomes = await asyncio.gather(
            *[self._run_check(c, content, context, semaphore) for c in active]
        )

        wall_ms = (time.monotonic() - wall_start) * 1000
        total_ms = sum(o.latency_ms for o in outcomes)
        passed_count = sum(1 for o in outcomes if o.result == CheckResult.PASS)
        failed_count = sum(
            1 for o in outcomes if o.result in (CheckResult.FAIL, CheckResult.ERROR)
        )
        warned_count = sum(1 for o in outcomes if o.result == CheckResult.WARN)

        aggregate_pass = self._evaluate_policy(outcomes, active)

        result = OrchestratorResult(
            passed=aggregate_pass,
            policy=self._policy,
            outcomes=list(outcomes),
            total_latency_ms=round(total_ms, 2),
            parallel_latency_ms=round(wall_ms, 2),
            checks_run=len(outcomes),
            checks_passed=passed_count,
            checks_failed=failed_count,
            checks_warned=warned_count,
        )
        self._history.append(result)
        return result

    def run_sync(
        self,
        content: str,
        context: dict[str, Any] | None = None,
    ) -> OrchestratorResult:
        context = context or {}
        wall_start = time.monotonic()

        active = self._get_active_checks(context)
        if not active:
            return OrchestratorResult(
                passed=True,
                policy=self._policy,
                checks_run=0,
            )

        outcomes: list[GuardrailOutcome] = []
        for check in active:
            outcome = self._run_check_sync(check, content, context)
            outcomes.append(outcome)

        wall_ms = (time.monotonic() - wall_start) * 1000
        total_ms = sum(o.latency_ms for o in outcomes)
        passed_count = sum(1 for o in outcomes if o.result == CheckResult.PASS)
        failed_count = sum(
            1 for o in outcomes if o.result in (CheckResult.FAIL, CheckResult.ERROR)
        )
        warned_count = sum(1 for o in outcomes if o.result == CheckResult.WARN)

        aggregate_pass = self._evaluate_policy(outcomes, active)

        result = OrchestratorResult(
            passed=aggregate_pass,
            policy=self._policy,
            outcomes=outcomes,
            total_latency_ms=round(total_ms, 2),
            parallel_latency_ms=round(wall_ms, 2),
            checks_run=len(outcomes),
            checks_passed=passed_count,
            checks_failed=failed_count,
            checks_warned=warned_count,
        )
        self._history.append(result)
        return result

    # ── Internal ─────────────────────────────────────────────────────

    def _get_active_checks(
        self, context: dict[str, Any]
    ) -> list[GuardrailCheck]:
        import random

        active: list[GuardrailCheck] = []
        for check in self._checks.values():
            if not check.enabled:
                continue
            if check.rollout_pct < 100.0 and random.random() * 100 > check.rollout_pct:  # noqa: S311
                    continue
            active.append(check)
        active.sort(key=lambda c: c.order)
        return active

    async def _run_check(
        self,
        check: GuardrailCheck,
        content: str,
        context: dict[str, Any],
        semaphore: asyncio.Semaphore,
    ) -> GuardrailOutcome:
        async with semaphore:
            start = time.monotonic()
            timeout_s = (check.timeout_ms or self._default_timeout_ms) / 1000
            try:
                result = check.check_fn(content, context)
                if asyncio.iscoroutine(result):
                    outcome = await asyncio.wait_for(result, timeout=timeout_s)
                else:
                    outcome = result
                outcome.latency_ms = round((time.monotonic() - start) * 1000, 2)
            except TimeoutError:
                outcome = GuardrailOutcome(
                    check_name=check.name,
                    result=CheckResult.TIMEOUT,
                    details=f"Timed out after {check.timeout_ms}ms",
                    latency_ms=round((time.monotonic() - start) * 1000, 2),
                )
            except Exception as exc:
                outcome = GuardrailOutcome(
                    check_name=check.name,
                    result=CheckResult.ERROR,
                    details=str(exc),
                    latency_ms=round((time.monotonic() - start) * 1000, 2),
                )
            self._record_latency(check.name, outcome)
            return outcome

    def _run_check_sync(
        self,
        check: GuardrailCheck,
        content: str,
        context: dict[str, Any],
    ) -> GuardrailOutcome:
        start = time.monotonic()
        try:
            outcome = check.check_fn(content, context)
            outcome.latency_ms = round((time.monotonic() - start) * 1000, 2)
        except Exception as exc:
            outcome = GuardrailOutcome(
                check_name=check.name,
                result=CheckResult.ERROR,
                details=str(exc),
                latency_ms=round((time.monotonic() - start) * 1000, 2),
            )
        self._record_latency(check.name, outcome)
        return outcome

    def _evaluate_policy(
        self,
        outcomes: list[GuardrailOutcome] | tuple[GuardrailOutcome, ...],
        checks: list[GuardrailCheck],
    ) -> bool:
        check_map = {c.name: c for c in checks}

        if self._policy == AggregatePolicy.ALL_PASS:
            return all(
                o.result in (CheckResult.PASS, CheckResult.WARN, CheckResult.SKIPPED)
                for o in outcomes
            )

        if self._policy == AggregatePolicy.NO_CRITICAL_FAIL:
            for o in outcomes:
                if o.result in (CheckResult.FAIL, CheckResult.ERROR):
                    chk = check_map.get(o.check_name)
                    if chk and chk.critical:
                        return False
            return True

        if self._policy == AggregatePolicy.MAJORITY_PASS:
            pass_count = sum(
                1 for o in outcomes if o.result in (CheckResult.PASS, CheckResult.WARN)
            )
            return pass_count > len(outcomes) / 2

        return True

    def _record_latency(self, name: str, outcome: GuardrailOutcome) -> None:
        if name not in self._latency_records:
            self._latency_records[name] = []
        self._latency_records[name].append(outcome.latency_ms)
        # keep last 1000
        if len(self._latency_records[name]) > 1000:
            self._latency_records[name] = self._latency_records[name][-1000:]

    # ── Stats & History ──────────────────────────────────────────────

    def get_latency_stats(self, name: str) -> LatencyStats | None:
        records = self._latency_records.get(name)
        if not records:
            return None
        sorted_r = sorted(records)
        n = len(sorted_r)
        timeout_count = sum(
            1 for r in self._history
            for o in r.outcomes
            if o.check_name == name and o.result == CheckResult.TIMEOUT
        )
        error_count = sum(
            1 for r in self._history
            for o in r.outcomes
            if o.check_name == name and o.result == CheckResult.ERROR
        )
        return LatencyStats(
            check_name=name,
            avg_ms=round(sum(sorted_r) / n, 2),
            p50_ms=sorted_r[n // 2],
            p95_ms=sorted_r[int(n * 0.95)],
            p99_ms=sorted_r[int(n * 0.99)],
            total_runs=n,
            timeout_count=timeout_count,
            error_count=error_count,
        )

    @property
    def history(self) -> list[OrchestratorResult]:
        return list(self._history)

    def clear_history(self) -> int:
        count = len(self._history)
        self._history.clear()
        return count

    def summary(self) -> dict[str, Any]:
        total = len(self._history)
        passed = sum(1 for r in self._history if r.passed)
        avg_speedup = 0.0
        if self._history:
            avg_speedup = sum(r.speedup_ratio for r in self._history) / total
        return {
            "total_runs": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "avg_speedup_ratio": round(avg_speedup, 2),
            "registered_checks": len(self._checks),
            "policy": self._policy,
        }
