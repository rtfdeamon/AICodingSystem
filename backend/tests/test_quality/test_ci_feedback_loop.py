"""Tests for CI Feedback Loop module."""

from __future__ import annotations

from app.quality.ci_feedback_loop import (
    CIFeedbackLoop,
    CorrectionStatus,
    FailureContext,
    FailureType,
    classify_failure,
    clear_sessions,
    generate_correction_prompt,
    get_feedback_stats,
    get_sessions,
    parse_failure_output,
)

FT = FailureType


class TestFailureClassification:
    """Classify CI failures from raw output."""

    def test_classify_test_failure(self) -> None:
        out = "FAILED tests/test_foo.py::test_bar"
        assert classify_failure(out) == FT.TEST_FAILURE

    def test_classify_assertion_error(self) -> None:
        assert classify_failure("AssertionError: expected True") == FT.TEST_FAILURE

    def test_classify_lint_ruff(self) -> None:
        assert classify_failure("ruff check found 3 errors") == FT.LINT_ERROR

    def test_classify_lint_eslint(self) -> None:
        out = "eslint: 2 problems (1 error, 1 warning)"
        assert classify_failure(out) == FT.LINT_ERROR

    def test_classify_type_error_mypy(self) -> None:
        out = "mypy: error: Argument 1 has incompatible type"
        assert classify_failure(out) == FT.TYPE_ERROR

    def test_classify_import_error(self) -> None:
        out = "ModuleNotFoundError: No module named 'foo'"
        assert classify_failure(out) == FT.IMPORT_ERROR

    def test_classify_build_error(self) -> None:
        out = "SyntaxError: invalid syntax"
        assert classify_failure(out) == FT.BUILD_ERROR

    def test_classify_runtime_error(self) -> None:
        out = "RuntimeError: cannot re-initialize"
        assert classify_failure(out) == FT.RUNTIME_ERROR

    def test_classify_security_scan(self) -> None:
        assert classify_failure("bandit found 2 issues") == FT.SECURITY_SCAN

    def test_classify_unknown(self) -> None:
        assert classify_failure("something weird happened") == FT.UNKNOWN


class TestParseFailureOutput:
    """Parse raw CI output into structured context."""

    def test_basic_parse(self) -> None:
        raw = "FAILED tests/test_api.py::test_login - AssertionError"
        ctx = parse_failure_output(raw, ci_job="pytest", exit_code=1)
        assert ctx.failure_type == FT.TEST_FAILURE
        assert ctx.ci_job == "pytest"
        assert ctx.exit_code == 1

    def test_extracts_error_message(self) -> None:
        raw = "error: Argument 1 has incompatible type\nmore details"
        ctx = parse_failure_output(raw)
        assert "error" in ctx.error_message.lower()

    def test_extracts_affected_files(self) -> None:
        raw = 'File "app/main.py", line 42, in foo\n  raise ValueError'
        ctx = parse_failure_output(raw)
        assert "app/main.py" in ctx.affected_files

    def test_extracts_test_name(self) -> None:
        raw = "FAILED tests/test_auth.py::test_login_invalid"
        ctx = parse_failure_output(raw)
        assert "test_auth" in ctx.test_name or "test_login" in ctx.test_name

    def test_truncates_raw_output(self) -> None:
        raw = "x" * 10000
        ctx = parse_failure_output(raw)
        assert len(ctx.raw_output) <= 5000

    def test_empty_output(self) -> None:
        ctx = parse_failure_output("")
        assert ctx.failure_type == FT.UNKNOWN


class TestCorrectionPromptGeneration:
    """Generate correction prompts from failure context."""

    def test_test_failure_prompt(self) -> None:
        ctx = FailureContext(
            failure_type=FT.TEST_FAILURE,
            error_message="AssertionError: expected 200 got 404",
            test_name="test_login",
            affected_files=["app/auth.py"],
        )
        prompt = generate_correction_prompt(ctx)
        assert "test_login" in prompt
        assert "AssertionError" in prompt
        assert "app/auth.py" in prompt

    def test_lint_prompt(self) -> None:
        ctx = FailureContext(
            failure_type=FT.LINT_ERROR,
            error_message="E501: line too long",
            affected_files=["app/main.py"],
        )
        prompt = generate_correction_prompt(ctx)
        assert "E501" in prompt
        assert "lint" in prompt.lower() or "Lint" in prompt

    def test_type_error_prompt(self) -> None:
        ctx = FailureContext(
            failure_type=FT.TYPE_ERROR,
            error_message="Incompatible type 'str'",
            affected_files=["app/models.py"],
        )
        prompt = generate_correction_prompt(ctx)
        assert "type" in prompt.lower()

    def test_import_error_prompt(self) -> None:
        ctx = FailureContext(
            failure_type=FT.IMPORT_ERROR,
            error_message="ModuleNotFoundError: no module named 'foo'",
        )
        prompt = generate_correction_prompt(ctx)
        assert "module" in prompt.lower() or "import" in prompt.lower()

    def test_unknown_type_uses_default(self) -> None:
        ctx = FailureContext(
            failure_type=FT.UNKNOWN,
            error_message="something broke",
        )
        prompt = generate_correction_prompt(ctx)
        assert "something broke" in prompt


class TestFeedbackSession:
    """Feedback session lifecycle tests."""

    def setup_method(self) -> None:
        clear_sessions()

    def test_create_session(self) -> None:
        loop = CIFeedbackLoop()
        ctx = FailureContext(failure_type=FT.TEST_FAILURE, error_message="fail")
        session = loop.create_session(ctx)
        assert session.id
        assert session.status == CorrectionStatus.PENDING
        assert session.failure == ctx

    def test_record_successful_attempt(self) -> None:
        loop = CIFeedbackLoop()
        ctx = FailureContext(failure_type=FT.TEST_FAILURE, error_message="fail")
        session = loop.create_session(ctx)
        loop.record_attempt(
            session, proposed_diff="fix", verification_passed=True,
        )
        assert session.status == CorrectionStatus.FIXED
        assert session.is_resolved
        assert session.resolved_at is not None

    def test_record_failed_attempt(self) -> None:
        loop = CIFeedbackLoop()
        ctx = FailureContext(failure_type=FT.LINT_ERROR, error_message="lint")
        session = loop.create_session(ctx)
        loop.record_attempt(session, error_after="still failing")
        assert session.status == CorrectionStatus.IN_PROGRESS
        assert session.attempt_count == 1

    def test_max_attempts_exhausted(self) -> None:
        loop = CIFeedbackLoop(max_attempts=2)
        ctx = FailureContext(failure_type=FT.BUILD_ERROR, error_message="err")
        session = loop.create_session(ctx)
        loop.record_attempt(session, error_after="nope")
        loop.record_attempt(session, error_after="still nope")
        assert session.status == CorrectionStatus.FAILED

    def test_should_retry(self) -> None:
        loop = CIFeedbackLoop(max_attempts=3)
        ctx = FailureContext(failure_type=FT.TEST_FAILURE, error_message="f")
        session = loop.create_session(ctx)
        assert loop.should_retry(session)
        loop.record_attempt(session, error_after="err")
        assert loop.should_retry(session)

    def test_should_not_retry_after_fix(self) -> None:
        loop = CIFeedbackLoop()
        ctx = FailureContext(failure_type=FT.TEST_FAILURE, error_message="f")
        session = loop.create_session(ctx)
        loop.record_attempt(session, verification_passed=True)
        assert not loop.should_retry(session)

    def test_skip_session(self) -> None:
        loop = CIFeedbackLoop()
        ctx = FailureContext(failure_type=FT.TEST_FAILURE, error_message="f")
        session = loop.create_session(ctx)
        loop.skip_session(session, reason="human will fix")
        assert session.status == CorrectionStatus.SKIPPED
        assert not loop.should_retry(session)

    def test_backoff_exponential(self) -> None:
        assert CIFeedbackLoop.get_backoff_seconds(1) == 2
        assert CIFeedbackLoop.get_backoff_seconds(2) == 4
        assert CIFeedbackLoop.get_backoff_seconds(3) == 8

    def test_backoff_capped(self) -> None:
        assert CIFeedbackLoop.get_backoff_seconds(10) == 60


class TestAnalytics:
    """Feedback analytics tests."""

    def setup_method(self) -> None:
        clear_sessions()

    def test_empty_stats(self) -> None:
        stats = get_feedback_stats()
        assert stats["total_sessions"] == 0

    def test_stats_after_sessions(self) -> None:
        loop = CIFeedbackLoop()
        ctx1 = FailureContext(failure_type=FT.TEST_FAILURE, error_message="f1")
        s1 = loop.create_session(ctx1)
        loop.record_attempt(s1, verification_passed=True)

        ctx2 = FailureContext(failure_type=FT.LINT_ERROR, error_message="f2")
        s2 = loop.create_session(ctx2)
        loop.record_attempt(s2, error_after="nope")
        loop.record_attempt(s2, error_after="nope")
        loop.record_attempt(s2, error_after="nope")

        stats = get_feedback_stats()
        assert stats["total_sessions"] == 2
        assert stats["fixed"] == 1
        assert stats["failed"] == 1
        assert stats["fix_rate"] == 0.5

    def test_sessions_list(self) -> None:
        loop = CIFeedbackLoop()
        ctx = FailureContext(failure_type=FT.TEST_FAILURE, error_message="f")
        loop.create_session(ctx)
        sessions = get_sessions()
        assert len(sessions) == 1

    def test_stats_by_failure_type(self) -> None:
        loop = CIFeedbackLoop()
        ctx = FailureContext(failure_type=FT.LINT_ERROR, error_message="lint")
        s = loop.create_session(ctx)
        loop.record_attempt(s, verification_passed=True)
        stats = get_feedback_stats()
        assert FT.LINT_ERROR in stats["by_failure_type"]
        assert stats["by_failure_type"][FT.LINT_ERROR]["fixed"] == 1
