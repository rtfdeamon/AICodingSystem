"""Tests for Parallel Guardrail Orchestrator."""

from __future__ import annotations

import asyncio

import pytest

from app.quality.guardrail_orchestrator import (
    AggregatePolicy,
    CheckResult,
    GuardrailCategory,
    GuardrailCheck,
    GuardrailOrchestrator,
    GuardrailOutcome,
    OrchestratorResult,
)

# ── Helpers ──────────────────────────────────────────────────────────────

def make_pass_check(name: str = "pass_check", critical: bool = False):
    def fn(content, ctx):
        return GuardrailOutcome(
            check_name=name, result=CheckResult.PASS, score=1.0,
        )
    return GuardrailCheck(
        name=name, category=GuardrailCategory.SAFETY,
        check_fn=fn, critical=critical,
    )


def make_fail_check(name: str = "fail_check", critical: bool = False):
    def fn(content, ctx):
        return GuardrailOutcome(
            check_name=name, result=CheckResult.FAIL,
            score=0.0, details="Failed",
        )
    return GuardrailCheck(
        name=name, category=GuardrailCategory.SAFETY,
        check_fn=fn, critical=critical,
    )


def make_warn_check(name: str = "warn_check"):
    def fn(content, ctx):
        return GuardrailOutcome(check_name=name, result=CheckResult.WARN, score=0.5)
    return GuardrailCheck(name=name, category=GuardrailCategory.QUALITY, check_fn=fn)


def make_error_check(name: str = "error_check"):
    def fn(content, ctx):
        raise ValueError("Boom")
    return GuardrailCheck(name=name, category=GuardrailCategory.SAFETY, check_fn=fn)


def make_slow_async_check(name: str = "slow_check", delay: float = 0.1):
    async def fn(content, ctx):
        await asyncio.sleep(delay)
        return GuardrailOutcome(
            check_name=name, result=CheckResult.PASS, score=1.0,
        )
    return GuardrailCheck(
        name=name, category=GuardrailCategory.QUALITY,
        check_fn=fn, timeout_ms=5000,
    )


def make_timeout_check(name: str = "timeout_check"):
    async def fn(content, ctx):
        await asyncio.sleep(10)
        return GuardrailOutcome(check_name=name, result=CheckResult.PASS)
    return GuardrailCheck(name=name, category=GuardrailCategory.SAFETY, check_fn=fn, timeout_ms=50)


# ── Registration ─────────────────────────────────────────────────────────

class TestRegistration:
    def test_register_check(self):
        orch = GuardrailOrchestrator()
        orch.register(make_pass_check("chk1"))
        assert "chk1" in orch.registered_checks

    def test_unregister_check(self):
        orch = GuardrailOrchestrator()
        orch.register(make_pass_check("chk1"))
        assert orch.unregister("chk1") is True
        assert "chk1" not in orch.registered_checks

    def test_unregister_nonexistent(self):
        orch = GuardrailOrchestrator()
        assert orch.unregister("nope") is False

    def test_enable_disable(self):
        orch = GuardrailOrchestrator()
        chk = make_pass_check("chk1")
        orch.register(chk)
        orch.disable("chk1")
        assert chk.enabled is False
        orch.enable("chk1")
        assert chk.enabled is True

    def test_set_rollout(self):
        orch = GuardrailOrchestrator()
        chk = make_pass_check("chk1")
        orch.register(chk)
        orch.set_rollout("chk1", 50.0)
        assert chk.rollout_pct == 50.0

    def test_set_rollout_clamped(self):
        orch = GuardrailOrchestrator()
        chk = make_pass_check("chk1")
        orch.register(chk)
        orch.set_rollout("chk1", 150.0)
        assert chk.rollout_pct == 100.0
        orch.set_rollout("chk1", -10.0)
        assert chk.rollout_pct == 0.0


# ── Sync Execution ───────────────────────────────────────────────────────

class TestSyncExecution:
    def test_all_pass(self):
        orch = GuardrailOrchestrator()
        orch.register(make_pass_check("c1"))
        orch.register(make_pass_check("c2"))
        result = orch.run_sync("hello")
        assert result.passed is True
        assert result.checks_run == 2
        assert result.checks_passed == 2

    def test_one_fail_blocks(self):
        orch = GuardrailOrchestrator(policy=AggregatePolicy.ALL_PASS)
        orch.register(make_pass_check("c1"))
        orch.register(make_fail_check("c2"))
        result = orch.run_sync("hello")
        assert result.passed is False
        assert result.checks_failed == 1

    def test_warn_passes_all_pass_policy(self):
        orch = GuardrailOrchestrator(policy=AggregatePolicy.ALL_PASS)
        orch.register(make_pass_check("c1"))
        orch.register(make_warn_check("c2"))
        result = orch.run_sync("hello")
        assert result.passed is True
        assert result.checks_warned == 1

    def test_no_critical_fail_policy(self):
        orch = GuardrailOrchestrator(policy=AggregatePolicy.NO_CRITICAL_FAIL)
        orch.register(make_fail_check("non_crit", critical=False))
        orch.register(make_pass_check("c2"))
        result = orch.run_sync("hello")
        assert result.passed is True

    def test_critical_fail_blocks(self):
        orch = GuardrailOrchestrator(policy=AggregatePolicy.NO_CRITICAL_FAIL)
        orch.register(make_fail_check("crit", critical=True))
        orch.register(make_pass_check("c2"))
        result = orch.run_sync("hello")
        assert result.passed is False

    def test_majority_pass_policy(self):
        orch = GuardrailOrchestrator(policy=AggregatePolicy.MAJORITY_PASS)
        orch.register(make_pass_check("c1"))
        orch.register(make_pass_check("c2"))
        orch.register(make_fail_check("c3"))
        result = orch.run_sync("hello")
        assert result.passed is True

    def test_majority_fail(self):
        orch = GuardrailOrchestrator(policy=AggregatePolicy.MAJORITY_PASS)
        orch.register(make_pass_check("c1"))
        orch.register(make_fail_check("c2"))
        orch.register(make_fail_check("c3"))
        result = orch.run_sync("hello")
        assert result.passed is False

    def test_disabled_check_skipped(self):
        orch = GuardrailOrchestrator()
        orch.register(make_pass_check("c1"))
        chk = make_fail_check("c2")
        orch.register(chk)
        orch.disable("c2")
        result = orch.run_sync("hello")
        assert result.passed is True
        assert result.checks_run == 1

    def test_error_in_check_captured(self):
        orch = GuardrailOrchestrator()
        orch.register(make_error_check("err"))
        result = orch.run_sync("hello")
        assert result.passed is False
        assert result.outcomes[0].result == CheckResult.ERROR
        assert "Boom" in result.outcomes[0].details

    def test_empty_checks(self):
        orch = GuardrailOrchestrator()
        result = orch.run_sync("hello")
        assert result.passed is True
        assert result.checks_run == 0


# ── Async Execution ──────────────────────────────────────────────────────

class TestAsyncExecution:
    @pytest.mark.asyncio
    async def test_all_pass_async(self):
        orch = GuardrailOrchestrator()
        orch.register(make_pass_check("c1"))
        orch.register(make_pass_check("c2"))
        result = await orch.run("hello")
        assert result.passed is True
        assert result.checks_run == 2

    @pytest.mark.asyncio
    async def test_fail_async(self):
        orch = GuardrailOrchestrator()
        orch.register(make_pass_check("c1"))
        orch.register(make_fail_check("c2"))
        result = await orch.run("hello")
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_async_checks_run_in_parallel(self):
        orch = GuardrailOrchestrator()
        orch.register(make_slow_async_check("s1", delay=0.05))
        orch.register(make_slow_async_check("s2", delay=0.05))
        orch.register(make_slow_async_check("s3", delay=0.05))
        result = await orch.run("hello")
        assert result.passed is True
        # parallel: wall time should be ~50ms, not ~150ms
        assert result.parallel_latency_ms < 150  # generous threshold

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        orch = GuardrailOrchestrator()
        orch.register(make_timeout_check("timeout"))
        result = await orch.run("hello")
        assert result.passed is False
        assert result.outcomes[0].result == CheckResult.TIMEOUT

    @pytest.mark.asyncio
    async def test_error_in_async_check(self):
        orch = GuardrailOrchestrator()
        orch.register(make_error_check("err"))
        result = await orch.run("hello")
        assert result.passed is False
        assert result.outcomes[0].result == CheckResult.ERROR

    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        orch = GuardrailOrchestrator(max_concurrency=2)
        for i in range(5):
            orch.register(make_slow_async_check(f"s{i}", delay=0.01))
        result = await orch.run("hello")
        assert result.passed is True
        assert result.checks_run == 5


# ── Speedup & Latency ───────────────────────────────────────────────────

class TestLatency:
    def test_speedup_ratio(self):
        result = OrchestratorResult(
            total_latency_ms=300.0,
            parallel_latency_ms=100.0,
        )
        assert result.speedup_ratio == 3.0

    def test_speedup_ratio_zero_parallel(self):
        result = OrchestratorResult(
            total_latency_ms=300.0,
            parallel_latency_ms=0.0,
        )
        assert result.speedup_ratio == 1.0

    def test_latency_stats(self):
        orch = GuardrailOrchestrator()
        orch.register(make_pass_check("c1"))
        for _ in range(10):
            orch.run_sync("hello")
        stats = orch.get_latency_stats("c1")
        assert stats is not None
        assert stats.total_runs == 10
        assert stats.avg_ms >= 0

    def test_latency_stats_missing(self):
        orch = GuardrailOrchestrator()
        assert orch.get_latency_stats("nope") is None


# ── History & Summary ────────────────────────────────────────────────────

class TestHistory:
    def test_history_recorded(self):
        orch = GuardrailOrchestrator()
        orch.register(make_pass_check("c1"))
        orch.run_sync("hello")
        assert len(orch.history) == 1

    def test_clear_history(self):
        orch = GuardrailOrchestrator()
        orch.register(make_pass_check("c1"))
        orch.run_sync("hello")
        count = orch.clear_history()
        assert count == 1
        assert len(orch.history) == 0

    def test_summary(self):
        orch = GuardrailOrchestrator()
        orch.register(make_pass_check("c1"))
        orch.register(make_fail_check("c2"))
        orch.run_sync("hello")
        s = orch.summary()
        assert s["total_runs"] == 1
        assert s["registered_checks"] == 2
        assert s["policy"] == AggregatePolicy.ALL_PASS

    def test_summary_empty(self):
        orch = GuardrailOrchestrator()
        s = orch.summary()
        assert s["total_runs"] == 0
        assert s["pass_rate"] == 0.0
