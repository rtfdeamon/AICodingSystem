"""OpenTelemetry Semantic Conventions for GenAI agent operations.

Implements the GenAI semantic conventions (2025-2026 spec) for tracing
AI agent calls with standardised attribute names, span naming, and
metric definitions.

Reference: OpenTelemetry GenAI Semantic Conventions
  https://opentelemetry.io/docs/specs/semconv/gen-ai/
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Semantic Convention Attribute Names ────────────────────────────────
# Following OpenTelemetry GenAI semantic conventions (2025-2026).


class GenAIAttributes(StrEnum):
    """Standard attribute names for GenAI spans."""

    # System
    SYSTEM = "gen_ai.system"  # "anthropic", "openai", "google"
    OPERATION_NAME = "gen_ai.operation.name"  # "chat", "completion", "embedding"

    # Request
    REQUEST_MODEL = "gen_ai.request.model"
    REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
    REQUEST_TEMPERATURE = "gen_ai.request.temperature"
    REQUEST_TOP_P = "gen_ai.request.top_p"
    REQUEST_STOP_SEQUENCES = "gen_ai.request.stop_sequences"

    # Response
    RESPONSE_MODEL = "gen_ai.response.model"
    RESPONSE_ID = "gen_ai.response.id"
    RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"

    # Usage
    USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
    USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
    USAGE_TOTAL_TOKENS = "gen_ai.usage.total_tokens"

    # Agent-specific (custom extensions)
    AGENT_NAME = "gen_ai.agent.name"
    AGENT_ACTION = "gen_ai.agent.action"
    AGENT_TICKET_ID = "gen_ai.agent.ticket_id"
    AGENT_PROJECT_ID = "gen_ai.agent.project_id"
    AGENT_COST_USD = "gen_ai.agent.cost_usd"
    AGENT_ITERATION = "gen_ai.agent.iteration"

    # Error
    ERROR_TYPE = "error.type"
    ERROR_MESSAGE = "error.message"


class GenAIMetricNames(StrEnum):
    """Standard metric names for GenAI operations."""

    TOKEN_USAGE = "gen_ai.client.token.usage"
    OPERATION_DURATION = "gen_ai.client.operation.duration"
    COST_TOTAL = "gen_ai.client.cost.total"
    ERROR_COUNT = "gen_ai.client.error.count"


class SpanKind(StrEnum):
    """Span types for GenAI operations."""

    CLIENT = "client"  # Outbound AI API call
    INTERNAL = "internal"  # Internal processing
    PIPELINE = "pipeline"  # Pipeline orchestration


# ── Span Attributes Builder ───────────────────────────────────────────


@dataclass
class SpanAttributes:
    """Builder for constructing semantically correct span attributes."""

    _attributes: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> SpanAttributes:
        """Set an attribute value."""
        if value is not None:
            self._attributes[key] = value
        return self

    def to_dict(self) -> dict[str, Any]:
        """Return the attributes as a dictionary."""
        return dict(self._attributes)

    @staticmethod
    def for_agent_call(
        *,
        system: str,
        model: str,
        agent_name: str,
        action: str,
        ticket_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> SpanAttributes:
        """Create attributes for an AI agent API call.

        Parameters
        ----------
        system:
            AI provider ("anthropic", "openai", "google").
        model:
            Model identifier (e.g., "claude-sonnet-4-6").
        agent_name:
            Name of the agent (e.g., "claude_agent", "review_agent").
        action:
            Action type (e.g., "code_review", "planning", "coding").
        """
        attrs = SpanAttributes()
        attrs.set(GenAIAttributes.SYSTEM, system)
        attrs.set(GenAIAttributes.REQUEST_MODEL, model)
        attrs.set(GenAIAttributes.OPERATION_NAME, "chat")
        attrs.set(GenAIAttributes.AGENT_NAME, agent_name)
        attrs.set(GenAIAttributes.AGENT_ACTION, action)

        if ticket_id:
            attrs.set(GenAIAttributes.AGENT_TICKET_ID, str(ticket_id))
        if project_id:
            attrs.set(GenAIAttributes.AGENT_PROJECT_ID, str(project_id))
        if temperature is not None:
            attrs.set(GenAIAttributes.REQUEST_TEMPERATURE, temperature)
        if max_tokens is not None:
            attrs.set(GenAIAttributes.REQUEST_MAX_TOKENS, max_tokens)

        return attrs

    @staticmethod
    def for_response(
        *,
        model: str,
        response_id: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        finish_reason: str = "",
    ) -> SpanAttributes:
        """Create attributes for an AI response."""
        attrs = SpanAttributes()
        attrs.set(GenAIAttributes.RESPONSE_MODEL, model)
        if response_id:
            attrs.set(GenAIAttributes.RESPONSE_ID, response_id)
        if input_tokens:
            attrs.set(GenAIAttributes.USAGE_INPUT_TOKENS, input_tokens)
        if output_tokens:
            attrs.set(GenAIAttributes.USAGE_OUTPUT_TOKENS, output_tokens)
        if input_tokens or output_tokens:
            attrs.set(GenAIAttributes.USAGE_TOTAL_TOKENS, input_tokens + output_tokens)
        if cost_usd:
            attrs.set(GenAIAttributes.AGENT_COST_USD, cost_usd)
        if finish_reason:
            attrs.set(GenAIAttributes.RESPONSE_FINISH_REASONS, [finish_reason])
        return attrs


# ── Span Naming Conventions ──────────────────────────────────────────


def build_span_name(operation: str, system: str, model: str = "") -> str:
    """Build a span name following GenAI semantic conventions.

    Format: "{operation} {system}/{model}" or "{operation} {system}"
    Examples:
        "chat anthropic/claude-sonnet-4-6"
        "code_review openai/gpt-4o"
        "planning anthropic"
    """
    if model:
        return f"{operation} {system}/{model}"
    return f"{operation} {system}"


def build_pipeline_span_name(phase: str) -> str:
    """Build a span name for a pipeline phase.

    Format: "pipeline.{phase}"
    Examples:
        "pipeline.planning"
        "pipeline.review"
        "pipeline.deployment"
    """
    return f"pipeline.{phase}"


# ── Lightweight Span Recorder (no OTel SDK dependency) ──────────────
# This can be used standalone or integrated with real OTel exporters.


@dataclass
class RecordedSpan:
    """A recorded span for observability."""

    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    trace_id: str = ""
    parent_span_id: str | None = None
    name: str = ""
    kind: str = SpanKind.CLIENT
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    duration_ms: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"  # "ok", "error"
    events: list[dict[str, Any]] = field(default_factory=list)


_recorded_spans: list[RecordedSpan] = []


def clear_recorded_spans() -> None:
    """Clear recorded spans (for testing)."""
    _recorded_spans.clear()


def record_span(
    name: str,
    attributes: dict[str, Any],
    *,
    kind: str = SpanKind.CLIENT,
    trace_id: str = "",
    parent_span_id: str | None = None,
    duration_ms: int = 0,
    status: str = "ok",
) -> RecordedSpan:
    """Record a span for observability.

    In production, this would forward to an OTel exporter.
    """
    span = RecordedSpan(
        trace_id=trace_id or uuid.uuid4().hex[:32],
        parent_span_id=parent_span_id,
        name=name,
        kind=kind,
        duration_ms=duration_ms,
        attributes=attributes,
        status=status,
    )
    if duration_ms > 0:
        span.end_time = span.start_time
    _recorded_spans.append(span)

    logger.debug(
        "Span recorded: name=%s trace=%s duration=%dms",
        name,
        span.trace_id,
        duration_ms,
    )
    return span


def get_recorded_spans(
    *,
    trace_id: str | None = None,
    limit: int = 100,
) -> list[RecordedSpan]:
    """Get recorded spans, optionally filtered by trace_id."""
    spans = _recorded_spans
    if trace_id:
        spans = [s for s in spans if s.trace_id == trace_id]
    return spans[-limit:]


def spans_to_json(spans: list[RecordedSpan]) -> list[dict[str, Any]]:
    """Serialize spans to JSON-compatible format."""
    return [
        {
            "span_id": s.span_id,
            "trace_id": s.trace_id,
            "parent_span_id": s.parent_span_id,
            "name": s.name,
            "kind": s.kind,
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat() if s.end_time else None,
            "duration_ms": s.duration_ms,
            "attributes": s.attributes,
            "status": s.status,
            "events": s.events,
        }
        for s in spans
    ]
