"""Tests for Agent Reasoning Trace Review."""

import pytest

from app.observability.reasoning_trace import (
    ConfidenceLevel,
    ReasoningTraceRecorder,
    StepType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def recorder():
    return ReasoningTraceRecorder()


@pytest.fixture
def active_trace(recorder: ReasoningTraceRecorder):
    return recorder.start_trace("planning-agent", ticket_id="TICKET-1")


# ---------------------------------------------------------------------------
# Trace lifecycle tests
# ---------------------------------------------------------------------------

class TestTraceLifecycle:
    def test_start_trace(self, recorder: ReasoningTraceRecorder):
        trace = recorder.start_trace("coding-agent")
        assert trace.trace_id.startswith("trace-")
        assert trace.agent_id == "coding-agent"
        assert trace.started_at != ""
        assert trace.completed_at is None

    def test_start_trace_with_ticket(self, recorder: ReasoningTraceRecorder):
        trace = recorder.start_trace("agent", ticket_id="T-1")
        assert trace.ticket_id == "T-1"

    def test_end_trace(self, recorder: ReasoningTraceRecorder, active_trace):
        completed = recorder.end_trace(active_trace.trace_id)
        assert completed is not None
        assert completed.completed_at is not None

    def test_end_active_trace(self, recorder: ReasoningTraceRecorder, active_trace):
        # Should end the current active trace
        completed = recorder.end_trace()
        assert completed is not None
        assert recorder.get_active_trace() is None

    def test_end_nonexistent_trace(self, recorder: ReasoningTraceRecorder):
        assert recorder.end_trace("nonexistent") is None

    def test_end_no_active_trace(self, recorder: ReasoningTraceRecorder):
        assert recorder.end_trace() is None

    def test_get_active_trace(self, recorder: ReasoningTraceRecorder, active_trace):
        assert recorder.get_active_trace() is not None
        assert recorder.get_active_trace().trace_id == active_trace.trace_id


# ---------------------------------------------------------------------------
# Step recording tests
# ---------------------------------------------------------------------------

class TestStepRecording:
    def test_record_basic_step(self, recorder: ReasoningTraceRecorder, active_trace):
        step = recorder.record_step(
            StepType.REASONING,
            "Analyzing the ticket requirements",
        )
        assert step is not None
        assert step.step_type == StepType.REASONING
        assert step.description == "Analyzing the ticket requirements"
        assert step.confidence == ConfidenceLevel.HIGH

    def test_record_step_with_details(self, recorder: ReasoningTraceRecorder, active_trace):
        step = recorder.record_step(
            StepType.TOOL_INVOCATION,
            "Running linter",
            details={"tool": "ruff", "args": ["check", "."]},
            duration_ms=1500.0,
        )
        assert step is not None
        assert step.details["tool"] == "ruff"
        assert step.duration_ms == 1500.0

    def test_record_step_no_active_trace(self, recorder: ReasoningTraceRecorder):
        step = recorder.record_step(StepType.REASONING, "test")
        assert step is None

    def test_step_ids_unique(self, recorder: ReasoningTraceRecorder, active_trace):
        s1 = recorder.record_step(StepType.REASONING, "step 1")
        s2 = recorder.record_step(StepType.REASONING, "step 2")
        assert s1 is not None and s2 is not None
        assert s1.step_id != s2.step_id

    def test_record_file_read(self, recorder: ReasoningTraceRecorder, active_trace):
        step = recorder.record_file_read("src/main.py")
        assert step is not None
        assert step.step_type == StepType.FILE_READ
        trace = recorder.get_active_trace()
        assert trace is not None
        assert "src/main.py" in trace.files_read

    def test_record_file_write(self, recorder: ReasoningTraceRecorder, active_trace):
        step = recorder.record_file_write("src/output.py")
        assert step is not None
        assert step.step_type == StepType.FILE_WRITE
        trace = recorder.get_active_trace()
        assert trace is not None
        assert "src/output.py" in trace.files_written

    def test_record_retrieval(self, recorder: ReasoningTraceRecorder, active_trace):
        step = recorder.record_retrieval("find auth middleware", results_count=5)
        assert step is not None
        assert step.step_type == StepType.RETRIEVAL_QUERY
        assert step.details["results_count"] == 5

    def test_record_decision(self, recorder: ReasoningTraceRecorder, active_trace):
        step = recorder.record_decision(
            "Use JWT for authentication",
            alternatives=["Session cookies", "OAuth tokens"],
            chosen_reason="Better for API-first architecture",
            confidence=ConfidenceLevel.HIGH,
        )
        assert step is not None
        assert step.step_type == StepType.DECISION
        trace = recorder.get_active_trace()
        assert trace is not None
        assert len(trace.decisions) == 1
        assert trace.decisions[0]["description"] == "Use JWT for authentication"

    def test_record_backtrack(self, recorder: ReasoningTraceRecorder, active_trace):
        step = recorder.record_backtrack("Approach didn't work with async")
        assert step is not None
        assert step.step_type == StepType.BACKTRACK
        assert step.confidence == ConfidenceLevel.LOW

    def test_record_error(self, recorder: ReasoningTraceRecorder, active_trace):
        step = recorder.record_error("File not found: config.py")
        assert step is not None
        assert step.step_type == StepType.ERROR

    def test_record_error_recoverable(self, recorder: ReasoningTraceRecorder, active_trace):
        step = recorder.record_error("Timeout", recoverable=True)
        assert step is not None
        assert step.details["recoverable"] is True

    def test_record_error_unrecoverable(self, recorder: ReasoningTraceRecorder, active_trace):
        step = recorder.record_error("Fatal crash", recoverable=False)
        assert step is not None
        assert step.details["recoverable"] is False

    def test_no_duplicate_file_reads(self, recorder: ReasoningTraceRecorder, active_trace):
        recorder.record_file_read("src/main.py")
        recorder.record_file_read("src/main.py")
        trace = recorder.get_active_trace()
        assert trace is not None
        assert trace.files_read.count("src/main.py") == 1

    def test_parent_step_id(self, recorder: ReasoningTraceRecorder, active_trace):
        s1 = recorder.record_step(StepType.REASONING, "parent")
        assert s1 is not None
        s2 = recorder.record_step(
            StepType.REASONING, "child", parent_step_id=s1.step_id
        )
        assert s2 is not None
        assert s2.parent_step_id == s1.step_id


# ---------------------------------------------------------------------------
# Aggregation tests
# ---------------------------------------------------------------------------

class TestAggregation:
    def test_backtrack_count(self, recorder: ReasoningTraceRecorder, active_trace):
        recorder.record_backtrack("reason 1")
        recorder.record_backtrack("reason 2")
        trace = recorder.end_trace()
        assert trace is not None
        assert trace.backtracks == 2

    def test_low_confidence_count(self, recorder: ReasoningTraceRecorder, active_trace):
        recorder.record_step(
            StepType.REASONING, "unsure", confidence=ConfidenceLevel.LOW
        )
        recorder.record_step(
            StepType.REASONING, "uncertain", confidence=ConfidenceLevel.UNCERTAIN
        )
        recorder.record_step(
            StepType.REASONING, "sure", confidence=ConfidenceLevel.HIGH
        )
        trace = recorder.end_trace()
        assert trace is not None
        assert trace.low_confidence_steps == 2

    def test_total_duration(self, recorder: ReasoningTraceRecorder, active_trace):
        recorder.record_step(StepType.REASONING, "s1", duration_ms=100.0)
        recorder.record_step(StepType.REASONING, "s2", duration_ms=200.0)
        trace = recorder.end_trace()
        assert trace is not None
        assert trace.total_duration_ms == 300.0


# ---------------------------------------------------------------------------
# Review tests
# ---------------------------------------------------------------------------

class TestTraceReview:
    def test_review_clean_trace(self, recorder: ReasoningTraceRecorder, active_trace):
        recorder.record_file_read("src/main.py")
        recorder.record_decision("Use pattern X", confidence=ConfidenceLevel.HIGH)
        recorder.record_file_write("src/output.py")
        recorder.end_trace()

        review = recorder.review_trace(active_trace.trace_id)
        assert review.score == 100.0
        assert len(review.issues) == 0

    def test_review_excessive_backtracks(self, recorder: ReasoningTraceRecorder, active_trace):
        for i in range(5):
            recorder.record_backtrack(f"reason {i}")
        recorder.end_trace()

        review = recorder.review_trace(active_trace.trace_id)
        assert review.score < 100.0
        assert any(
            i["type"] == "excessive_backtracks" for i in review.issues
        )

    def test_review_low_confidence_decisions(
        self, recorder: ReasoningTraceRecorder, active_trace
    ):
        recorder.record_decision(
            "Uncertain choice", confidence=ConfidenceLevel.LOW
        )
        recorder.end_trace()

        review = recorder.review_trace(active_trace.trace_id)
        assert review.score < 100.0

    def test_review_no_context_read(self, recorder: ReasoningTraceRecorder, active_trace):
        recorder.record_file_write("output.py")
        recorder.end_trace()

        review = recorder.review_trace(active_trace.trace_id)
        assert any(i["type"] == "no_context_read" for i in review.issues)
        assert review.score <= 70.0

    def test_review_unrecoverable_errors(
        self, recorder: ReasoningTraceRecorder, active_trace
    ):
        recorder.record_error("fatal", recoverable=False)
        recorder.end_trace()

        review = recorder.review_trace(active_trace.trace_id)
        assert any(i["type"] == "unrecoverable_errors" for i in review.issues)

    def test_review_no_decisions_with_writes(
        self, recorder: ReasoningTraceRecorder, active_trace
    ):
        recorder.record_file_read("input.py")
        recorder.record_file_write("output.py")
        recorder.end_trace()

        review = recorder.review_trace(active_trace.trace_id)
        assert any("no explicit decisions" in w for w in review.warnings)

    def test_review_nonexistent_trace(self, recorder: ReasoningTraceRecorder):
        review = recorder.review_trace("nonexistent")
        assert review.score == 0.0
        assert len(review.issues) > 0

    def test_review_score_minimum_zero(
        self, recorder: ReasoningTraceRecorder, active_trace
    ):
        # Generate many issues to test score floor
        for i in range(10):
            recorder.record_backtrack(f"reason {i}")
        for i in range(5):
            recorder.record_decision(f"bad {i}", confidence=ConfidenceLevel.LOW)
        recorder.record_error("fatal", recoverable=False)
        recorder.record_file_write("out.py")  # no reads
        recorder.end_trace()

        review = recorder.review_trace(active_trace.trace_id)
        assert review.score >= 0.0


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------

class TestQueries:
    def test_get_trace(self, recorder: ReasoningTraceRecorder, active_trace):
        trace = recorder.get_trace(active_trace.trace_id)
        assert trace is not None
        assert trace.trace_id == active_trace.trace_id

    def test_get_nonexistent_trace(self, recorder: ReasoningTraceRecorder):
        assert recorder.get_trace("nonexistent") is None

    def test_get_traces_for_ticket(self, recorder: ReasoningTraceRecorder):
        recorder.start_trace("agent-1", ticket_id="T-1")
        recorder.end_trace()
        recorder.start_trace("agent-2", ticket_id="T-1")
        recorder.end_trace()
        recorder.start_trace("agent-3", ticket_id="T-2")
        recorder.end_trace()

        traces = recorder.get_traces_for_ticket("T-1")
        assert len(traces) == 2

    def test_get_stats(self, recorder: ReasoningTraceRecorder, active_trace):
        recorder.record_step(StepType.REASONING, "s1")
        recorder.record_step(StepType.REASONING, "s2")
        recorder.end_trace()

        stats = recorder.get_stats()
        assert stats["total_traces"] == 1
        assert stats["completed_traces"] == 1
        assert stats["avg_steps_per_trace"] == 2.0

    def test_traces_property(self, recorder: ReasoningTraceRecorder, active_trace):
        traces = recorder.traces
        assert len(traces) == 1


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_step_to_dict(self, recorder: ReasoningTraceRecorder, active_trace):
        step = recorder.record_step(StepType.REASONING, "test step")
        assert step is not None
        d = step.to_dict()
        assert d["step_type"] == "reasoning"
        assert d["description"] == "test step"

    def test_trace_to_dict(self, recorder: ReasoningTraceRecorder, active_trace):
        recorder.record_file_read("src/main.py")
        recorder.record_decision("Use X")
        recorder.end_trace()

        d = active_trace.to_dict()
        assert d["agent_id"] == "planning-agent"
        assert d["step_count"] == 2
        assert "files_read" in d
        assert "decisions" in d

    def test_review_to_dict(self, recorder: ReasoningTraceRecorder, active_trace):
        recorder.end_trace()
        review = recorder.review_trace(active_trace.trace_id)
        d = review.to_dict()
        assert "trace_id" in d
        assert "score" in d
        assert "issues" in d
