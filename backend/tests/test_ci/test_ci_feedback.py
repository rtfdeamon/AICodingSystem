"""Tests for app.ci.ci_feedback — CI feedback loop for self-correction."""

from __future__ import annotations

import pytest

from app.ci.ci_feedback import (
    CIFeedbackResult,
    FeedbackLoopSummary,
    build_fix_prompt,
    feedback_summary_to_json,
    parse_test_failures,
    run_ci_feedback_loop,
)
from app.ci.test_runner import TestSuiteResult

# ---------------------------------------------------------------------------
# parse_test_failures
# ---------------------------------------------------------------------------


def test_parse_failures_from_json_report():
    report = {
        "tests": [
            {
                "nodeid": "tests/test_foo.py::test_bar",
                "outcome": "failed",
                "call": {
                    "longrepr": "AssertionError: expected 42 got 0",
                    "crash": {"path": "tests/test_foo.py", "lineno": 15},
                },
            },
            {
                "nodeid": "tests/test_foo.py::test_ok",
                "outcome": "passed",
            },
        ]
    }
    result = TestSuiteResult(
        passed=False,
        total=2,
        failed=1,
        report_json=report,
    )
    failures = parse_test_failures(result)
    assert len(failures) == 1
    assert failures[0]["test_name"] == "tests/test_foo.py::test_bar"
    assert "AssertionError" in failures[0]["error_message"]
    assert failures[0]["file"] == "tests/test_foo.py"
    assert failures[0]["line"] == "15"


def test_parse_failures_from_log_output():
    log = (
        "FAILED tests/test_a.py::test_x - AssertionError\n"
        "FAILED tests/test_b.py::test_y - ValueError: bad input\n"
    )
    result = TestSuiteResult(
        passed=False,
        total=2,
        failed=2,
        log_output=log,
    )
    failures = parse_test_failures(result)
    assert len(failures) == 2
    assert failures[0]["test_name"] == "tests/test_a.py::test_x"
    assert failures[1]["test_name"] == "tests/test_b.py::test_y"


def test_parse_failures_empty_result():
    result = TestSuiteResult(passed=True, total=5, failed=0)
    failures = parse_test_failures(result)
    assert failures == []


def test_parse_failures_json_error_outcome():
    report = {
        "tests": [
            {
                "nodeid": "tests/test_crash.py::test_boom",
                "outcome": "error",
                "call": {
                    "longrepr": "RuntimeError: explosion",
                },
            }
        ]
    }
    result = TestSuiteResult(
        passed=False,
        total=1,
        failed=1,
        report_json=report,
    )
    failures = parse_test_failures(result)
    assert len(failures) == 1
    assert "RuntimeError" in failures[0]["error_message"]


def test_parse_failures_log_with_assert_details():
    log = (
        "FAILED tests/test_calc.py::test_add\n"
        "assert 2 + 2 == 5\n"
        "AssertionError: 4 != 5\n"
    )
    result = TestSuiteResult(passed=False, total=1, failed=1, log_output=log)
    failures = parse_test_failures(result)
    assert len(failures) == 1
    assert "assert" in failures[0]["error_message"].lower()


# ---------------------------------------------------------------------------
# build_fix_prompt
# ---------------------------------------------------------------------------


def test_build_fix_prompt_basic():
    failures = [
        {
            "test_name": "tests/test_foo.py::test_bar",
            "error_message": "AssertionError: got None",
            "file": "tests/test_foo.py",
            "line": "42",
        }
    ]
    prompt = build_fix_prompt(failures, "diff content", iteration=1)
    assert "Iteration 1" in prompt
    assert "test_foo.py::test_bar" in prompt
    assert "AssertionError" in prompt
    assert "diff content" in prompt


def test_build_fix_prompt_with_previous_attempts():
    failures = [{"test_name": "test_x", "error_message": "fail", "file": "", "line": ""}]
    prompt = build_fix_prompt(
        failures,
        "diff",
        iteration=2,
        previous_attempts=["Added null check", "Changed return type"],
    )
    assert "Previous Fix Attempts" in prompt
    assert "Added null check" in prompt
    assert "Changed return type" in prompt
    assert "different approach" in prompt


def test_build_fix_prompt_limits_failures():
    failures = [
        {"test_name": f"test_{i}", "error_message": f"error {i}", "file": "", "line": ""}
        for i in range(20)
    ]
    prompt = build_fix_prompt(failures, "diff", iteration=1)
    # Should limit to 10 failures
    assert "test_0" in prompt
    assert "test_9" in prompt
    assert "test_10" not in prompt


def test_build_fix_prompt_truncates_long_diff():
    long_diff = "x" * 50_000
    prompt = build_fix_prompt(
        [{"test_name": "t", "error_message": "e", "file": "", "line": ""}],
        long_diff,
        iteration=1,
    )
    # Diff should be truncated to 20_000 chars
    assert len(prompt) < 50_000 + 5_000  # prompt overhead


# ---------------------------------------------------------------------------
# run_ci_feedback_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_loop_resolved_first_iteration():
    test_result = TestSuiteResult(
        passed=False,
        total=5,
        failed=1,
        log_output="FAILED tests/test_a.py::test_x - AssertionError\n",
    )

    async def fix_callback(prompt, iteration):
        return CIFeedbackResult(
            iteration=iteration,
            fixed=True,
            fix_description="Fixed the null check",
            files_changed=["app/foo.py"],
            cost_usd=0.02,
        )

    summary = await run_ci_feedback_loop(
        test_result=test_result,
        diff="some diff",
        fix_callback=fix_callback,
    )
    assert summary.resolved is True
    assert summary.total_iterations == 1
    assert summary.escalated_to_human is False
    assert summary.total_cost_usd == 0.02


@pytest.mark.asyncio
async def test_feedback_loop_resolved_second_iteration():
    test_result = TestSuiteResult(
        passed=False,
        total=5,
        failed=1,
        log_output="FAILED tests/test_a.py::test_x - AssertionError\n",
    )
    call_count = 0

    async def fix_callback(prompt, iteration):
        nonlocal call_count
        call_count += 1
        return CIFeedbackResult(
            iteration=iteration,
            fixed=(call_count >= 2),
            fix_description=f"Attempt {call_count}",
            cost_usd=0.01,
        )

    summary = await run_ci_feedback_loop(
        test_result=test_result,
        diff="diff",
        fix_callback=fix_callback,
    )
    assert summary.resolved is True
    assert summary.total_iterations == 2
    assert summary.total_cost_usd == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_feedback_loop_exhausted_escalates():
    test_result = TestSuiteResult(
        passed=False,
        total=5,
        failed=1,
        log_output="FAILED tests/test_a.py::test_x - AssertionError\n",
    )

    async def fix_callback(prompt, iteration):
        return CIFeedbackResult(
            iteration=iteration,
            fixed=False,
            fix_description="Still broken",
            cost_usd=0.01,
        )

    summary = await run_ci_feedback_loop(
        test_result=test_result,
        diff="diff",
        fix_callback=fix_callback,
        max_iterations=2,
    )
    assert summary.resolved is False
    assert summary.escalated_to_human is True
    assert summary.total_iterations == 2


@pytest.mark.asyncio
async def test_feedback_loop_tests_already_pass():
    test_result = TestSuiteResult(passed=True, total=5, failed=0)

    async def fix_callback(prompt, iteration):
        raise RuntimeError("Should not be called")

    summary = await run_ci_feedback_loop(
        test_result=test_result,
        diff="diff",
        fix_callback=fix_callback,
    )
    assert summary.resolved is True
    assert summary.total_iterations == 0


@pytest.mark.asyncio
async def test_feedback_loop_callback_exception():
    test_result = TestSuiteResult(
        passed=False,
        total=1,
        failed=1,
        log_output="FAILED tests/test_x.py::test_y - Error\n",
    )

    async def fix_callback(prompt, iteration):
        raise RuntimeError("Agent crashed")

    summary = await run_ci_feedback_loop(
        test_result=test_result,
        diff="diff",
        fix_callback=fix_callback,
    )
    assert summary.resolved is False
    assert summary.total_iterations == 1
    assert "Error" in summary.iterations[0].fix_description


@pytest.mark.asyncio
async def test_feedback_loop_unparseable_failure_escalates():
    test_result = TestSuiteResult(
        passed=False,
        total=0,
        failed=0,
        log_output="Something went horribly wrong",
    )

    async def fix_callback(prompt, iteration):
        raise RuntimeError("Should not be called")

    summary = await run_ci_feedback_loop(
        test_result=test_result,
        diff="diff",
        fix_callback=fix_callback,
    )
    assert summary.resolved is False
    assert summary.escalated_to_human is True
    assert "could not be parsed" in summary.failure_summary


# ---------------------------------------------------------------------------
# feedback_summary_to_json
# ---------------------------------------------------------------------------


def test_feedback_summary_to_json():
    summary = FeedbackLoopSummary(
        total_iterations=2,
        resolved=True,
        iterations=[
            CIFeedbackResult(
                iteration=1,
                fixed=False,
                fix_description="First try",
                files_changed=["a.py"],
                remaining_failures=3,
                cost_usd=0.01,
            ),
            CIFeedbackResult(
                iteration=2,
                fixed=True,
                fix_description="Second try",
                files_changed=["a.py", "b.py"],
                cost_usd=0.02,
            ),
        ],
        total_cost_usd=0.03,
    )
    data = feedback_summary_to_json(summary)
    assert data["total_iterations"] == 2
    assert data["resolved"] is True
    assert len(data["iterations"]) == 2
    assert data["iterations"][0]["fix_description"] == "First try"
    assert data["total_cost_usd"] == 0.03


def test_feedback_summary_to_json_empty():
    summary = FeedbackLoopSummary()
    data = feedback_summary_to_json(summary)
    assert data["total_iterations"] == 0
    assert data["resolved"] is False
    assert data["iterations"] == []
