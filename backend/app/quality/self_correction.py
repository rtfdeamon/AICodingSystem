"""Self-Correction Pipeline -- auto-detect issues and trigger regeneration.

When primary model output fails quality gates, this module orchestrates
a self-correction loop: detect the problem, generate targeted feedback,
re-prompt the model with error context, and validate the revised output.

Key features:
- Multi-stage correction pipeline: detect → diagnose → re-prompt → validate
- Configurable correction strategies per error type
- Max retry budget with escalation to human review
- Correction history and success rate tracking
- Feedback template generation for effective re-prompting
- Circuit breaker to avoid infinite correction loops
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class IssueType(StrEnum):
    SYNTAX_ERROR = "syntax_error"
    TYPE_ERROR = "type_error"
    LOGIC_ERROR = "logic_error"
    SECURITY_ISSUE = "security_issue"
    INCOMPLETE_OUTPUT = "incomplete_output"
    WRONG_FORMAT = "wrong_format"
    HALLUCINATED_API = "hallucinated_api"
    STYLE_VIOLATION = "style_violation"
    TEST_FAILURE = "test_failure"
    MISSING_ERROR_HANDLING = "missing_error_handling"


class CorrectionStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    FIXED = "fixed"
    PARTIALLY_FIXED = "partially_fixed"
    UNFIXABLE = "unfixable"
    ESCALATED = "escalated"


class PipelineState(StrEnum):
    IDLE = "idle"
    DETECTING = "detecting"
    DIAGNOSING = "diagnosing"
    CORRECTING = "correcting"
    VALIDATING = "validating"
    COMPLETE = "complete"
    ESCALATED = "escalated"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class DetectedIssue:
    """An issue detected in model output."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    issue_type: IssueType = IssueType.LOGIC_ERROR
    severity: int = 5  # 1-10
    description: str = ""
    location: str = ""  # file:line or snippet
    suggested_fix: str = ""


@dataclass
class CorrectionAttempt:
    """Record of a single correction attempt."""
    attempt_number: int = 0
    issues_targeted: list[str] = field(default_factory=list)  # issue IDs
    feedback_prompt: str = ""
    original_hash: str = ""
    corrected_hash: str = ""
    issues_resolved: list[str] = field(default_factory=list)
    issues_remaining: list[str] = field(default_factory=list)
    new_issues: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class CorrectionSession:
    """Complete correction session tracking all attempts."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_output: str = ""
    final_output: str = ""
    status: CorrectionStatus = CorrectionStatus.PENDING
    detected_issues: list[DetectedIssue] = field(default_factory=list)
    attempts: list[CorrectionAttempt] = field(default_factory=list)
    total_issues_found: int = 0
    total_issues_fixed: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    escalation_reason: str | None = None


@dataclass
class CorrectionStrategy:
    """Strategy for correcting a specific issue type."""
    issue_type: IssueType
    max_retries: int = 3
    feedback_template: str = ""
    auto_fixable: bool = True
    escalate_after: int = 2  # escalate after N failed attempts


# ── Detectors ────────────────────────────────────────────────────────────

class IssueDetector:
    """Detects common issues in AI-generated code output."""

    SYNTAX_PATTERNS = [
        (r"SyntaxError:", "Python syntax error detected"),
        (r"Unexpected token", "JavaScript syntax error detected"),
        (r"}\s*$(?!.*{)", "Possible unclosed brace"),
    ]

    SECURITY_PATTERNS = [
        (r"eval\(", "Use of eval() is a security risk"),
        (r"exec\(", "Use of exec() is a security risk"),
        (r"subprocess\.call\(.*shell\s*=\s*True", "Shell injection risk"),
        (r"pickle\.loads?\(", "Pickle deserialization risk"),
        (r"__import__\(", "Dynamic import is a security risk"),
        (r"os\.system\(", "os.system() is a security risk"),
        (r"SELECT.*\+.*input|f['\"]SELECT", "Possible SQL injection"),
        (r"innerHTML\s*=", "Possible XSS via innerHTML"),
    ]

    QUALITY_PATTERNS = [
        (r"pass\s*$", "Empty pass statement — missing implementation"),
        (r"TODO|FIXME|HACK|XXX", "Unresolved marker in output"),
        (r"\.\.\.\s*$", "Ellipsis placeholder — incomplete code"),
        (r"raise NotImplementedError", "Not implemented placeholder"),
    ]

    def detect(self, code: str, context: dict[str, Any] | None = None) -> list[DetectedIssue]:
        import re
        issues: list[DetectedIssue] = []
        lines = code.splitlines()

        for i, line in enumerate(lines, 1):
            for pattern, desc in self.SECURITY_PATTERNS:
                if re.search(pattern, line):
                    issues.append(DetectedIssue(
                        issue_type=IssueType.SECURITY_ISSUE,
                        severity=8,
                        description=desc,
                        location=f"line:{i}",
                        suggested_fix=f"Remove or replace unsafe pattern at line {i}",
                    ))

            for pattern, desc in self.QUALITY_PATTERNS:
                if re.search(pattern, line):
                    issues.append(DetectedIssue(
                        issue_type=IssueType.INCOMPLETE_OUTPUT,
                        severity=5,
                        description=desc,
                        location=f"line:{i}",
                    ))

        # Check for truncated output
        stripped = code.rstrip()
        if stripped and not self._is_complete(stripped):
            issues.append(DetectedIssue(
                issue_type=IssueType.INCOMPLETE_OUTPUT,
                severity=7,
                description="Output appears truncated",
                location="end",
                suggested_fix="Request continuation of the output",
            ))

        # Check for missing error handling
        if "def " in code and "try" not in code and "except" not in code:
            fn_count = code.count("def ")
            if fn_count >= 3:
                issues.append(DetectedIssue(
                    issue_type=IssueType.MISSING_ERROR_HANDLING,
                    severity=4,
                    description=f"{fn_count} functions with no error handling",
                    location="global",
                    suggested_fix="Add try/except blocks for external calls",
                ))

        return issues

    def _is_complete(self, code: str) -> bool:
        opens = code.count("{") + code.count("[") + code.count("(")
        closes = code.count("}") + code.count("]") + code.count(")")
        # Allow small imbalance for string literals
        return abs(opens - closes) <= 1


# ── Pipeline ─────────────────────────────────────────────────────────────

class SelfCorrectionPipeline:
    """Orchestrates detect → diagnose → correct → validate loops."""

    _SYNTAX_TPL = (
        "The code has a syntax error: {description} "
        "at {location}. Please fix it."
    )
    _SECURITY_TPL = (
        "Security issue detected: {description}. "
        "Replace with a safe alternative."
    )
    _INCOMPLETE_TPL = (
        "The output is incomplete: {description}. "
        "Please provide the complete implementation."
    )
    _ERR_HANDLING_TPL = (
        "Missing error handling: {description}. "
        "Add appropriate try/except blocks."
    )
    _STYLE_TPL = (
        "Style violation: {description}. "
        "Please follow the project's style guide."
    )

    DEFAULT_STRATEGIES: dict[IssueType, CorrectionStrategy] = {
        IssueType.SYNTAX_ERROR: CorrectionStrategy(
            issue_type=IssueType.SYNTAX_ERROR,
            max_retries=3,
            feedback_template=_SYNTAX_TPL,
            auto_fixable=True,
        ),
        IssueType.SECURITY_ISSUE: CorrectionStrategy(
            issue_type=IssueType.SECURITY_ISSUE,
            max_retries=2,
            feedback_template=_SECURITY_TPL,
            auto_fixable=True,
            escalate_after=1,
        ),
        IssueType.INCOMPLETE_OUTPUT: CorrectionStrategy(
            issue_type=IssueType.INCOMPLETE_OUTPUT,
            max_retries=2,
            feedback_template=_INCOMPLETE_TPL,
            auto_fixable=True,
        ),
        IssueType.LOGIC_ERROR: CorrectionStrategy(
            issue_type=IssueType.LOGIC_ERROR,
            max_retries=2,
            feedback_template=(
                "Logic error: {description}. "
                "Please review and fix the logic."
            ),
            auto_fixable=False,
            escalate_after=1,
        ),
        IssueType.HALLUCINATED_API: CorrectionStrategy(
            issue_type=IssueType.HALLUCINATED_API,
            max_retries=2,
            feedback_template=(
                "The API call '{description}' does not exist. "
                "Use the correct API."
            ),
            auto_fixable=True,
        ),
        IssueType.MISSING_ERROR_HANDLING: CorrectionStrategy(
            issue_type=IssueType.MISSING_ERROR_HANDLING,
            max_retries=2,
            feedback_template=_ERR_HANDLING_TPL,
            auto_fixable=True,
        ),
        IssueType.TEST_FAILURE: CorrectionStrategy(
            issue_type=IssueType.TEST_FAILURE,
            max_retries=3,
            feedback_template=(
                "Test failed: {description}. "
                "Fix the code to pass the test."
            ),
            auto_fixable=True,
        ),
        IssueType.WRONG_FORMAT: CorrectionStrategy(
            issue_type=IssueType.WRONG_FORMAT,
            max_retries=2,
            feedback_template=(
                "Wrong output format: {description}. "
                "Please use the correct format."
            ),
            auto_fixable=True,
        ),
        IssueType.STYLE_VIOLATION: CorrectionStrategy(
            issue_type=IssueType.STYLE_VIOLATION,
            max_retries=1,
            feedback_template=_STYLE_TPL,
            auto_fixable=True,
        ),
        IssueType.TYPE_ERROR: CorrectionStrategy(
            issue_type=IssueType.TYPE_ERROR,
            max_retries=2,
            feedback_template=(
                "Type error: {description}. "
                "Fix the type annotations and usage."
            ),
            auto_fixable=True,
        ),
    }

    def __init__(
        self,
        *,
        detector: IssueDetector | None = None,
        strategies: dict[IssueType, CorrectionStrategy] | None = None,
        max_attempts: int = 3,
        circuit_breaker_threshold: int = 5,
    ) -> None:
        self._detector = detector or IssueDetector()
        self._strategies = strategies or dict(self.DEFAULT_STRATEGIES)
        self._max_attempts = max_attempts
        self._circuit_breaker_threshold = circuit_breaker_threshold
        self._consecutive_failures = 0
        self._circuit_open = False
        self._sessions: list[CorrectionSession] = []

    # ── Configuration ────────────────────────────────────────────────

    def set_strategy(self, strategy: CorrectionStrategy) -> None:
        self._strategies[strategy.issue_type] = strategy

    @property
    def is_circuit_open(self) -> bool:
        return self._circuit_open

    def reset_circuit(self) -> None:
        self._circuit_open = False
        self._consecutive_failures = 0

    # ── Pipeline execution ───────────────────────────────────────────

    def detect(self, code: str, context: dict[str, Any] | None = None) -> list[DetectedIssue]:
        return self._detector.detect(code, context)

    def generate_feedback(self, issues: list[DetectedIssue]) -> str:
        if not issues:
            return ""

        parts: list[str] = [
            "The following issues were detected in your output. Please fix them:\n"
        ]
        for i, issue in enumerate(issues, 1):
            strategy = self._strategies.get(issue.issue_type)
            if strategy and strategy.feedback_template:
                msg = strategy.feedback_template.format(
                    description=issue.description,
                    location=issue.location,
                )
            else:
                msg = f"{issue.issue_type}: {issue.description}"
            parts.append(f"{i}. [{issue.severity}/10] {msg}")
            if issue.suggested_fix:
                parts.append(f"   Suggested: {issue.suggested_fix}")

        return "\n".join(parts)

    def start_session(self, original_output: str) -> CorrectionSession:
        issues = self._detector.detect(original_output)
        session = CorrectionSession(
            original_output=original_output,
            final_output=original_output,
            detected_issues=issues,
            total_issues_found=len(issues),
            status=(
                CorrectionStatus.PENDING if issues
                else CorrectionStatus.FIXED
            ),
        )
        if not issues:
            session.completed_at = datetime.now(UTC).isoformat()
        self._sessions.append(session)
        return session

    def record_attempt(
        self,
        session: CorrectionSession,
        corrected_output: str,
    ) -> CorrectionAttempt:
        if self._circuit_open:
            session.status = CorrectionStatus.ESCALATED
            session.escalation_reason = "Circuit breaker open — too many consecutive failures"
            session.completed_at = datetime.now(UTC).isoformat()
            return CorrectionAttempt(
                attempt_number=len(session.attempts) + 1,
                issues_remaining=[i.id for i in session.detected_issues],
            )

        attempt_num = len(session.attempts) + 1

        if attempt_num > self._max_attempts:
            session.status = CorrectionStatus.ESCALATED
            session.escalation_reason = f"Max attempts ({self._max_attempts}) exceeded"
            session.completed_at = datetime.now(UTC).isoformat()
            return CorrectionAttempt(
                attempt_number=attempt_num,
                issues_remaining=[i.id for i in session.detected_issues],
            )

        # Detect new issues in corrected output
        new_issues = self._detector.detect(corrected_output)
        old_ids = {i.id for i in session.detected_issues}

        original_hash = hashlib.sha256(session.final_output.encode()).hexdigest()[:16]
        corrected_hash = hashlib.sha256(corrected_output.encode()).hexdigest()[:16]

        # Issues from previous round that aren't in the new round => resolved
        resolved = [i.id for i in session.detected_issues
                     if not any(n.description == i.description for n in new_issues)]
        remaining = [i.id for i in session.detected_issues
                     if any(n.description == i.description for n in new_issues)]
        truly_new = [i.id for i in new_issues
                     if not any(o.description == i.description for o in session.detected_issues)]

        attempt = CorrectionAttempt(
            attempt_number=attempt_num,
            issues_targeted=[i.id for i in session.detected_issues],
            feedback_prompt=self.generate_feedback(session.detected_issues),
            original_hash=original_hash,
            corrected_hash=corrected_hash,
            issues_resolved=resolved,
            issues_remaining=remaining,
            new_issues=truly_new,
        )
        session.attempts.append(attempt)
        session.final_output = corrected_output
        session.detected_issues = new_issues
        session.total_issues_fixed += len(resolved)

        if not new_issues:
            session.status = CorrectionStatus.FIXED
            session.completed_at = datetime.now(UTC).isoformat()
            self._consecutive_failures = 0
        elif len(new_issues) < len(old_ids):
            session.status = CorrectionStatus.PARTIALLY_FIXED
        else:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._circuit_breaker_threshold:
                self._circuit_open = True
                session.status = CorrectionStatus.ESCALATED
                session.escalation_reason = "Circuit breaker tripped"
                session.completed_at = datetime.now(UTC).isoformat()

        # Check per-type escalation
        for issue in new_issues:
            strategy = self._strategies.get(issue.issue_type)
            if (
                strategy
                and attempt_num >= strategy.escalate_after
                and not strategy.auto_fixable
            ):
                    session.status = CorrectionStatus.ESCALATED
                    session.escalation_reason = (
                        f"Issue type {issue.issue_type} requires human review"
                    )
                    session.completed_at = datetime.now(UTC).isoformat()
                    break

        return attempt

    # ── Analytics ────────────────────────────────────────────────────

    @property
    def sessions(self) -> list[CorrectionSession]:
        return list(self._sessions)

    def clear_sessions(self) -> int:
        count = len(self._sessions)
        self._sessions.clear()
        return count

    def success_rate(self) -> float | None:
        completed = [
            s for s in self._sessions
            if s.status in (CorrectionStatus.FIXED, CorrectionStatus.PARTIALLY_FIXED,
                           CorrectionStatus.UNFIXABLE, CorrectionStatus.ESCALATED)
        ]
        if not completed:
            return None
        fixed = sum(1 for s in completed if s.status == CorrectionStatus.FIXED)
        return round(fixed / len(completed), 4)

    def avg_attempts_to_fix(self) -> float | None:
        fixed = [s for s in self._sessions if s.status == CorrectionStatus.FIXED]
        if not fixed:
            return None
        return round(sum(len(s.attempts) for s in fixed) / len(fixed), 2)

    def issues_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for session in self._sessions:
            for issue in session.detected_issues:
                counts[issue.issue_type] = counts.get(issue.issue_type, 0) + 1
        return counts

    def summary(self) -> dict[str, Any]:
        total = len(self._sessions)
        by_status: dict[str, int] = {}
        for s in self._sessions:
            by_status[s.status] = by_status.get(s.status, 0) + 1
        return {
            "total_sessions": total,
            "by_status": by_status,
            "success_rate": self.success_rate(),
            "avg_attempts_to_fix": self.avg_attempts_to_fix(),
            "circuit_breaker_open": self._circuit_open,
            "consecutive_failures": self._consecutive_failures,
            "strategies_configured": len(self._strategies),
        }
