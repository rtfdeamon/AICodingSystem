"""
Agent Reasoning Trace Review.

Captures and exposes the full reasoning trace of AI coding agents — which
files the model read, what retrieval queries it issued, what logic chain
it followed, what alternatives it considered and rejected — as a first-class
reviewable artifact in pull requests alongside the generated code.

Industry context (2025-2026):
- As AI agents become more autonomous, reviewing only the final code diff
  is insufficient
- Reasoning traces reveal why the agent made specific decisions
- Teams reviewing traces catch architectural misalignment before production
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class StepType(StrEnum):
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    RETRIEVAL_QUERY = "retrieval_query"
    TOOL_INVOCATION = "tool_invocation"
    DECISION = "decision"
    BACKTRACK = "backtrack"
    ERROR = "error"
    REASONING = "reasoning"
    CONTEXT_LOAD = "context_load"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"


@dataclass
class TraceStep:
    """Single step in an agent's reasoning trace."""
    step_id: str
    step_type: StepType
    timestamp: str
    description: str
    details: dict[str, Any] = field(default_factory=dict)
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH
    duration_ms: float = 0.0
    parent_step_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_type": self.step_type.value,
            "timestamp": self.timestamp,
            "description": self.description,
            "details": self.details,
            "confidence": self.confidence.value,
            "duration_ms": self.duration_ms,
            "parent_step_id": self.parent_step_id,
        }


@dataclass
class ReasoningTrace:
    """Complete reasoning trace for an agent execution."""
    trace_id: str
    agent_id: str
    ticket_id: str | None = None
    started_at: str = ""
    completed_at: str | None = None
    steps: list[TraceStep] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    backtracks: int = 0
    low_confidence_steps: int = 0
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "agent_id": self.agent_id,
            "ticket_id": self.ticket_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "step_count": len(self.steps),
            "files_read": self.files_read,
            "files_written": self.files_written,
            "decisions": self.decisions,
            "backtracks": self.backtracks,
            "low_confidence_steps": self.low_confidence_steps,
            "total_duration_ms": self.total_duration_ms,
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class TraceReview:
    """Review checklist result for a reasoning trace."""
    trace_id: str
    reviewed_at: str
    issues: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float = 0.0  # 0-100

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "reviewed_at": self.reviewed_at,
            "issues": self.issues,
            "warnings": self.warnings,
            "score": self.score,
        }


# ---------------------------------------------------------------------------
# Reasoning Trace Recorder
# ---------------------------------------------------------------------------

class ReasoningTraceRecorder:
    """
    Records and reviews agent reasoning traces.

    Responsibilities:
    - Capture every file read, retrieval query, tool invocation, and decision
    - Flag traces with low confidence, backtracks, or retries
    - Auto-review traces against a checklist
    - Store traces as immutable artifacts linked to commits
    """

    def __init__(self) -> None:
        self._traces: dict[str, ReasoningTrace] = {}
        self._active_trace: str | None = None
        self._step_counter: int = 0

    # -- Trace lifecycle ----------------------------------------------------

    def start_trace(
        self, agent_id: str, ticket_id: str | None = None
    ) -> ReasoningTrace:
        """Start a new reasoning trace for an agent execution."""
        now = datetime.now(UTC).isoformat()
        trace_id = f"trace-{hashlib.sha256(f'{agent_id}-{now}'.encode()).hexdigest()[:12]}"

        trace = ReasoningTrace(
            trace_id=trace_id,
            agent_id=agent_id,
            ticket_id=ticket_id,
            started_at=now,
        )
        self._traces[trace_id] = trace
        self._active_trace = trace_id
        return trace

    def end_trace(self, trace_id: str | None = None) -> ReasoningTrace | None:
        """Complete a reasoning trace."""
        tid = trace_id or self._active_trace
        if tid is None or tid not in self._traces:
            return None

        trace = self._traces[tid]
        trace.completed_at = datetime.now(UTC).isoformat()

        # Calculate aggregates
        trace.backtracks = sum(
            1 for s in trace.steps if s.step_type == StepType.BACKTRACK
        )
        trace.low_confidence_steps = sum(
            1 for s in trace.steps
            if s.confidence in (ConfidenceLevel.LOW, ConfidenceLevel.UNCERTAIN)
        )
        trace.total_duration_ms = sum(s.duration_ms for s in trace.steps)

        if tid == self._active_trace:
            self._active_trace = None

        return trace

    # -- Step recording -----------------------------------------------------

    def record_step(
        self,
        step_type: StepType,
        description: str,
        *,
        trace_id: str | None = None,
        details: dict[str, Any] | None = None,
        confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
        duration_ms: float = 0.0,
        parent_step_id: str | None = None,
    ) -> TraceStep | None:
        """Record a single step in the current trace."""
        tid = trace_id or self._active_trace
        if tid is None or tid not in self._traces:
            return None

        trace = self._traces[tid]
        self._step_counter += 1
        now = datetime.now(UTC).isoformat()

        step = TraceStep(
            step_id=f"step-{self._step_counter:04d}",
            step_type=step_type,
            timestamp=now,
            description=description,
            details=details or {},
            confidence=confidence,
            duration_ms=duration_ms,
            parent_step_id=parent_step_id,
        )
        trace.steps.append(step)

        # Update trace aggregates
        if step_type == StepType.FILE_READ:
            file_path = (details or {}).get("file_path", "")
            if file_path and file_path not in trace.files_read:
                trace.files_read.append(file_path)

        elif step_type == StepType.FILE_WRITE:
            file_path = (details or {}).get("file_path", "")
            if file_path and file_path not in trace.files_written:
                trace.files_written.append(file_path)

        elif step_type == StepType.DECISION:
            trace.decisions.append({
                "step_id": step.step_id,
                "description": description,
                "confidence": confidence.value,
                "details": details or {},
            })

        return step

    # -- Convenience methods ------------------------------------------------

    def record_file_read(
        self, file_path: str, *, trace_id: str | None = None, duration_ms: float = 0.0
    ) -> TraceStep | None:
        return self.record_step(
            StepType.FILE_READ,
            f"Read file: {file_path}",
            trace_id=trace_id,
            details={"file_path": file_path},
            duration_ms=duration_ms,
        )

    def record_file_write(
        self, file_path: str, *, trace_id: str | None = None, duration_ms: float = 0.0
    ) -> TraceStep | None:
        return self.record_step(
            StepType.FILE_WRITE,
            f"Write file: {file_path}",
            trace_id=trace_id,
            details={"file_path": file_path},
            duration_ms=duration_ms,
        )

    def record_retrieval(
        self,
        query: str,
        results_count: int = 0,
        *,
        trace_id: str | None = None,
        duration_ms: float = 0.0,
    ) -> TraceStep | None:
        return self.record_step(
            StepType.RETRIEVAL_QUERY,
            f"Retrieval query: {query}",
            trace_id=trace_id,
            details={"query": query, "results_count": results_count},
            duration_ms=duration_ms,
        )

    def record_decision(
        self,
        decision: str,
        alternatives: list[str] | None = None,
        chosen_reason: str = "",
        *,
        trace_id: str | None = None,
        confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    ) -> TraceStep | None:
        return self.record_step(
            StepType.DECISION,
            decision,
            trace_id=trace_id,
            details={
                "alternatives_considered": alternatives or [],
                "chosen_reason": chosen_reason,
            },
            confidence=confidence,
        )

    def record_backtrack(
        self,
        reason: str,
        from_step_id: str | None = None,
        *,
        trace_id: str | None = None,
    ) -> TraceStep | None:
        return self.record_step(
            StepType.BACKTRACK,
            f"Backtrack: {reason}",
            trace_id=trace_id,
            details={"from_step_id": from_step_id, "reason": reason},
            confidence=ConfidenceLevel.LOW,
        )

    def record_error(
        self,
        error: str,
        *,
        trace_id: str | None = None,
        recoverable: bool = True,
    ) -> TraceStep | None:
        return self.record_step(
            StepType.ERROR,
            f"Error: {error}",
            trace_id=trace_id,
            details={"error": error, "recoverable": recoverable},
            confidence=ConfidenceLevel.LOW,
        )

    # -- Review -------------------------------------------------------------

    def review_trace(self, trace_id: str) -> TraceReview:
        """Auto-review a trace against quality checklist."""
        trace = self._traces.get(trace_id)
        if trace is None:
            return TraceReview(
                trace_id=trace_id,
                reviewed_at=datetime.now(UTC).isoformat(),
                issues=[{"type": "error", "message": "Trace not found"}],
                score=0.0,
            )

        now = datetime.now(UTC).isoformat()
        issues: list[dict[str, Any]] = []
        warnings: list[str] = []
        score = 100.0

        # Check 1: Excessive backtracks
        if trace.backtracks > 3:
            issues.append({
                "type": "excessive_backtracks",
                "message": f"Agent backtracked {trace.backtracks} times",
                "severity": "warning",
            })
            score -= min(trace.backtracks * 5, 25)

        # Check 2: Low confidence decisions
        low_conf_decisions = [
            d for d in trace.decisions
            if d["confidence"] in ("low", "uncertain")
        ]
        if low_conf_decisions:
            issues.append({
                "type": "low_confidence_decisions",
                "message": f"{len(low_conf_decisions)} decision(s) made with low confidence",
                "severity": "warning",
                "decisions": low_conf_decisions,
            })
            score -= len(low_conf_decisions) * 10

        # Check 3: No files read before writing
        if trace.files_written and not trace.files_read:
            issues.append({
                "type": "no_context_read",
                "message": "Agent wrote files without reading any context",
                "severity": "error",
            })
            score -= 30

        # Check 4: Too many files read without action
        if len(trace.files_read) > 20 and not trace.files_written:
            warnings.append(
                f"Agent read {len(trace.files_read)} files but wrote nothing"
            )
            score -= 10

        # Check 5: Errors without recovery
        errors = [
            s for s in trace.steps if s.step_type == StepType.ERROR
        ]
        unrecoverable = [
            e for e in errors
            if not e.details.get("recoverable", True)
        ]
        if unrecoverable:
            issues.append({
                "type": "unrecoverable_errors",
                "message": f"{len(unrecoverable)} unrecoverable error(s) occurred",
                "severity": "error",
            })
            score -= len(unrecoverable) * 15

        # Check 6: No decisions recorded
        if not trace.decisions and trace.files_written:
            warnings.append(
                "Agent wrote code but recorded no explicit decisions"
            )
            score -= 10

        # Check 7: Very long execution
        if trace.total_duration_ms > 300_000:  # > 5 minutes
            warnings.append(
                f"Execution took {trace.total_duration_ms / 1000:.1f}s (>5min)"
            )

        score = max(score, 0.0)

        return TraceReview(
            trace_id=trace_id,
            reviewed_at=now,
            issues=issues,
            warnings=warnings,
            score=round(score, 1),
        )

    # -- Queries ------------------------------------------------------------

    def get_trace(self, trace_id: str) -> ReasoningTrace | None:
        """Get a trace by ID."""
        return self._traces.get(trace_id)

    def get_traces_for_ticket(self, ticket_id: str) -> list[ReasoningTrace]:
        """Get all traces for a ticket."""
        return [
            t for t in self._traces.values()
            if t.ticket_id == ticket_id
        ]

    def get_active_trace(self) -> ReasoningTrace | None:
        """Get the currently active trace."""
        if self._active_trace and self._active_trace in self._traces:
            return self._traces[self._active_trace]
        return None

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics."""
        completed = [t for t in self._traces.values() if t.completed_at]
        avg_steps = (
            sum(len(t.steps) for t in completed) / len(completed)
            if completed
            else 0
        )
        avg_backtracks = (
            sum(t.backtracks for t in completed) / len(completed)
            if completed
            else 0
        )

        return {
            "total_traces": len(self._traces),
            "completed_traces": len(completed),
            "active_trace": self._active_trace,
            "avg_steps_per_trace": round(avg_steps, 1),
            "avg_backtracks_per_trace": round(avg_backtracks, 1),
            "total_steps_recorded": self._step_counter,
        }

    @property
    def traces(self) -> dict[str, ReasoningTrace]:
        return dict(self._traces)
