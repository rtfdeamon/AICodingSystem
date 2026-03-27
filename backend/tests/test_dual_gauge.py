"""Tests for Joint Security-Functionality Benchmarking (DualGauge) engine."""

from __future__ import annotations

import pytest

from app.quality.dual_gauge import (
    BatchReport,
    DualGaugeEngine,
    DualTestCase,
    DualTestExecution,
    DualTestResult,
    DualTestType,
    GateDecision,
    SecurityCategory,
    TaskEvaluation,
)


@pytest.fixture
def engine() -> DualGaugeEngine:
    return DualGaugeEngine()


@pytest.fixture
def engine_with_tests(engine: DualGaugeEngine) -> DualGaugeEngine:
    engine.register_functional_test("func-1", "Test basic output")
    engine.register_functional_test("func-2", "Test edge cases")
    engine.register_functional_test("func-3", "Test error handling")
    engine.register_security_test(
        "sec-1", "SQL injection", SecurityCategory.INJECTION, severity_weight=2.0,
    )
    engine.register_security_test(
        "sec-2", "XSS prevention", SecurityCategory.XSS, severity_weight=1.5,
    )
    engine.register_security_test(
        "sec-3", "Auth bypass", SecurityCategory.BROKEN_AUTH, severity_weight=2.0,
    )
    return engine


def _make_results(
    func_pass: int = 3,
    func_fail: int = 0,
    sec_pass: int = 3,
    sec_fail: int = 0,
) -> list[DualTestExecution]:
    results: list[DualTestExecution] = []
    for i in range(func_pass):
        results.append(DualTestExecution(
            test_id=f"func-{i + 1}", test_type=DualTestType.FUNCTIONAL,
            result=DualTestResult.PASSED,
        ))
    for i in range(func_fail):
        results.append(DualTestExecution(
            test_id=f"func-{func_pass + i + 1}", test_type=DualTestType.FUNCTIONAL,
            result=DualTestResult.FAILED,
        ))
    for i in range(sec_pass):
        results.append(DualTestExecution(
            test_id=f"sec-{i + 1}", test_type=DualTestType.SECURITY,
            result=DualTestResult.PASSED,
        ))
    for i in range(sec_fail):
        results.append(DualTestExecution(
            test_id=f"sec-{sec_pass + i + 1}", test_type=DualTestType.SECURITY,
            result=DualTestResult.FAILED,
        ))
    return results


class TestRegistration:
    def test_register_functional_test(self, engine: DualGaugeEngine) -> None:
        tc = engine.register_functional_test("f1", "Test output")
        assert tc.test_type == DualTestType.FUNCTIONAL

    def test_register_security_test(self, engine: DualGaugeEngine) -> None:
        tc = engine.register_security_test(
            "s1", "Injection", SecurityCategory.INJECTION,
        )
        assert tc.test_type == DualTestType.SECURITY
        assert tc.security_category == SecurityCategory.INJECTION

    def test_register_test_directly(self, engine: DualGaugeEngine) -> None:
        tc = DualTestCase(id="t1", name="Custom", test_type=DualTestType.FUNCTIONAL)
        engine.register_test(tc)
        assert "t1" in engine._test_cases

    def test_assign_tests(self, engine_with_tests: DualGaugeEngine) -> None:
        engine_with_tests.assign_tests("task-1", ["func-1", "sec-1"])
        assert engine_with_tests._task_suites["task-1"] == ["func-1", "sec-1"]


class TestEvaluation:
    def test_all_pass(self, engine_with_tests: DualGaugeEngine) -> None:
        results = _make_results(3, 0, 3, 0)
        ev = engine_with_tests.evaluate("task-1", "def foo(): pass", results)
        assert isinstance(ev, TaskEvaluation)
        assert ev.joint_pass is True
        assert ev.gate_decision == GateDecision.PASS

    def test_functional_fail(self, engine_with_tests: DualGaugeEngine) -> None:
        results = _make_results(1, 2, 3, 0)
        ev = engine_with_tests.evaluate("task-2", "code", results)
        assert ev.functional_pass_rate < 0.8
        assert ev.joint_pass is False

    def test_security_fail_blocks(self, engine_with_tests: DualGaugeEngine) -> None:
        results = _make_results(3, 0, 0, 3)
        ev = engine_with_tests.evaluate("task-3", "code", results)
        assert ev.security_pass_rate < 0.7
        assert ev.gate_decision == GateDecision.BLOCK

    def test_both_fail(self, engine_with_tests: DualGaugeEngine) -> None:
        results = _make_results(0, 3, 0, 3)
        ev = engine_with_tests.evaluate("task-4", "code", results)
        assert ev.joint_pass is False
        assert ev.gate_decision == GateDecision.BLOCK

    def test_safe_score_range(self, engine_with_tests: DualGaugeEngine) -> None:
        results = _make_results(2, 1, 2, 1)
        ev = engine_with_tests.evaluate("task-5", "code", results)
        assert 0.0 <= ev.safe_score <= 1.0

    def test_code_snippet_truncated(self, engine_with_tests: DualGaugeEngine) -> None:
        long_code = "x" * 1000
        results = _make_results()
        ev = engine_with_tests.evaluate("task-6", long_code, results)
        assert len(ev.code_snippet) <= 500

    def test_timestamp_set(self, engine_with_tests: DualGaugeEngine) -> None:
        results = _make_results()
        ev = engine_with_tests.evaluate("task-7", "code", results)
        assert "T" in ev.timestamp

    def test_get_evaluation(self, engine_with_tests: DualGaugeEngine) -> None:
        results = _make_results()
        engine_with_tests.evaluate("task-8", "code", results)
        ev = engine_with_tests.get_evaluation("task-8")
        assert ev is not None
        assert ev.task_id == "task-8"

    def test_get_evaluation_nonexistent(self, engine_with_tests: DualGaugeEngine) -> None:
        assert engine_with_tests.get_evaluation("nope") is None

    def test_empty_results(self, engine_with_tests: DualGaugeEngine) -> None:
        ev = engine_with_tests.evaluate("task-9", "code", [])
        assert ev.functional_pass_rate == 0.0
        assert ev.security_pass_rate == 0.0

    def test_security_only_results(self, engine_with_tests: DualGaugeEngine) -> None:
        results = [
            DualTestExecution(
                test_id="sec-1",
                test_type=DualTestType.SECURITY,
                result=DualTestResult.PASSED,
            ),
        ]
        ev = engine_with_tests.evaluate("task-10", "code", results)
        assert ev.functional_pass_rate == 0.0
        assert ev.security_pass_rate > 0.0

    def test_weighted_security(self, engine_with_tests: DualGaugeEngine) -> None:
        # sec-1 has weight 2.0, sec-2 has weight 1.5, sec-3 has weight 2.0
        results = [
            DualTestExecution(
                test_id="sec-1",
                test_type=DualTestType.SECURITY,
                result=DualTestResult.PASSED,
            ),
            DualTestExecution(
                test_id="sec-2",
                test_type=DualTestType.SECURITY,
                result=DualTestResult.FAILED,
            ),
            DualTestExecution(
                test_id="sec-3",
                test_type=DualTestType.SECURITY,
                result=DualTestResult.PASSED,
            ),
        ]
        ev = engine_with_tests.evaluate("task-11", "code", results)
        # Weighted: (2.0 + 0 + 2.0) / (2.0 + 1.5 + 2.0) ≈ 0.727
        assert 0.7 <= ev.security_pass_rate <= 0.75


class TestBatchReport:
    def test_empty_report(self, engine: DualGaugeEngine) -> None:
        report = engine.batch_report()
        assert report.total_tasks == 0

    def test_report_after_evaluations(self, engine_with_tests: DualGaugeEngine) -> None:
        engine_with_tests.evaluate("t1", "code", _make_results(3, 0, 3, 0))
        engine_with_tests.evaluate("t2", "code", _make_results(0, 3, 3, 0))
        engine_with_tests.evaluate("t3", "code", _make_results(3, 0, 0, 3))
        report = engine_with_tests.batch_report()
        assert isinstance(report, BatchReport)
        assert report.total_tasks == 3
        assert report.tasks_both == 1
        # t2: func=0, sec=1.0 → security_only; t3: func=1.0, sec=0 → functional_only
        assert report.tasks_functional_only + report.tasks_security_only + report.tasks_neither == 2
        # Verify counts sum
        total = (
            report.tasks_both + report.tasks_functional_only
            + report.tasks_security_only + report.tasks_neither
        )
        assert total == 3

    def test_safe_at_1(self, engine_with_tests: DualGaugeEngine) -> None:
        engine_with_tests.evaluate("t1", "code", _make_results(3, 0, 3, 0))
        engine_with_tests.evaluate("t2", "code", _make_results(3, 0, 3, 0))
        report = engine_with_tests.batch_report()
        assert report.safe_at_1 == 1.0

    def test_gate_counts(self, engine_with_tests: DualGaugeEngine) -> None:
        engine_with_tests.evaluate("t1", "code", _make_results(3, 0, 3, 0))
        engine_with_tests.evaluate("t2", "code", _make_results(3, 0, 0, 3))
        report = engine_with_tests.batch_report()
        assert report.gate_passed >= 1
        assert report.gate_blocked >= 1

    def test_security_category_breakdown(self, engine_with_tests: DualGaugeEngine) -> None:
        results = [
            DualTestExecution(
                test_id="func-1",
                test_type=DualTestType.FUNCTIONAL,
                result=DualTestResult.PASSED,
            ),
            DualTestExecution(
                test_id="sec-1",
                test_type=DualTestType.SECURITY,
                result=DualTestResult.PASSED,
            ),
            DualTestExecution(
                test_id="sec-2",
                test_type=DualTestType.SECURITY,
                result=DualTestResult.FAILED,
            ),
        ]
        engine_with_tests.evaluate("t1", "code", results)
        report = engine_with_tests.batch_report()
        assert SecurityCategory.INJECTION in report.security_category_breakdown


class TestAnalyticsAndAudit:
    def test_audit_log(self, engine_with_tests: DualGaugeEngine) -> None:
        engine_with_tests.evaluate("t1", "code", _make_results())
        log = engine_with_tests.get_audit_log()
        assert len(log) >= 1
        assert log[0]["action"] == "evaluate"

    def test_analytics(self, engine_with_tests: DualGaugeEngine) -> None:
        engine_with_tests.evaluate("t1", "code", _make_results(3, 0, 3, 0))
        engine_with_tests.evaluate("t2", "code", _make_results(0, 3, 0, 3))
        stats = engine_with_tests.analytics()
        assert stats["total_evaluations"] == 2
        assert stats["gap"] >= 0.0

    def test_analytics_empty(self, engine: DualGaugeEngine) -> None:
        stats = engine.analytics()
        assert stats["total_evaluations"] == 0


class TestDisableSecurityBlock:
    def test_no_block_when_disabled(self) -> None:
        engine = DualGaugeEngine(block_on_security_fail=False)
        engine.register_functional_test("f1", "Test")
        engine.register_security_test("s1", "Sec", SecurityCategory.INJECTION)
        results = [
            DualTestExecution(
                test_id="f1",
                test_type=DualTestType.FUNCTIONAL,
                result=DualTestResult.PASSED,
            ),
            DualTestExecution(
                test_id="s1",
                test_type=DualTestType.SECURITY,
                result=DualTestResult.FAILED,
            ),
        ]
        ev = engine.evaluate("t1", "code", results)
        assert ev.gate_decision != GateDecision.BLOCK
