"""Tests for Maker-Checker Loop Orchestrator."""

from __future__ import annotations

import pytest

from app.quality.maker_checker_loop import (
    BatchLoopReport,
    CheckCriterion,
    CheckResult,
    GateDecision,
    LoopConfig,
    LoopOutcome,
    LoopSession,
    MakerCheckerLoop,
    _aggregate_feedback,
    _all_required_pass,
    _compute_overall_score,
    _detect_stagnation,
    _outcome_to_gate,
)


# ── Helper factories ──────────────────────────────────────────────────────

def _make_loop(**overrides) -> MakerCheckerLoop:
    config = LoopConfig(**overrides) if overrides else None
    return MakerCheckerLoop(config)


def _good_checks(score: float = 0.90) -> list[CheckResult]:
    return [
        CheckResult(criterion=CheckCriterion.CORRECTNESS, passed=True, score=score, feedback=""),
        CheckResult(criterion=CheckCriterion.COMPLETENESS, passed=True, score=score, feedback=""),
        CheckResult(criterion=CheckCriterion.STYLE, passed=True, score=score, feedback=""),
    ]


def _bad_checks(score: float = 0.30) -> list[CheckResult]:
    return [
        CheckResult(criterion=CheckCriterion.CORRECTNESS, passed=False, score=score, feedback="incorrect logic"),
        CheckResult(criterion=CheckCriterion.COMPLETENESS, passed=False, score=score, feedback="missing edge cases"),
    ]


def _mixed_checks() -> list[CheckResult]:
    return [
        CheckResult(criterion=CheckCriterion.CORRECTNESS, passed=True, score=0.85),
        CheckResult(criterion=CheckCriterion.COMPLETENESS, passed=True, score=0.70),
        CheckResult(criterion=CheckCriterion.STYLE, passed=False, score=0.40, feedback="inconsistent naming"),
    ]


# ── Pure helper tests ─────────────────────────────────────────────────────

class TestComputeOverallScore:
    def test_empty(self):
        assert _compute_overall_score([]) == 0.0

    def test_uniform(self):
        results = _good_checks(0.80)
        assert _compute_overall_score(results) == 0.8

    def test_mixed(self):
        results = _mixed_checks()
        score = _compute_overall_score(results)
        assert 0.6 < score < 0.7


class TestAllRequiredPass:
    def test_all_pass(self):
        results = _good_checks()
        assert _all_required_pass(results, [CheckCriterion.CORRECTNESS, CheckCriterion.COMPLETENESS])

    def test_missing_required(self):
        results = [CheckResult(criterion=CheckCriterion.STYLE, passed=True, score=0.9)]
        assert not _all_required_pass(results, [CheckCriterion.CORRECTNESS])

    def test_empty_required(self):
        assert _all_required_pass([], [])


class TestDetectStagnation:
    def test_no_stagnation(self):
        assert not _detect_stagnation([0.3, 0.5, 0.7, 0.85], 0.02, 2)

    def test_stagnation_detected(self):
        assert _detect_stagnation([0.7, 0.71, 0.71, 0.71], 0.02, 2)

    def test_too_few_rounds(self):
        assert not _detect_stagnation([0.5, 0.5], 0.02, 2)

    def test_boundary_tolerance(self):
        # Improvement exactly at tolerance
        assert _detect_stagnation([0.5, 0.51, 0.52], 0.02, 2)


class TestAggregateDescription:
    def test_all_passed(self):
        results = _good_checks()
        assert _aggregate_feedback(results) == "All checks passed."

    def test_with_failures(self):
        results = _bad_checks()
        feedback = _aggregate_feedback(results)
        assert "incorrect logic" in feedback
        assert "missing edge cases" in feedback


class TestOutcomeToGate:
    def test_approved(self):
        assert _outcome_to_gate(LoopOutcome.APPROVED) == GateDecision.PASS

    def test_conditional(self):
        assert _outcome_to_gate(LoopOutcome.CONDITIONALLY_APPROVED) == GateDecision.WARN

    def test_rejected(self):
        assert _outcome_to_gate(LoopOutcome.REJECTED) == GateDecision.BLOCK

    def test_escalated(self):
        assert _outcome_to_gate(LoopOutcome.ESCALATED) == GateDecision.BLOCK


# ── Loop session tests ────────────────────────────────────────────────────

class TestStartSession:
    def test_creates_session(self):
        loop = _make_loop()
        session = loop.start_session("coder", "reviewer")
        assert session.agent_maker == "coder"
        assert session.agent_checker == "reviewer"
        assert session.session_id

    def test_with_task_description(self):
        loop = _make_loop()
        session = loop.start_session("coder", "reviewer", task_description="implement auth")
        assert session.task_description == "implement auth"


class TestRecordIteration:
    def test_first_iteration(self):
        loop = _make_loop()
        session = loop.start_session("m", "c")
        record = loop.record_iteration(session.session_id, _good_checks())
        assert record.iteration == 1
        assert record.approved is True

    def test_sequential_iterations(self):
        loop = _make_loop()
        session = loop.start_session("m", "c")
        loop.record_iteration(session.session_id, _bad_checks())
        r2 = loop.record_iteration(session.session_id, _good_checks())
        assert r2.iteration == 2
        assert len(session.iterations) == 2

    def test_invalid_session(self):
        loop = _make_loop()
        with pytest.raises(ValueError, match="not found"):
            loop.record_iteration("nonexistent", _good_checks())

    def test_tracks_improvement_trajectory(self):
        loop = _make_loop()
        session = loop.start_session("m", "c")
        loop.record_iteration(session.session_id, _bad_checks(0.30))
        loop.record_iteration(session.session_id, _good_checks(0.90))
        assert len(session.improvement_trajectory) == 2
        assert session.improvement_trajectory[0] < session.improvement_trajectory[1]


class TestEvaluateSession:
    def test_approved_on_good_checks(self):
        loop = _make_loop()
        session = loop.start_session("m", "c")
        loop.record_iteration(session.session_id, _good_checks())
        result = loop.evaluate_session(session.session_id)
        assert result.outcome == LoopOutcome.APPROVED
        assert result.gate == GateDecision.PASS

    def test_rejected_on_bad_checks(self):
        loop = _make_loop(max_iterations=1, escalate_on_rejection=False)
        session = loop.start_session("m", "c")
        loop.record_iteration(session.session_id, _bad_checks())
        result = loop.evaluate_session(session.session_id)
        assert result.outcome == LoopOutcome.REJECTED

    def test_escalated_at_cap(self):
        loop = _make_loop(max_iterations=2, escalate_on_rejection=True)
        session = loop.start_session("m", "c")
        loop.record_iteration(session.session_id, _bad_checks())
        loop.record_iteration(session.session_id, _bad_checks())
        result = loop.evaluate_session(session.session_id)
        assert result.outcome == LoopOutcome.ESCALATED

    def test_stagnation_detection(self):
        loop = _make_loop(max_iterations=10, stagnation_rounds=2, stagnation_tolerance=0.02)
        session = loop.start_session("m", "c")
        for _ in range(4):
            loop.record_iteration(session.session_id, _bad_checks(0.50))
        result = loop.evaluate_session(session.session_id)
        assert result.outcome == LoopOutcome.STAGNATED

    def test_conditional_approval(self):
        loop = _make_loop(max_iterations=1)
        session = loop.start_session("m", "c")
        # Score between conditional and approval thresholds
        checks = [
            CheckResult(criterion=CheckCriterion.CORRECTNESS, passed=True, score=0.70),
            CheckResult(criterion=CheckCriterion.COMPLETENESS, passed=True, score=0.70),
        ]
        loop.record_iteration(session.session_id, checks)
        result = loop.evaluate_session(session.session_id)
        assert result.outcome == LoopOutcome.CONDITIONALLY_APPROVED

    def test_empty_session(self):
        loop = _make_loop()
        session = loop.start_session("m", "c")
        result = loop.evaluate_session(session.session_id)
        assert result.outcome == LoopOutcome.REJECTED  # default

    def test_invalid_session_evaluate(self):
        loop = _make_loop()
        with pytest.raises(ValueError):
            loop.evaluate_session("nonexistent")

    def test_completed_at_set(self):
        loop = _make_loop()
        session = loop.start_session("m", "c")
        loop.record_iteration(session.session_id, _good_checks())
        result = loop.evaluate_session(session.session_id)
        assert result.completed_at is not None


class TestBatchReport:
    def test_empty_report(self):
        loop = _make_loop()
        report = loop.batch_report()
        assert report.total_sessions == 0

    def test_multi_session_report(self):
        loop = _make_loop()

        # Approved session
        s1 = loop.start_session("m1", "c1")
        loop.record_iteration(s1.session_id, _good_checks())
        loop.evaluate_session(s1.session_id)

        # Rejected session
        s2 = loop.start_session("m2", "c2")
        loop.record_iteration(s2.session_id, _bad_checks())
        loop.evaluate_session(s2.session_id)

        report = loop.batch_report()
        assert report.total_sessions == 2
        assert report.approval_rate == 0.5

    def test_avg_iterations(self):
        loop = _make_loop()
        s1 = loop.start_session("m", "c")
        loop.record_iteration(s1.session_id, _bad_checks())
        loop.record_iteration(s1.session_id, _good_checks())
        loop.evaluate_session(s1.session_id)

        report = loop.batch_report()
        assert report.avg_iterations_to_approval == 2.0


class TestLoopConfig:
    def test_defaults(self):
        cfg = LoopConfig()
        assert cfg.max_iterations == 5
        assert cfg.approval_threshold == 0.80
        assert CheckCriterion.CORRECTNESS in cfg.required_criteria

    def test_custom(self):
        cfg = LoopConfig(max_iterations=10, approval_threshold=0.90)
        assert cfg.max_iterations == 10


class TestEnumValues:
    def test_outcomes(self):
        assert LoopOutcome.APPROVED == "approved"
        assert LoopOutcome.STAGNATED == "stagnated"

    def test_criteria(self):
        assert CheckCriterion.SAFETY == "safety"
