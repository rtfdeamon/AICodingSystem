"""End-to-end Agent Tracing — full execution traces for each agent run.

Provides a tracing framework that captures the complete lifecycle of
an agent operation, from initial prompt to final output, including:
- Prompt construction timing
- API call latency
- Response parsing
- Output validation
- Post-processing (PII scan, deduplication)
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.observability.otel_conventions import (
    GenAIAttributes,
    RecordedSpan,
    SpanAttributes,
    SpanKind,
    build_span_name,
    record_span,
)

logger = logging.getLogger(__name__)


@dataclass
class TracePhase:
    """A single phase within an agent trace."""

    name: str
    start_time_ns: int = 0
    end_time_ns: int = 0
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def is_complete(self) -> bool:
        return self.end_time_ns > 0


@dataclass
class AgentTrace:
    """Complete execution trace for an agent run."""

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:32])
    agent_name: str = ""
    action: str = ""
    ticket_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    model: str = ""
    system: str = ""

    # Timing
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    total_duration_ms: int = 0

    # Phases
    phases: list[TracePhase] = field(default_factory=list)

    # Results
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    success: bool = False
    error: str | None = None

    # Generated spans
    spans: list[RecordedSpan] = field(default_factory=list)


# ── In-memory trace store ──────────────────────────────────────────────

_traces: dict[str, AgentTrace] = {}


def clear_traces() -> None:
    """Clear stored traces (for testing)."""
    _traces.clear()


def get_trace(trace_id: str) -> AgentTrace | None:
    """Get a trace by ID."""
    return _traces.get(trace_id)


def get_recent_traces(
    *,
    agent_name: str | None = None,
    limit: int = 20,
) -> list[AgentTrace]:
    """Get recent traces, optionally filtered by agent name."""
    traces = list(_traces.values())
    if agent_name:
        traces = [t for t in traces if t.agent_name == agent_name]
    traces.sort(key=lambda t: t.start_time, reverse=True)
    return traces[:limit]


# ── Trace Builder ──────────────────────────────────────────────────────


class AgentTracer:
    """Context manager for tracing agent execution.

    Usage::

        tracer = AgentTracer(
            agent_name="claude_agent",
            action="code_review",
            system="anthropic",
            model="claude-sonnet-4-6",
        )
        with tracer:
            with tracer.phase("prompt_construction"):
                prompt = build_prompt(...)
            with tracer.phase("api_call"):
                response = await agent.invoke(prompt)
            with tracer.phase("response_parsing"):
                result = parse_response(response)
            tracer.set_tokens(input=1000, output=500)
            tracer.set_cost(0.05)
    """

    def __init__(
        self,
        agent_name: str,
        action: str,
        *,
        system: str = "",
        model: str = "",
        ticket_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> None:
        self.trace = AgentTrace(
            agent_name=agent_name,
            action=action,
            system=system,
            model=model,
            ticket_id=ticket_id,
            project_id=project_id,
        )
        self._start_ns: int = 0
        self._current_phase: TracePhase | None = None

    def __enter__(self) -> AgentTracer:
        self._start_ns = time.perf_counter_ns()
        self.trace.start_time = datetime.now(UTC)

        # Record root span
        attrs = SpanAttributes.for_agent_call(
            system=self.trace.system or "unknown",
            model=self.trace.model,
            agent_name=self.trace.agent_name,
            action=self.trace.action,
            ticket_id=self.trace.ticket_id,
            project_id=self.trace.project_id,
        )
        self._root_span = record_span(
            name=build_span_name(
                self.trace.action,
                self.trace.system or "unknown",
                self.trace.model,
            ),
            attributes=attrs.to_dict(),
            kind=SpanKind.PIPELINE,
            trace_id=self.trace.trace_id,
        )
        self.trace.spans.append(self._root_span)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        elapsed_ns = time.perf_counter_ns() - self._start_ns
        self.trace.total_duration_ms = elapsed_ns // 1_000_000
        self.trace.end_time = datetime.now(UTC)

        if exc_val is not None:
            self.trace.success = False
            self.trace.error = str(exc_val)
            self._root_span.status = "error"
        else:
            self.trace.success = True

        self._root_span.duration_ms = self.trace.total_duration_ms

        # Store trace
        _traces[self.trace.trace_id] = self.trace

        logger.info(
            "Agent trace completed: agent=%s action=%s duration=%dms success=%s",
            self.trace.agent_name,
            self.trace.action,
            self.trace.total_duration_ms,
            self.trace.success,
        )

    @contextmanager
    def phase(self, name: str) -> Generator[TracePhase, None, None]:
        """Record a phase within the trace."""
        trace_phase = TracePhase(name=name)
        trace_phase.start_time_ns = time.perf_counter_ns()

        # Record child span
        span = record_span(
            name=f"{self.trace.agent_name}.{name}",
            attributes={
                GenAIAttributes.AGENT_NAME: self.trace.agent_name,
                "phase": name,
            },
            kind=SpanKind.INTERNAL,
            trace_id=self.trace.trace_id,
            parent_span_id=self._root_span.span_id,
        )

        self._current_phase = trace_phase
        try:
            yield trace_phase
        except Exception as exc:
            trace_phase.error = str(exc)
            span.status = "error"
            raise
        finally:
            self._current_phase = None
            trace_phase.end_time_ns = time.perf_counter_ns()
            trace_phase.duration_ms = (
                (trace_phase.end_time_ns - trace_phase.start_time_ns) // 1_000_000
            )
            span.duration_ms = trace_phase.duration_ms
            self.trace.phases.append(trace_phase)
            self.trace.spans.append(span)

    def set_tokens(self, *, input: int = 0, output: int = 0) -> None:
        """Record token usage."""
        self.trace.input_tokens = input
        self.trace.output_tokens = output

    def set_cost(self, cost_usd: float) -> None:
        """Record cost."""
        self.trace.cost_usd = cost_usd

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the current phase or last completed phase."""
        if self._current_phase is not None:
            self._current_phase.metadata[key] = value
        elif self.trace.phases:
            self.trace.phases[-1].metadata[key] = value


def trace_to_json(trace: AgentTrace) -> dict[str, Any]:
    """Serialize an AgentTrace to JSON-compatible dict."""
    return {
        "trace_id": trace.trace_id,
        "agent_name": trace.agent_name,
        "action": trace.action,
        "ticket_id": str(trace.ticket_id) if trace.ticket_id else None,
        "model": trace.model,
        "system": trace.system,
        "start_time": trace.start_time.isoformat(),
        "end_time": trace.end_time.isoformat() if trace.end_time else None,
        "total_duration_ms": trace.total_duration_ms,
        "input_tokens": trace.input_tokens,
        "output_tokens": trace.output_tokens,
        "cost_usd": trace.cost_usd,
        "success": trace.success,
        "error": trace.error,
        "phases": [
            {
                "name": p.name,
                "duration_ms": p.duration_ms,
                "error": p.error,
                "metadata": p.metadata,
            }
            for p in trace.phases
        ],
        "span_count": len(trace.spans),
    }
