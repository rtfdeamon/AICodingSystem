"""Tests for end-to-end agent tracing module."""

from __future__ import annotations

import time
import uuid

import pytest

from app.observability.agent_tracing import (
    AgentTracer,
    clear_traces,
    get_recent_traces,
    get_trace,
    trace_to_json,
)
from app.observability.otel_conventions import clear_recorded_spans


@pytest.fixture(autouse=True)
def _clean() -> None:
    clear_traces()
    clear_recorded_spans()


class TestAgentTracer:
    def test_basic_trace(self) -> None:
        tracer = AgentTracer(
            agent_name="claude_agent",
            action="code_review",
            system="anthropic",
            model="claude-sonnet-4-6",
        )
        with tracer:
            pass

        assert tracer.trace.success is True
        assert tracer.trace.total_duration_ms >= 0
        assert tracer.trace.agent_name == "claude_agent"

    def test_trace_with_phases(self) -> None:
        tracer = AgentTracer(agent_name="test_agent", action="test")
        with tracer:
            with tracer.phase("phase_1"):
                time.sleep(0.001)
            with tracer.phase("phase_2"):
                time.sleep(0.001)

        assert len(tracer.trace.phases) == 2
        assert tracer.trace.phases[0].name == "phase_1"
        assert tracer.trace.phases[1].name == "phase_2"
        assert all(p.is_complete for p in tracer.trace.phases)

    def test_trace_records_tokens(self) -> None:
        tracer = AgentTracer(agent_name="test", action="test")
        with tracer:
            tracer.set_tokens(input=1000, output=500)
            tracer.set_cost(0.05)

        assert tracer.trace.input_tokens == 1000
        assert tracer.trace.output_tokens == 500
        assert tracer.trace.cost_usd == 0.05

    def test_trace_handles_error(self) -> None:
        tracer = AgentTracer(agent_name="test", action="test")
        with pytest.raises(ValueError):
            with tracer:
                raise ValueError("test error")

        assert tracer.trace.success is False
        assert "test error" in str(tracer.trace.error)

    def test_phase_handles_error(self) -> None:
        tracer = AgentTracer(agent_name="test", action="test")
        with pytest.raises(RuntimeError):
            with tracer:
                with tracer.phase("failing_phase"):
                    raise RuntimeError("phase failed")

        assert tracer.trace.phases[0].error == "phase failed"

    def test_trace_stored(self) -> None:
        tracer = AgentTracer(agent_name="test", action="test")
        with tracer:
            pass

        found = get_trace(tracer.trace.trace_id)
        assert found is not None
        assert found.agent_name == "test"

    def test_trace_generates_spans(self) -> None:
        tracer = AgentTracer(
            agent_name="test",
            action="review",
            system="anthropic",
            model="claude-sonnet-4-6",
        )
        with tracer:
            with tracer.phase("prompt"):
                pass
            with tracer.phase("api_call"):
                pass

        # Root span + 2 phase spans
        assert len(tracer.trace.spans) == 3

    def test_add_metadata(self) -> None:
        tracer = AgentTracer(agent_name="test", action="test")
        with tracer:
            with tracer.phase("p1"):
                tracer.add_metadata("key", "value")

        assert tracer.trace.phases[0].metadata["key"] == "value"

    def test_ticket_and_project_ids(self) -> None:
        tid = uuid.uuid4()
        pid = uuid.uuid4()
        tracer = AgentTracer(
            agent_name="test",
            action="test",
            ticket_id=tid,
            project_id=pid,
        )
        with tracer:
            pass

        assert tracer.trace.ticket_id == tid
        assert tracer.trace.project_id == pid


class TestTraceRetrieval:
    def test_get_recent_traces(self) -> None:
        for i in range(5):
            t = AgentTracer(agent_name=f"agent_{i}", action="test")
            with t:
                pass

        traces = get_recent_traces(limit=3)
        assert len(traces) == 3

    def test_filter_by_agent_name(self) -> None:
        for name in ["agent_a", "agent_b", "agent_a"]:
            t = AgentTracer(agent_name=name, action="test")
            with t:
                pass

        traces = get_recent_traces(agent_name="agent_a")
        assert len(traces) == 2
        assert all(t.agent_name == "agent_a" for t in traces)


class TestTraceToJson:
    def test_serializes_trace(self) -> None:
        tracer = AgentTracer(
            agent_name="test_agent",
            action="code_review",
            system="anthropic",
            model="claude-sonnet-4-6",
        )
        with tracer:
            with tracer.phase("phase_1"):
                pass
            tracer.set_tokens(input=100, output=50)

        data = trace_to_json(tracer.trace)
        assert data["agent_name"] == "test_agent"
        assert data["action"] == "code_review"
        assert data["input_tokens"] == 100
        assert len(data["phases"]) == 1
        assert data["phases"][0]["name"] == "phase_1"
        assert data["success"] is True
        assert data["span_count"] == 2  # root + 1 phase
