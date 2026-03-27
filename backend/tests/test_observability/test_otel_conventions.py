"""Tests for OpenTelemetry semantic conventions module."""

from __future__ import annotations

import uuid

import pytest

from app.observability.otel_conventions import (
    GenAIAttributes,
    GenAIMetricNames,
    SpanAttributes,
    SpanKind,
    build_pipeline_span_name,
    build_span_name,
    clear_recorded_spans,
    get_recorded_spans,
    record_span,
    spans_to_json,
)


@pytest.fixture(autouse=True)
def _clean_spans() -> None:
    clear_recorded_spans()


# ── GenAI attribute names ─────────────────────────────────────────────


class TestGenAIAttributes:
    def test_system_attribute(self) -> None:
        assert GenAIAttributes.SYSTEM == "gen_ai.system"

    def test_request_model(self) -> None:
        assert GenAIAttributes.REQUEST_MODEL == "gen_ai.request.model"

    def test_usage_tokens(self) -> None:
        assert GenAIAttributes.USAGE_INPUT_TOKENS == "gen_ai.usage.input_tokens"
        assert GenAIAttributes.USAGE_OUTPUT_TOKENS == "gen_ai.usage.output_tokens"

    def test_agent_custom_attributes(self) -> None:
        assert GenAIAttributes.AGENT_NAME == "gen_ai.agent.name"
        assert GenAIAttributes.AGENT_ACTION == "gen_ai.agent.action"

    def test_metric_names(self) -> None:
        assert GenAIMetricNames.TOKEN_USAGE == "gen_ai.client.token.usage"
        assert GenAIMetricNames.OPERATION_DURATION == "gen_ai.client.operation.duration"


# ── SpanAttributes builder ────────────────────────────────────────────


class TestSpanAttributes:
    def test_set_and_get(self) -> None:
        attrs = SpanAttributes()
        attrs.set("key", "value")
        assert attrs.to_dict() == {"key": "value"}

    def test_skips_none_values(self) -> None:
        attrs = SpanAttributes()
        attrs.set("key", None)
        assert attrs.to_dict() == {}

    def test_chaining(self) -> None:
        attrs = SpanAttributes().set("a", 1).set("b", 2)
        assert attrs.to_dict() == {"a": 1, "b": 2}

    def test_for_agent_call(self) -> None:
        tid = uuid.uuid4()
        attrs = SpanAttributes.for_agent_call(
            system="anthropic",
            model="claude-sonnet-4-6",
            agent_name="review_agent",
            action="code_review",
            ticket_id=tid,
            temperature=0.1,
            max_tokens=4096,
        )
        d = attrs.to_dict()
        assert d[GenAIAttributes.SYSTEM] == "anthropic"
        assert d[GenAIAttributes.REQUEST_MODEL] == "claude-sonnet-4-6"
        assert d[GenAIAttributes.AGENT_NAME] == "review_agent"
        assert d[GenAIAttributes.AGENT_ACTION] == "code_review"
        assert d[GenAIAttributes.AGENT_TICKET_ID] == str(tid)
        assert d[GenAIAttributes.REQUEST_TEMPERATURE] == 0.1
        assert d[GenAIAttributes.REQUEST_MAX_TOKENS] == 4096

    def test_for_agent_call_optional_fields(self) -> None:
        attrs = SpanAttributes.for_agent_call(
            system="openai",
            model="gpt-4o",
            agent_name="coding_agent",
            action="coding",
        )
        d = attrs.to_dict()
        assert GenAIAttributes.AGENT_TICKET_ID not in d
        assert GenAIAttributes.REQUEST_TEMPERATURE not in d

    def test_for_response(self) -> None:
        attrs = SpanAttributes.for_response(
            model="claude-sonnet-4-6",
            response_id="resp-123",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05,
            finish_reason="end_turn",
        )
        d = attrs.to_dict()
        assert d[GenAIAttributes.RESPONSE_MODEL] == "claude-sonnet-4-6"
        assert d[GenAIAttributes.RESPONSE_ID] == "resp-123"
        assert d[GenAIAttributes.USAGE_INPUT_TOKENS] == 1000
        assert d[GenAIAttributes.USAGE_OUTPUT_TOKENS] == 500
        assert d[GenAIAttributes.USAGE_TOTAL_TOKENS] == 1500
        assert d[GenAIAttributes.AGENT_COST_USD] == 0.05


# ── Span naming ──────────────────────────────────────────────────────


class TestSpanNaming:
    def test_with_model(self) -> None:
        name = build_span_name("chat", "anthropic", "claude-sonnet-4-6")
        assert name == "chat anthropic/claude-sonnet-4-6"

    def test_without_model(self) -> None:
        name = build_span_name("code_review", "openai")
        assert name == "code_review openai"

    def test_pipeline_span_name(self) -> None:
        name = build_pipeline_span_name("planning")
        assert name == "pipeline.planning"


# ── Span recording ───────────────────────────────────────────────────


class TestRecordSpan:
    def test_records_span(self) -> None:
        span = record_span("test_span", {"key": "value"}, duration_ms=100)
        assert span.name == "test_span"
        assert span.attributes["key"] == "value"
        assert span.duration_ms == 100

    def test_assigns_trace_id(self) -> None:
        span = record_span("test", {})
        assert len(span.trace_id) == 32

    def test_uses_provided_trace_id(self) -> None:
        span = record_span("test", {}, trace_id="abc123")
        assert span.trace_id == "abc123"

    def test_get_recorded_spans(self) -> None:
        record_span("s1", {})
        record_span("s2", {})
        spans = get_recorded_spans()
        assert len(spans) == 2

    def test_filter_by_trace_id(self) -> None:
        record_span("s1", {}, trace_id="trace-1")
        record_span("s2", {}, trace_id="trace-2")
        spans = get_recorded_spans(trace_id="trace-1")
        assert len(spans) == 1
        assert spans[0].name == "s1"

    def test_respects_limit(self) -> None:
        for i in range(20):
            record_span(f"s{i}", {})
        spans = get_recorded_spans(limit=5)
        assert len(spans) == 5

    def test_spans_to_json(self) -> None:
        span = record_span("test", {"k": "v"}, duration_ms=50)
        data = spans_to_json([span])
        assert len(data) == 1
        assert data[0]["name"] == "test"
        assert data[0]["attributes"]["k"] == "v"
        assert data[0]["duration_ms"] == 50

    def test_span_kind_values(self) -> None:
        span = record_span("test", {}, kind=SpanKind.PIPELINE)
        assert span.kind == "pipeline"
