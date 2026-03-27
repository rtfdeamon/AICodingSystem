"""CI Feedback Loop — feed CI/test failures back to AI agents for auto-correction.

When a CI pipeline or test suite fails after AI-generated code is merged, this
module captures the failure context (error messages, stack traces, affected
files), structures it into an actionable prompt, and routes it back to the
originating AI agent for a self-correction attempt.

Implements exponential back-off retry with a configurable attempt budget so the
system doesn't loop forever, and records every attempt for observability.

Key features:
- Parse CI failure output into structured FailureContext
- Classify failure type: test, lint, type-check, build, runtime
- Generate targeted correction prompts from failure context
- Retry budget with exponential backoff (max 3 attempts by default)
- Full attempt history with diffs for audit
- Success-rate analytics across failure types
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class FailureType(StrEnum):
    TEST_FAILURE = "test_failure"
    LINT_ERROR = "lint_error"
    TYPE_ERROR = "type_error"
    BUILD_ERROR = "build_error"
    RUNTIME_ERROR = "runtime_error"
    IMPORT_ERROR = "import_error"
    SECURITY_SCAN = "security_scan"
    UNKNOWN = "unknown"


class CorrectionStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    FIXED = "fixed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class FailureContext:
    """Structured representation of a CI/test failure."""

    failure_type: FailureType
    error_message: str
    stack_trace: str = ""
    affected_files: list[str] = field(default_factory=list)
    test_name: str = ""
    ci_job: str = ""
    exit_code: int = 1
    raw_output: str = ""


@dataclass
class CorrectionAttempt:
    """Record of a single auto-correction attempt."""

    attempt_number: int
    prompt_used: str
    proposed_diff: str = ""
    verification_passed: bool = False
    error_after: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class FeedbackSession:
    """End-to-end record of a CI feedback loop session."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    failure: FailureContext | None = None
    status: CorrectionStatus = CorrectionStatus.PENDING
    attempts: list[CorrectionAttempt] = field(default_factory=list)
    max_attempts: int = 3
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    resolved_at: str | None = None

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def is_resolved(self) -> bool:
        return self.status == CorrectionStatus.FIXED


# ── Failure classifier ───────────────────────────────────────────────────

_FAILURE_PATTERNS: list[tuple[str, FailureType]] = [
    ("FAILED", FailureType.TEST_FAILURE),
    ("AssertionError", FailureType.TEST_FAILURE),
    ("assert ", FailureType.TEST_FAILURE),
    ("ModuleNotFoundError", FailureType.IMPORT_ERROR),
    ("ImportError", FailureType.IMPORT_ERROR),
    ("SyntaxError", FailureType.BUILD_ERROR),
    ("RuntimeError", FailureType.RUNTIME_ERROR),
    ("TypeError", FailureType.RUNTIME_ERROR),
    ("ValueError", FailureType.RUNTIME_ERROR),
    ("mypy", FailureType.TYPE_ERROR),
    ("error: ", FailureType.TYPE_ERROR),
    ("ruff", FailureType.LINT_ERROR),
    ("eslint", FailureType.LINT_ERROR),
    ("flake8", FailureType.LINT_ERROR),
    ("bandit", FailureType.SECURITY_SCAN),
    ("vulnerability", FailureType.SECURITY_SCAN),
]


def classify_failure(output: str) -> FailureType:
    """Classify a CI failure from its raw output."""
    lower = output.lower()
    for pattern, ftype in _FAILURE_PATTERNS:
        if pattern.lower() in lower:
            return ftype
    return FailureType.UNKNOWN


def parse_failure_output(
    raw_output: str,
    *,
    ci_job: str = "",
    exit_code: int = 1,
) -> FailureContext:
    """Parse raw CI output into a structured FailureContext."""
    failure_type = classify_failure(raw_output)

    # Extract error message (first line with 'error' or 'FAILED')
    error_message = ""
    stack_lines: list[str] = []
    affected: set[str] = set()
    test_name = ""

    for line in raw_output.splitlines():
        stripped = line.strip()
        if not error_message and ("error" in stripped.lower() or "FAILED" in stripped):
            error_message = stripped[:500]
        if stripped.startswith("File "):
            # Python traceback line
            stack_lines.append(stripped)
            # Extract filename
            parts = stripped.split('"')
            if len(parts) >= 2:
                affected.add(parts[1])
        if stripped.startswith("FAILED "):
            test_name = stripped.replace("FAILED ", "").split("[")[0].strip()

    return FailureContext(
        failure_type=failure_type,
        error_message=error_message or raw_output[:300],
        stack_trace="\n".join(stack_lines[-10:]),
        affected_files=sorted(affected),
        test_name=test_name,
        ci_job=ci_job,
        exit_code=exit_code,
        raw_output=raw_output[:5000],
    )


# ── Prompt generator ─────────────────────────────────────────────────────

_PROMPT_TEMPLATES: dict[FailureType, str] = {
    FailureType.TEST_FAILURE: (
        "The following test failed after your code change:\n"
        "Test: {test_name}\n"
        "Error: {error_message}\n"
        "Stack trace:\n{stack_trace}\n\n"
        "Affected files: {affected_files}\n\n"
        "Please fix the code so the test passes. "
        "Only change what is necessary — do not refactor unrelated code."
    ),
    FailureType.LINT_ERROR: (
        "Linting failed with the following error:\n"
        "{error_message}\n\n"
        "Affected files: {affected_files}\n\n"
        "Fix the lint violation(s). Follow the project's style guide."
    ),
    FailureType.TYPE_ERROR: (
        "Type checking failed:\n"
        "{error_message}\n\n"
        "Affected files: {affected_files}\n\n"
        "Fix the type errors. Ensure all function signatures and return types are correct."
    ),
    FailureType.BUILD_ERROR: (
        "Build failed:\n"
        "{error_message}\n"
        "{stack_trace}\n\n"
        "Affected files: {affected_files}\n\n"
        "Fix the build error."
    ),
    FailureType.IMPORT_ERROR: (
        "Import error detected:\n"
        "{error_message}\n\n"
        "Ensure the module exists and is listed in requirements."
    ),
    FailureType.SECURITY_SCAN: (
        "Security scan found issues:\n"
        "{error_message}\n\n"
        "Affected files: {affected_files}\n\n"
        "Fix the security vulnerabilities without changing functionality."
    ),
}

_DEFAULT_TEMPLATE = (
    "CI failed with the following output:\n"
    "{error_message}\n"
    "{stack_trace}\n\n"
    "Affected files: {affected_files}\n\n"
    "Please diagnose and fix the issue."
)


def generate_correction_prompt(failure: FailureContext) -> str:
    """Create a targeted correction prompt from failure context."""
    template = _PROMPT_TEMPLATES.get(failure.failure_type, _DEFAULT_TEMPLATE)
    return template.format(
        test_name=failure.test_name,
        error_message=failure.error_message,
        stack_trace=failure.stack_trace,
        affected_files=", ".join(failure.affected_files) or "(unknown)",
    )


# ── Session manager ──────────────────────────────────────────────────────

_sessions: list[FeedbackSession] = []


class CIFeedbackLoop:
    """Manages the lifecycle of CI failure → AI correction → verification."""

    def __init__(self, *, max_attempts: int = 3) -> None:
        self.max_attempts = max_attempts

    def create_session(self, failure: FailureContext) -> FeedbackSession:
        """Start a new feedback session for a CI failure."""
        session = FeedbackSession(
            failure=failure,
            max_attempts=self.max_attempts,
            status=CorrectionStatus.PENDING,
        )
        _sessions.append(session)
        logger.info("CI feedback session %s created for %s", session.id, failure.failure_type)
        return session

    def record_attempt(
        self,
        session: FeedbackSession,
        *,
        proposed_diff: str = "",
        verification_passed: bool = False,
        error_after: str = "",
    ) -> CorrectionAttempt:
        """Record a correction attempt in the session."""
        attempt = CorrectionAttempt(
            attempt_number=session.attempt_count + 1,
            prompt_used=generate_correction_prompt(session.failure) if session.failure else "",
            proposed_diff=proposed_diff,
            verification_passed=verification_passed,
            error_after=error_after,
        )
        session.attempts.append(attempt)

        if verification_passed:
            session.status = CorrectionStatus.FIXED
            session.resolved_at = datetime.now(UTC).isoformat()
            logger.info("Session %s fixed on attempt %d", session.id, attempt.attempt_number)
        elif session.attempt_count >= session.max_attempts:
            session.status = CorrectionStatus.FAILED
            logger.warning(
                "Session %s exhausted %d attempts", session.id, session.max_attempts,
            )
        else:
            session.status = CorrectionStatus.IN_PROGRESS

        return attempt

    def should_retry(self, session: FeedbackSession) -> bool:
        """Check if the session still has retry budget."""
        terminal = (
            CorrectionStatus.FIXED,
            CorrectionStatus.FAILED,
            CorrectionStatus.SKIPPED,
        )
        return (
            session.status not in terminal
            and session.attempt_count < session.max_attempts
        )

    def skip_session(self, session: FeedbackSession, *, reason: str = "") -> None:
        """Mark a session as skipped (e.g. human decided to fix manually)."""
        session.status = CorrectionStatus.SKIPPED
        logger.info("Session %s skipped: %s", session.id, reason)

    @staticmethod
    def get_backoff_seconds(attempt: int) -> float:
        """Exponential backoff: 2^attempt seconds (2, 4, 8, …)."""
        return min(2 ** attempt, 60)


# ── Analytics ────────────────────────────────────────────────────────────

def get_sessions() -> list[FeedbackSession]:
    return list(_sessions)


def get_feedback_stats() -> dict[str, Any]:
    """Aggregate analytics across all feedback sessions."""
    if not _sessions:
        return {"total_sessions": 0}

    total = len(_sessions)
    fixed = sum(1 for s in _sessions if s.status == CorrectionStatus.FIXED)
    failed = sum(1 for s in _sessions if s.status == CorrectionStatus.FAILED)
    skipped = sum(1 for s in _sessions if s.status == CorrectionStatus.SKIPPED)

    # Per failure-type stats
    by_type: dict[str, dict[str, int]] = {}
    for s in _sessions:
        ft = s.failure.failure_type if s.failure else FailureType.UNKNOWN
        if ft not in by_type:
            by_type[ft] = {"total": 0, "fixed": 0}
        by_type[ft]["total"] += 1
        if s.status == CorrectionStatus.FIXED:
            by_type[ft]["fixed"] += 1

    total_attempts = sum(s.attempt_count for s in _sessions)
    avg_attempts = total_attempts / total if total else 0

    return {
        "total_sessions": total,
        "fixed": fixed,
        "failed": failed,
        "skipped": skipped,
        "fix_rate": fixed / total if total else 0,
        "avg_attempts_per_session": round(avg_attempts, 2),
        "by_failure_type": by_type,
    }


def clear_sessions() -> None:
    _sessions.clear()
