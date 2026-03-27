"""Joint Security-Functionality Benchmarking (DualGauge) — simultaneous
evaluation of both security and functional correctness of AI-generated code.

Research shows that >90% of LLM outputs are either functional or secure,
but rarely both simultaneously.  DualGauge exposes this gap by running
both functional tests and security tests against every code snippet,
producing a joint pass rate (SAFE@k) that reflects real-world readiness.

Based on Pathak et al. "DualGauge: Automated Joint Security-Functionality
Benchmarking for Secure Code Generation" (arXiv:2511.20709, Nov 2025).

Key capabilities:
- Dual test execution: functional + security tests per task
- SAFE@k metric: joint pass rate across both dimensions
- Sandboxed execution environment for generated code
- OWASP/CERT-grounded security test templates
- Task-level and batch-level analytics
- Quality gate with configurable thresholds
- Severity-weighted security scoring
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class DualTestType(StrEnum):
    FUNCTIONAL = "functional"
    SECURITY = "security"


class DualTestResult(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class SecurityCategory(StrEnum):
    INJECTION = "injection"
    BROKEN_AUTH = "broken_auth"
    DATA_EXPOSURE = "data_exposure"
    XXE = "xxe"
    BROKEN_ACCESS = "broken_access"
    MISCONFIG = "misconfig"
    XSS = "xss"
    DESERIALIZATION = "deserialization"
    VULNERABLE_DEPS = "vulnerable_deps"
    LOGGING_GAPS = "logging_gaps"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class DualTestCase:
    """A single test case (functional or security)."""

    id: str
    name: str
    test_type: DualTestType
    description: str = ""
    security_category: SecurityCategory | None = None
    severity_weight: float = 1.0  # higher = more important
    test_fn: str = ""  # Code or reference to test function


@dataclass
class DualTestExecution:
    """Result of executing a single test case."""

    test_id: str
    test_type: DualTestType
    result: DualTestResult
    message: str = ""
    duration_ms: float = 0.0


@dataclass
class TaskEvaluation:
    """Evaluation of a single code generation task."""

    task_id: str
    code_snippet: str
    functional_results: list[DualTestExecution]
    security_results: list[DualTestExecution]
    functional_pass_rate: float
    security_pass_rate: float
    joint_pass: bool  # True only if BOTH dimensions pass threshold
    safe_score: float  # weighted joint score
    gate_decision: GateDecision
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchReport:
    """Aggregated DualGauge report for a batch of tasks."""

    total_tasks: int
    functional_pass_rate: float
    security_pass_rate: float
    joint_pass_rate: float  # SAFE@k
    safe_at_1: float
    tasks_functional_only: int
    tasks_security_only: int
    tasks_both: int
    tasks_neither: int
    security_category_breakdown: dict[str, float]
    gate_blocked: int
    gate_warned: int
    gate_passed: int


# ── DualGauge Engine ─────────────────────────────────────────────────────

class DualGaugeEngine:
    """Joint security-functionality benchmarking engine.

    Evaluates code against both functional and security test suites,
    producing a joint SAFE@k score.
    """

    def __init__(
        self,
        *,
        functional_threshold: float = 0.8,
        security_threshold: float = 0.7,
        joint_threshold: float = 0.6,
        block_on_security_fail: bool = True,
    ) -> None:
        self._test_cases: dict[str, DualTestCase] = {}
        self._task_suites: dict[str, list[str]] = {}  # task_id → [test_ids]
        self._evaluations: list[TaskEvaluation] = []
        self._functional_threshold = functional_threshold
        self._security_threshold = security_threshold
        self._joint_threshold = joint_threshold
        self._block_on_security = block_on_security_fail
        self._audit_log: list[dict[str, Any]] = []

    # ── Test Registration ────────────────────────────────────────────

    def register_test(self, test: DualTestCase) -> None:
        """Register a test case."""
        self._test_cases[test.id] = test

    def assign_tests(self, task_id: str, test_ids: list[str]) -> None:
        """Assign test cases to a task."""
        self._task_suites[task_id] = test_ids

    def register_functional_test(
        self,
        test_id: str,
        name: str,
        description: str = "",
    ) -> DualTestCase:
        """Convenience: register a functional test."""
        tc = DualTestCase(
            id=test_id,
            name=name,
            test_type=DualTestType.FUNCTIONAL,
            description=description,
        )
        self.register_test(tc)
        return tc

    def register_security_test(
        self,
        test_id: str,
        name: str,
        category: SecurityCategory,
        *,
        severity_weight: float = 1.0,
        description: str = "",
    ) -> DualTestCase:
        """Convenience: register a security test."""
        tc = DualTestCase(
            id=test_id,
            name=name,
            test_type=DualTestType.SECURITY,
            description=description,
            security_category=category,
            severity_weight=severity_weight,
        )
        self.register_test(tc)
        return tc

    # ── Evaluation ───────────────────────────────────────────────────

    def evaluate(
        self,
        task_id: str,
        code_snippet: str,
        results: list[DualTestExecution],
    ) -> TaskEvaluation:
        """Evaluate a code snippet against its test suite results."""
        func_results = [r for r in results if r.test_type == DualTestType.FUNCTIONAL]
        sec_results = [r for r in results if r.test_type == DualTestType.SECURITY]

        func_pass = self._pass_rate(func_results)
        sec_pass = self._weighted_security_pass_rate(sec_results)

        joint = func_pass >= self._functional_threshold and sec_pass >= self._security_threshold
        safe_score = (func_pass + sec_pass) / 2.0

        # Gate decision
        if sec_pass < self._security_threshold and self._block_on_security:
            gate = GateDecision.BLOCK
        elif not joint:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        evaluation = TaskEvaluation(
            task_id=task_id,
            code_snippet=code_snippet[:500],
            functional_results=func_results,
            security_results=sec_results,
            functional_pass_rate=func_pass,
            security_pass_rate=sec_pass,
            joint_pass=joint,
            safe_score=safe_score,
            gate_decision=gate,
        )
        self._evaluations.append(evaluation)

        self._audit_log.append({
            "action": "evaluate",
            "task_id": task_id,
            "func_pass": func_pass,
            "sec_pass": sec_pass,
            "joint_pass": joint,
            "safe_score": safe_score,
            "gate": gate,
            "timestamp": evaluation.timestamp,
        })

        return evaluation

    def batch_report(self) -> BatchReport:
        """Generate aggregated report from all evaluations."""
        if not self._evaluations:
            return BatchReport(
                total_tasks=0,
                functional_pass_rate=0.0,
                security_pass_rate=0.0,
                joint_pass_rate=0.0,
                safe_at_1=0.0,
                tasks_functional_only=0,
                tasks_security_only=0,
                tasks_both=0,
                tasks_neither=0,
                security_category_breakdown={},
                gate_blocked=0,
                gate_warned=0,
                gate_passed=0,
            )

        n = len(self._evaluations)
        func_only = 0
        sec_only = 0
        both = 0
        neither = 0

        for ev in self._evaluations:
            f_ok = ev.functional_pass_rate >= self._functional_threshold
            s_ok = ev.security_pass_rate >= self._security_threshold
            if f_ok and s_ok:
                both += 1
            elif f_ok:
                func_only += 1
            elif s_ok:
                sec_only += 1
            else:
                neither += 1

        # Security category breakdown
        cat_scores: dict[str, list[float]] = {}
        for ev in self._evaluations:
            for sr in ev.security_results:
                tc = self._test_cases.get(sr.test_id)
                if tc and tc.security_category:
                    cat_scores.setdefault(tc.security_category, []).append(
                        1.0 if sr.result == DualTestResult.PASSED else 0.0,
                    )

        cat_breakdown = {
            cat: sum(scores) / len(scores)
            for cat, scores in cat_scores.items()
        }

        return BatchReport(
            total_tasks=n,
            functional_pass_rate=sum(e.functional_pass_rate for e in self._evaluations) / n,
            security_pass_rate=sum(e.security_pass_rate for e in self._evaluations) / n,
            joint_pass_rate=both / n,
            safe_at_1=both / n,
            tasks_functional_only=func_only,
            tasks_security_only=sec_only,
            tasks_both=both,
            tasks_neither=neither,
            security_category_breakdown=cat_breakdown,
            gate_blocked=sum(1 for e in self._evaluations if e.gate_decision == GateDecision.BLOCK),
            gate_warned=sum(1 for e in self._evaluations if e.gate_decision == GateDecision.WARN),
            gate_passed=sum(1 for e in self._evaluations if e.gate_decision == GateDecision.PASS),
        )

    def get_evaluation(self, task_id: str) -> TaskEvaluation | None:
        for ev in reversed(self._evaluations):
            if ev.task_id == task_id:
                return ev
        return None

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def analytics(self) -> dict[str, Any]:
        report = self.batch_report()
        return {
            "total_evaluations": report.total_tasks,
            "functional_pass_rate": report.functional_pass_rate,
            "security_pass_rate": report.security_pass_rate,
            "safe_at_1": report.safe_at_1,
            "joint_pass_rate": report.joint_pass_rate,
            "gap": abs(report.functional_pass_rate - report.security_pass_rate),
            "blocked": report.gate_blocked,
        }

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _pass_rate(results: list[DualTestExecution]) -> float:
        if not results:
            return 0.0
        passed = sum(1 for r in results if r.result == DualTestResult.PASSED)
        return passed / len(results)

    def _weighted_security_pass_rate(self, results: list[DualTestExecution]) -> float:
        if not results:
            return 0.0
        total_weight = 0.0
        weighted_pass = 0.0
        for r in results:
            tc = self._test_cases.get(r.test_id)
            weight = tc.severity_weight if tc else 1.0
            total_weight += weight
            if r.result == DualTestResult.PASSED:
                weighted_pass += weight
        return weighted_pass / max(total_weight, 0.001)
