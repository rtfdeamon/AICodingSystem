"""CI Feedback Loop — feeds CI/CD results back to AI agents for self-correction.

Implements the inner/outer feedback loop pattern:
  - Inner loop: Fast validation (lint, type check, unit tests) before push
  - Outer loop: Full CI pipeline results feed back into agent for fixes

When CI fails, the feedback loop:
  1. Parses failure details (test names, error messages, stack traces)
  2. Builds a targeted fix prompt with failure context
  3. Invokes the coding agent with error context for self-correction
  4. Tracks iteration count to prevent runaway loops
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ci.test_runner import TestSuiteResult

logger = logging.getLogger(__name__)

# Maximum number of fix iterations before requiring human intervention
MAX_FIX_ITERATIONS = 3


@dataclass
class CIFeedbackResult:
    """Result of a CI feedback iteration."""

    iteration: int
    fixed: bool
    fix_description: str = ""
    files_changed: list[str] = field(default_factory=list)
    remaining_failures: int = 0
    cost_usd: float = 0.0


@dataclass
class FeedbackLoopSummary:
    """Summary of all CI feedback loop iterations."""

    total_iterations: int = 0
    resolved: bool = False
    iterations: list[CIFeedbackResult] = field(default_factory=list)
    total_cost_usd: float = 0.0
    escalated_to_human: bool = False
    failure_summary: str = ""


def parse_test_failures(test_result: TestSuiteResult) -> list[dict[str, str]]:
    """Extract structured failure details from a test suite result.

    Returns a list of dicts with keys: test_name, error_message, file, line.
    """
    failures: list[dict[str, str]] = []

    # Parse from JSON report if available
    if test_result.report_json:
        tests = test_result.report_json.get("tests", [])
        for test in tests:
            outcome = test.get("outcome", "")
            if outcome in ("failed", "error"):
                failure = {
                    "test_name": test.get("nodeid", "unknown"),
                    "error_message": "",
                    "file": "",
                    "line": "",
                }
                # Extract error message from call info
                call_info = test.get("call", {})
                if isinstance(call_info, dict):
                    crash = call_info.get("crash", {})
                    failure["error_message"] = call_info.get("longrepr", "")[:2000]
                    if isinstance(crash, dict):
                        failure["file"] = crash.get("path", "")
                        failure["line"] = str(crash.get("lineno", ""))
                failures.append(failure)

    # Fallback: parse from log output
    if not failures and test_result.log_output:
        current_failure: dict[str, str] | None = None
        for raw_line in test_result.log_output.splitlines():
            line = raw_line.strip()
            if line.startswith("FAILED "):
                if current_failure:
                    failures.append(current_failure)
                test_name = line.removeprefix("FAILED ").split(" ")[0]
                current_failure = {
                    "test_name": test_name,
                    "error_message": "",
                    "file": "",
                    "line": "",
                }
            elif current_failure and (
                "Error" in line or "assert" in line.lower()
            ):
                current_failure["error_message"] += line + "\n"
        if current_failure:
            failures.append(current_failure)

    return failures


def build_fix_prompt(
    failures: list[dict[str, str]],
    diff: str,
    iteration: int,
    previous_attempts: list[str] | None = None,
) -> str:
    """Build a targeted prompt for the coding agent to fix CI failures.

    Parameters
    ----------
    failures:
        Parsed test failure details.
    diff:
        The current code diff that caused failures.
    iteration:
        Current fix iteration (1-based).
    previous_attempts:
        Descriptions of previous fix attempts (for progressive context).
    """
    prompt_parts = [
        f"## CI Fix Request (Iteration {iteration}/{MAX_FIX_ITERATIONS})\n",
        "The following tests are failing after code generation. "
        "Fix the code to make all tests pass.\n\n",
    ]

    # Add failure details
    prompt_parts.append("### Failing Tests\n")
    for i, f in enumerate(failures[:10], 1):  # Limit to 10 failures
        prompt_parts.append(f"**{i}. {f['test_name']}**\n")
        if f.get("file"):
            prompt_parts.append(f"  File: {f['file']}")
            if f.get("line"):
                prompt_parts.append(f":{f['line']}")
            prompt_parts.append("\n")
        if f.get("error_message"):
            error_excerpt = f["error_message"][:500]
            prompt_parts.append(f"  Error: ```\n{error_excerpt}\n```\n")
        prompt_parts.append("\n")

    # Add current diff context
    prompt_parts.append(f"### Current Code Diff\n```\n{diff[:20_000]}\n```\n")

    # Add progressive context from previous attempts
    if previous_attempts:
        prompt_parts.append("\n### Previous Fix Attempts (all failed)\n")
        for idx, attempt_desc in enumerate(previous_attempts, 1):
            prompt_parts.append(f"**Attempt {idx}:** {attempt_desc}\n")
        prompt_parts.append(
            "\nDo NOT repeat the same fixes. Try a different approach.\n"
        )

    prompt_parts.append(
        "\n### Instructions\n"
        "1. Analyze each failing test to understand what it expects\n"
        "2. Identify the root cause in the generated code\n"
        "3. Produce corrected code that passes all tests\n"
        "4. Only modify files that are relevant to the failures\n"
    )

    return "".join(prompt_parts)


async def run_ci_feedback_loop(
    test_result: TestSuiteResult,
    diff: str,
    fix_callback: Any,
    *,
    db: AsyncSession | None = None,
    ticket_id: uuid.UUID | None = None,
    max_iterations: int = MAX_FIX_ITERATIONS,
) -> FeedbackLoopSummary:
    """Run the CI feedback loop until tests pass or max iterations reached.

    Parameters
    ----------
    test_result:
        Initial failing test results.
    diff:
        The code diff that caused failures.
    fix_callback:
        Async callable(prompt, iteration) -> CIFeedbackResult.
        The orchestrator provides this to apply fixes and re-run tests.
    db:
        Optional database session.
    ticket_id:
        Optional ticket ID for logging.
    max_iterations:
        Maximum fix attempts before escalating to human.

    Returns
    -------
    FeedbackLoopSummary with all iteration details.
    """
    summary = FeedbackLoopSummary()
    previous_attempts: list[str] = []
    current_result = test_result

    for iteration in range(1, max_iterations + 1):
        failures = parse_test_failures(current_result)

        if not failures:
            # No parseable failures — tests may have passed or error is unparseable
            if current_result.passed:
                summary.resolved = True
                break
            # Unparseable failure — escalate
            summary.escalated_to_human = True
            summary.failure_summary = (
                f"CI failed but failures could not be parsed. "
                f"Log: {current_result.log_output[:500]}"
            )
            break

        prompt = build_fix_prompt(failures, diff, iteration, previous_attempts)

        logger.info(
            "CI feedback loop iteration %d/%d for ticket %s — %d failure(s)",
            iteration,
            max_iterations,
            ticket_id,
            len(failures),
        )

        try:
            feedback_result: CIFeedbackResult = await fix_callback(prompt, iteration)
            feedback_result.iteration = iteration
            summary.iterations.append(feedback_result)
            summary.total_cost_usd += feedback_result.cost_usd
            previous_attempts.append(feedback_result.fix_description)

            if feedback_result.fixed:
                summary.resolved = True
                break

            # Update remaining failures count
            feedback_result.remaining_failures = len(failures)

        except Exception as exc:
            logger.error(
                "CI feedback iteration %d failed for ticket %s: %s",
                iteration,
                ticket_id,
                exc,
            )
            summary.iterations.append(
                CIFeedbackResult(
                    iteration=iteration,
                    fixed=False,
                    fix_description=f"Error: {exc}",
                )
            )
            break

    summary.total_iterations = len(summary.iterations)

    if not summary.resolved and not summary.escalated_to_human:
        summary.escalated_to_human = True
        summary.failure_summary = (
            f"Failed to fix after {summary.total_iterations} iteration(s). "
            f"Escalating to human review."
        )
        logger.warning(
            "CI feedback loop exhausted for ticket %s after %d iterations",
            ticket_id,
            summary.total_iterations,
        )

    return summary


def feedback_summary_to_json(summary: FeedbackLoopSummary) -> dict[str, Any]:
    """Serialize a FeedbackLoopSummary to JSON-compatible dict."""
    return {
        "total_iterations": summary.total_iterations,
        "resolved": summary.resolved,
        "escalated_to_human": summary.escalated_to_human,
        "total_cost_usd": summary.total_cost_usd,
        "failure_summary": summary.failure_summary,
        "iterations": [
            {
                "iteration": it.iteration,
                "fixed": it.fixed,
                "fix_description": it.fix_description,
                "files_changed": it.files_changed,
                "remaining_failures": it.remaining_failures,
                "cost_usd": it.cost_usd,
            }
            for it in summary.iterations
        ],
    }
