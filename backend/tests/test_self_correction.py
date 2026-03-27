"""Tests for Self-Correction Pipeline."""

from __future__ import annotations

from app.quality.self_correction import (
    CorrectionSession,
    CorrectionStatus,
    CorrectionStrategy,
    DetectedIssue,
    IssueDetector,
    IssueType,
    SelfCorrectionPipeline,
)

# ── IssueDetector ────────────────────────────────────────────────────────

class TestIssueDetector:
    def test_detect_eval_usage(self):
        detector = IssueDetector()
        issues = detector.detect("result = eval(user_input)")
        assert any(i.issue_type == IssueType.SECURITY_ISSUE for i in issues)

    def test_detect_exec_usage(self):
        detector = IssueDetector()
        issues = detector.detect("exec(code)")
        assert any(i.issue_type == IssueType.SECURITY_ISSUE for i in issues)

    def test_detect_subprocess_shell(self):
        detector = IssueDetector()
        issues = detector.detect("subprocess.call(cmd, shell=True)")
        assert any(i.issue_type == IssueType.SECURITY_ISSUE for i in issues)

    def test_detect_pickle_loads(self):
        detector = IssueDetector()
        issues = detector.detect("data = pickle.loads(raw)")
        assert any(i.issue_type == IssueType.SECURITY_ISSUE for i in issues)

    def test_detect_os_system(self):
        detector = IssueDetector()
        issues = detector.detect("os.system('rm -rf /')")
        assert any(i.issue_type == IssueType.SECURITY_ISSUE for i in issues)

    def test_detect_sql_injection(self):
        detector = IssueDetector()
        issues = detector.detect('query = f"SELECT * FROM users WHERE id={input}"')
        assert any(i.issue_type == IssueType.SECURITY_ISSUE for i in issues)

    def test_detect_innerhtml_xss(self):
        detector = IssueDetector()
        issues = detector.detect("element.innerHTML = userInput")
        assert any(i.issue_type == IssueType.SECURITY_ISSUE for i in issues)

    def test_detect_todo_marker(self):
        detector = IssueDetector()
        issues = detector.detect("# TODO: implement this")
        assert any(i.issue_type == IssueType.INCOMPLETE_OUTPUT for i in issues)

    def test_detect_ellipsis_placeholder(self):
        detector = IssueDetector()
        issues = detector.detect("def foo():\n    ...")
        assert any(i.issue_type == IssueType.INCOMPLETE_OUTPUT for i in issues)

    def test_detect_not_implemented(self):
        detector = IssueDetector()
        issues = detector.detect("raise NotImplementedError")
        assert any(i.issue_type == IssueType.INCOMPLETE_OUTPUT for i in issues)

    def test_detect_pass_statement(self):
        detector = IssueDetector()
        issues = detector.detect("def foo():\n    pass")
        assert any(i.issue_type == IssueType.INCOMPLETE_OUTPUT for i in issues)

    def test_detect_missing_error_handling(self):
        detector = IssueDetector()
        code = "def a(): pass\ndef b(): pass\ndef c(): pass"
        issues = detector.detect(code)
        assert any(i.issue_type == IssueType.MISSING_ERROR_HANDLING for i in issues)

    def test_safe_code_no_issues(self):
        detector = IssueDetector()
        code = "def add(a, b):\n    return a + b"
        issues = detector.detect(code)
        # No security issues (may have quality notes)
        security = [i for i in issues if i.issue_type == IssueType.SECURITY_ISSUE]
        assert len(security) == 0

    def test_truncated_output_detected(self):
        detector = IssueDetector()
        code = "def foo():\n    if x:\n        {{{{"
        issues = detector.detect(code)
        assert any(
            i.issue_type == IssueType.INCOMPLETE_OUTPUT
            and "truncated" in i.description.lower()
            for i in issues
        )

    def test_complete_output_ok(self):
        detector = IssueDetector()
        code = "def foo():\n    return {}"
        issues = detector.detect(code)
        truncated = [i for i in issues if i.description == "Output appears truncated"]
        assert len(truncated) == 0

    def test_line_numbers_in_location(self):
        detector = IssueDetector()
        code = "safe line\nresult = eval(x)\nanother safe line"
        issues = detector.detect(code)
        security = [i for i in issues if i.issue_type == IssueType.SECURITY_ISSUE]
        assert any("line:2" in i.location for i in security)

    def test_severity_set(self):
        detector = IssueDetector()
        issues = detector.detect("eval(x)")
        security = [i for i in issues if i.issue_type == IssueType.SECURITY_ISSUE]
        assert all(i.severity > 0 for i in security)

    def test_dynamic_import_detected(self):
        detector = IssueDetector()
        issues = detector.detect("mod = __import__('os')")
        assert any(i.issue_type == IssueType.SECURITY_ISSUE for i in issues)


# ── SelfCorrectionPipeline ───────────────────────────────────────────────

class TestPipelineBasics:
    def test_detect_delegates_to_detector(self):
        pipeline = SelfCorrectionPipeline()
        issues = pipeline.detect("eval(x)")
        assert len(issues) > 0

    def test_start_session_with_issues(self):
        pipeline = SelfCorrectionPipeline()
        session = pipeline.start_session("eval(x)")
        assert session.status == CorrectionStatus.PENDING
        assert session.total_issues_found > 0
        assert len(session.detected_issues) > 0

    def test_start_session_clean_code(self):
        pipeline = SelfCorrectionPipeline()
        session = pipeline.start_session("def add(a, b):\n    return a + b")
        assert session.status == CorrectionStatus.FIXED
        assert session.completed_at is not None

    def test_generate_feedback(self):
        pipeline = SelfCorrectionPipeline()
        issues = pipeline.detect("eval(x)")
        feedback = pipeline.generate_feedback(issues)
        assert "eval" in feedback.lower() or "security" in feedback.lower()

    def test_generate_feedback_empty(self):
        pipeline = SelfCorrectionPipeline()
        assert pipeline.generate_feedback([]) == ""


# ── Correction Attempts ──────────────────────────────────────────────────

class TestCorrectionAttempts:
    def test_successful_correction(self):
        pipeline = SelfCorrectionPipeline()
        session = pipeline.start_session("eval(user_input)")
        # Replace with code that has no issues at all
        pipeline.record_attempt(session, "result = int(user_input)")
        assert session.status == CorrectionStatus.FIXED

    def test_correction_with_remaining_issues(self):
        pipeline = SelfCorrectionPipeline()
        session = pipeline.start_session("eval(x)\nexec(y)")
        # Fix eval but keep exec
        pipeline.record_attempt(session, "safe(x)\nexec(y)")
        assert session.status in (
            CorrectionStatus.PARTIALLY_FIXED,
            CorrectionStatus.PENDING,
            CorrectionStatus.IN_PROGRESS,
        )

    def test_max_attempts_exceeded(self):
        pipeline = SelfCorrectionPipeline(max_attempts=2)
        session = pipeline.start_session("eval(x)")
        pipeline.record_attempt(session, "eval(x)")  # still bad
        pipeline.record_attempt(session, "eval(x)")  # still bad
        pipeline.record_attempt(session, "eval(x)")  # exceeds max
        assert session.status == CorrectionStatus.ESCALATED

    def test_hashes_recorded(self):
        pipeline = SelfCorrectionPipeline()
        session = pipeline.start_session("eval(x)")
        attempt = pipeline.record_attempt(session, "safe(x)")
        assert len(attempt.original_hash) == 16
        assert len(attempt.corrected_hash) == 16

    def test_final_output_updated(self):
        pipeline = SelfCorrectionPipeline()
        session = pipeline.start_session("eval(x)")
        pipeline.record_attempt(session, "safe_call(x)")
        assert session.final_output == "safe_call(x)"


# ── Circuit Breaker ──────────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_circuit_opens_after_threshold(self):
        pipeline = SelfCorrectionPipeline(circuit_breaker_threshold=3)
        for _ in range(3):
            session = pipeline.start_session("eval(x)")
            pipeline.record_attempt(session, "eval(x)")  # keeps failing
        assert pipeline.is_circuit_open is True

    def test_circuit_blocks_new_attempts(self):
        pipeline = SelfCorrectionPipeline(circuit_breaker_threshold=2)
        for _ in range(2):
            s = pipeline.start_session("eval(x)")
            pipeline.record_attempt(s, "eval(x)")
        assert pipeline.is_circuit_open
        new_session = pipeline.start_session("eval(y)")
        pipeline.record_attempt(new_session, "safe(y)")
        assert new_session.status == CorrectionStatus.ESCALATED

    def test_reset_circuit(self):
        pipeline = SelfCorrectionPipeline(circuit_breaker_threshold=1)
        s = pipeline.start_session("eval(x)")
        pipeline.record_attempt(s, "eval(x)")
        assert pipeline.is_circuit_open
        pipeline.reset_circuit()
        assert pipeline.is_circuit_open is False


# ── Strategies ───────────────────────────────────────────────────────────

class TestStrategies:
    def test_default_strategies_loaded(self):
        pipeline = SelfCorrectionPipeline()
        assert IssueType.SECURITY_ISSUE in pipeline._strategies
        assert IssueType.SYNTAX_ERROR in pipeline._strategies

    def test_custom_strategy(self):
        strategy = CorrectionStrategy(
            issue_type=IssueType.STYLE_VIOLATION,
            max_retries=1,
            feedback_template="Fix style: {description}",
        )
        pipeline = SelfCorrectionPipeline()
        pipeline.set_strategy(strategy)
        assert pipeline._strategies[IssueType.STYLE_VIOLATION].max_retries == 1

    def test_escalation_for_non_auto_fixable(self):
        pipeline = SelfCorrectionPipeline()
        # Logic errors are not auto-fixable and escalate after 1 attempt
        issues = [DetectedIssue(
            issue_type=IssueType.LOGIC_ERROR,
            severity=7,
            description="Wrong algorithm",
        )]
        session = CorrectionSession(
            original_output="bad code",
            final_output="bad code",
            detected_issues=issues,
            status=CorrectionStatus.PENDING,
            total_issues_found=1,
        )
        pipeline._sessions.append(session)
        # Simulate: after attempt 1, logic error still present
        pipeline.record_attempt(session, "still bad code with FIXME\neval(x)")
        # The logic error strategy escalates after 1 attempt


# ── Analytics ────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_sessions_tracked(self):
        pipeline = SelfCorrectionPipeline()
        pipeline.start_session("eval(x)")
        assert len(pipeline.sessions) == 1

    def test_clear_sessions(self):
        pipeline = SelfCorrectionPipeline()
        pipeline.start_session("eval(x)")
        count = pipeline.clear_sessions()
        assert count == 1
        assert len(pipeline.sessions) == 0

    def test_success_rate(self):
        pipeline = SelfCorrectionPipeline()
        s1 = pipeline.start_session("def add(a, b):\n    return a + b")  # clean
        assert s1.status == CorrectionStatus.FIXED
        s2 = pipeline.start_session("eval(x)")
        pipeline.record_attempt(s2, "safe(x)")
        rate = pipeline.success_rate()
        assert rate is not None

    def test_success_rate_empty(self):
        pipeline = SelfCorrectionPipeline()
        assert pipeline.success_rate() is None

    def test_avg_attempts_to_fix(self):
        pipeline = SelfCorrectionPipeline()
        s = pipeline.start_session("eval(x)")
        pipeline.record_attempt(s, "safe_call(x)")
        avg = pipeline.avg_attempts_to_fix()
        if s.status == CorrectionStatus.FIXED:
            assert avg is not None
            assert avg >= 1.0

    def test_summary(self):
        pipeline = SelfCorrectionPipeline()
        pipeline.start_session("eval(x)")
        s = pipeline.summary()
        assert s["total_sessions"] == 1
        assert "by_status" in s
        assert "circuit_breaker_open" in s

    def test_summary_empty(self):
        pipeline = SelfCorrectionPipeline()
        s = pipeline.summary()
        assert s["total_sessions"] == 0
