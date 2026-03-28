"""Maker-Checker Loop Orchestrator — structured review loops for AI outputs.

Implements the maker-checker pattern where one agent generates output and
another evaluates it against criteria. Failed checks cycle back to the
maker with structured feedback until the checker approves or an iteration
cap is reached. Prevents infinite refinement loops with configurable limits
and fallback strategies.

Based on:
- Codebridge "Multi-Agent Systems & AI Orchestration Guide 2026"
- Microsoft Azure "AI Agent Design Patterns" (2026)
- AI-AgentsPlus "Multi-Agent Orchestration Patterns" (2026)
- Lyzr "Agent Orchestration 101" (2026)
- n1n.ai "5 AI Agent Design Patterns to Master by 2026"

Key capabilities:
- Structured maker-checker iteration with feedback propagation
- Configurable iteration cap with fallback behaviour
- Per-iteration quality tracking with improvement detection
- Stagnation detection: abort if quality plateaus across rounds
- Checker criteria: correctness, completeness, style, safety
- Escalation to human reviewer when quality gate not met
- Quality gate: approved / conditionally_approved / rejected / escalated
- Batch loop analytics across all maker-checker sessions
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class LoopOutcome(StrEnum):
    APPROVED = "approved"                       # checker approved
    CONDITIONALLY_APPROVED = "conditionally_approved"  # approved with caveats
    REJECTED = "rejected"                       # cap reached, not approved
    ESCALATED = "escalated"                     # handed to human
    STAGNATED = "stagnated"                     # quality stopped improving


class CheckCriterion(StrEnum):
    CORRECTNESS = "correctness"
    COMPLETENESS = "completeness"
    STYLE = "style"
    SAFETY = "safety"
    PERFORMANCE = "performance"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    """Result from a single checker evaluation."""

    criterion: CheckCriterion
    passed: bool
    score: float = 0.0  # 0-1
    feedback: str = ""


@dataclass
class IterationRecord:
    """Record of a single maker-checker iteration."""

    iteration: int
    maker_output_hash: str = ""
    check_results: list[CheckResult] = field(default_factory=list)
    overall_score: float = 0.0
    approved: bool = False
    feedback_to_maker: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class LoopConfig:
    """Configuration for maker-checker loops."""

    max_iterations: int = 5
    approval_threshold: float = 0.80  # minimum score for approval
    conditional_threshold: float = 0.65  # minimum for conditional approval
    stagnation_tolerance: float = 0.02  # improvement < this = stagnating
    stagnation_rounds: int = 2  # consecutive stagnating rounds to abort
    required_criteria: list[CheckCriterion] = field(default_factory=lambda: [
        CheckCriterion.CORRECTNESS,
        CheckCriterion.COMPLETENESS,
    ])
    escalate_on_rejection: bool = True


@dataclass
class LoopSession:
    """A complete maker-checker loop session."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_maker: str = ""
    agent_checker: str = ""
    task_description: str = ""
    iterations: list[IterationRecord] = field(default_factory=list)
    outcome: LoopOutcome = LoopOutcome.REJECTED
    final_score: float = 0.0
    gate: GateDecision = GateDecision.BLOCK
    total_iterations: int = 0
    improvement_trajectory: list[float] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


@dataclass
class BatchLoopReport:
    """Analytics across all maker-checker sessions."""

    sessions: list[LoopSession] = field(default_factory=list)
    total_sessions: int = 0
    approval_rate: float = 0.0
    avg_iterations_to_approval: float = 0.0
    avg_final_score: float = 0.0
    escalation_count: int = 0
    stagnation_count: int = 0


# ── Pure helpers ─────────────────────────────────────────────────────────

def _compute_overall_score(results: list[CheckResult]) -> float:
    """Compute weighted average score from check results."""
    if not results:
        return 0.0
    return round(sum(r.score for r in results) / len(results), 4)


def _all_required_pass(
    results: list[CheckResult],
    required: list[CheckCriterion],
) -> bool:
    """Check if all required criteria passed."""
    passed_criteria = {r.criterion for r in results if r.passed}
    return all(c in passed_criteria for c in required)


def _detect_stagnation(
    trajectory: list[float],
    tolerance: float,
    rounds: int,
) -> bool:
    """Detect if quality improvement has stagnated."""
    if len(trajectory) < rounds + 1:
        return False
    recent = trajectory[-(rounds + 1):]
    improvements = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]
    return all(abs(imp) < tolerance for imp in improvements)


def _aggregate_feedback(results: list[CheckResult]) -> str:
    """Build feedback string from failed checks."""
    failed = [r for r in results if not r.passed]
    if not failed:
        return "All checks passed."
    parts = [f"[{r.criterion}] {r.feedback}" for r in failed if r.feedback]
    return "; ".join(parts) if parts else "Some checks failed without specific feedback."


def _outcome_to_gate(outcome: LoopOutcome) -> GateDecision:
    """Map loop outcome to gate decision."""
    if outcome == LoopOutcome.APPROVED:
        return GateDecision.PASS
    if outcome == LoopOutcome.CONDITIONALLY_APPROVED:
        return GateDecision.WARN
    return GateDecision.BLOCK


# ── Main class ───────────────────────────────────────────────────────────

class MakerCheckerLoop:
    """Orchestrates maker-checker loops with quality tracking."""

    def __init__(self, config: LoopConfig | None = None) -> None:
        self._config = config or LoopConfig()
        self._sessions: list[LoopSession] = []

    @property
    def config(self) -> LoopConfig:
        return self._config

    def start_session(
        self,
        agent_maker: str,
        agent_checker: str,
        task_description: str = "",
    ) -> LoopSession:
        """Start a new maker-checker session."""
        session = LoopSession(
            agent_maker=agent_maker,
            agent_checker=agent_checker,
            task_description=task_description,
        )
        self._sessions.append(session)
        logger.info(
            "Started maker-checker session %s: maker=%s, checker=%s",
            session.session_id, agent_maker, agent_checker,
        )
        return session

    def record_iteration(
        self,
        session_id: str,
        check_results: list[CheckResult],
        maker_output_hash: str = "",
    ) -> IterationRecord:
        """Record one iteration of the maker-checker loop."""
        session = self._find_session(session_id)
        if session is None:
            msg = f"Session {session_id} not found"
            raise ValueError(msg)

        iteration_num = len(session.iterations) + 1
        overall_score = _compute_overall_score(check_results)
        approved = (
            overall_score >= self._config.approval_threshold
            and _all_required_pass(check_results, self._config.required_criteria)
        )
        feedback = _aggregate_feedback(check_results)

        record = IterationRecord(
            iteration=iteration_num,
            maker_output_hash=maker_output_hash,
            check_results=check_results,
            overall_score=overall_score,
            approved=approved,
            feedback_to_maker=feedback,
        )

        session.iterations.append(record)
        session.improvement_trajectory.append(overall_score)
        session.total_iterations = iteration_num

        return record

    def evaluate_session(self, session_id: str) -> LoopSession:
        """Evaluate the current state of a session and determine outcome."""
        session = self._find_session(session_id)
        if session is None:
            msg = f"Session {session_id} not found"
            raise ValueError(msg)

        if not session.iterations:
            return session

        last = session.iterations[-1]
        session.final_score = last.overall_score

        # Check approval
        if last.approved:
            session.outcome = LoopOutcome.APPROVED
        elif last.overall_score >= self._config.conditional_threshold:
            if session.total_iterations >= self._config.max_iterations:
                session.outcome = LoopOutcome.CONDITIONALLY_APPROVED
            elif last.approved:
                session.outcome = LoopOutcome.APPROVED
            else:
                session.outcome = LoopOutcome.REJECTED
        else:
            session.outcome = LoopOutcome.REJECTED

        # Check stagnation
        if _detect_stagnation(
            session.improvement_trajectory,
            self._config.stagnation_tolerance,
            self._config.stagnation_rounds,
        ):
            session.outcome = LoopOutcome.STAGNATED

        # Check iteration cap
        if (
            session.total_iterations >= self._config.max_iterations
            and session.outcome not in (LoopOutcome.APPROVED, LoopOutcome.CONDITIONALLY_APPROVED)
        ):
            if self._config.escalate_on_rejection:
                session.outcome = LoopOutcome.ESCALATED
            else:
                session.outcome = LoopOutcome.REJECTED

        session.gate = _outcome_to_gate(session.outcome)
        session.completed_at = datetime.now(UTC)

        logger.info(
            "Session %s outcome: %s (score=%.3f, iterations=%d)",
            session_id, session.outcome, session.final_score, session.total_iterations,
        )
        return session

    def batch_report(self) -> BatchLoopReport:
        """Generate analytics across all sessions."""
        if not self._sessions:
            return BatchLoopReport()

        approved = [
            s for s in self._sessions
            if s.outcome in (LoopOutcome.APPROVED, LoopOutcome.CONDITIONALLY_APPROVED)
        ]
        approval_rate = len(approved) / len(self._sessions) if self._sessions else 0.0

        iterations_for_approved = [s.total_iterations for s in approved] if approved else [0]
        avg_iterations = sum(iterations_for_approved) / len(iterations_for_approved)

        avg_score = (
            sum(s.final_score for s in self._sessions) / len(self._sessions)
            if self._sessions
            else 0.0
        )

        escalation_count = sum(1 for s in self._sessions if s.outcome == LoopOutcome.ESCALATED)
        stagnation_count = sum(1 for s in self._sessions if s.outcome == LoopOutcome.STAGNATED)

        return BatchLoopReport(
            sessions=self._sessions,
            total_sessions=len(self._sessions),
            approval_rate=round(approval_rate, 4),
            avg_iterations_to_approval=round(avg_iterations, 2),
            avg_final_score=round(avg_score, 4),
            escalation_count=escalation_count,
            stagnation_count=stagnation_count,
        )

    def _find_session(self, session_id: str) -> LoopSession | None:
        """Find a session by ID."""
        for s in self._sessions:
            if s.session_id == session_id:
                return s
        return None
