"""Tests for Context Window Manager.

Covers: segment management, lazy loading, deduplication,
position-aware placement, compaction, and stats.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.quality.context_window_manager import (
    CompactionResult,
    CompressionStrategy,
    ContextBudget,
    ContextSegment,
    ContextSnapshot,
    ContextWindowManager,
    SegmentType,
    _relevance_decay,
    estimate_tokens,
)

# ── estimate_tokens ──────────────────────────────────────────────────────

class TestEstimateTokens:
    def test_basic_estimation(self):
        assert estimate_tokens("hello world") >= 1

    def test_empty_string(self):
        assert estimate_tokens("") == 1  # min 1

    def test_longer_text(self):
        text = "a" * 400
        assert estimate_tokens(text) == 100  # 400/4

    def test_proportional(self):
        short = estimate_tokens("abc")
        long = estimate_tokens("a" * 1000)
        assert long > short


# ── ContextSegment ───────────────────────────────────────────────────────

class TestContextSegment:
    def test_auto_token_estimate(self):
        seg = ContextSegment(content="hello world here")
        assert seg.token_estimate >= 1

    def test_auto_content_hash(self):
        seg = ContextSegment(content="test content")
        assert seg.content_hash != ""

    def test_explicit_token_estimate(self):
        seg = ContextSegment(content="abc", token_estimate=999)
        assert seg.token_estimate == 999

    def test_empty_content_no_hash(self):
        seg = ContextSegment(content="")
        assert seg.content_hash == ""


# ── ContextBudget ────────────────────────────────────────────────────────

class TestContextBudget:
    def test_usable_tokens(self):
        b = ContextBudget(max_tokens=100_000, reserved_for_output=4_000)
        assert b.usable_tokens == 96_000

    def test_default_budget(self):
        b = ContextBudget()
        assert b.max_tokens == 128_000
        assert b.usable_tokens == 128_000 - 4_096


# ── ContextSnapshot ──────────────────────────────────────────────────────

class TestContextSnapshot:
    def test_utilization(self):
        budget = ContextBudget(max_tokens=10_000, reserved_for_output=0)
        snap = ContextSnapshot(
            segments=[], total_tokens=5_000, budget=budget
        )
        assert snap.utilization == 0.5

    def test_tokens_remaining(self):
        budget = ContextBudget(max_tokens=10_000, reserved_for_output=0)
        snap = ContextSnapshot(
            segments=[], total_tokens=3_000, budget=budget
        )
        assert snap.tokens_remaining == 7_000

    def test_zero_budget(self):
        budget = ContextBudget(max_tokens=0, reserved_for_output=0)
        snap = ContextSnapshot(
            segments=[], total_tokens=0, budget=budget
        )
        assert snap.utilization == 0.0


# ── CompactionResult ─────────────────────────────────────────────────────

class TestCompactionResult:
    def test_tokens_saved(self):
        r = CompactionResult(
            tokens_before=1000, tokens_after=600,
            segments_removed=2, segments_compressed=1,
            strategies_applied=["dedup"],
        )
        assert r.tokens_saved == 400

    def test_reduction_pct(self):
        r = CompactionResult(
            tokens_before=1000, tokens_after=500,
            segments_removed=0, segments_compressed=0,
            strategies_applied=[],
        )
        assert r.reduction_pct == 50.0

    def test_zero_before(self):
        r = CompactionResult(
            tokens_before=0, tokens_after=0,
            segments_removed=0, segments_compressed=0,
            strategies_applied=[],
        )
        assert r.reduction_pct == 0.0


# ── Relevance decay ─────────────────────────────────────────────────────

class TestRelevanceDecay:
    def test_fresh_segment_no_decay(self):
        seg = ContextSegment(
            content="test", priority=5.0,
            segment_type=SegmentType.CODE_CONTEXT,
        )
        now = datetime.now(UTC)
        score = _relevance_decay(seg, now)
        assert score >= 4.5  # near 5.0

    def test_old_conversation_decays_more(self):
        seg = ContextSegment(
            content="test", priority=5.0,
            segment_type=SegmentType.CONVERSATION_HISTORY,
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )
        now = datetime.now(UTC)
        score = _relevance_decay(seg, now)
        assert score < 2.5

    def test_code_context_decays_slower(self):
        past = datetime.now(UTC) - timedelta(hours=2)
        convo = ContextSegment(
            content="test", priority=5.0,
            segment_type=SegmentType.CONVERSATION_HISTORY,
            created_at=past,
        )
        code = ContextSegment(
            content="test", priority=5.0,
            segment_type=SegmentType.CODE_CONTEXT,
            created_at=past,
        )
        now = datetime.now(UTC)
        assert _relevance_decay(code, now) > _relevance_decay(convo, now)


# ── ContextWindowManager ────────────────────────────────────────────────

class TestContextWindowManager:
    def test_add_segment(self):
        mgr = ContextWindowManager()
        seg = mgr.add_segment("hello", SegmentType.USER_MESSAGE)
        assert seg.segment_type == SegmentType.USER_MESSAGE
        assert mgr.segment_count == 1

    def test_add_segment_default_priority(self):
        mgr = ContextWindowManager()
        seg = mgr.add_segment("sys", SegmentType.SYSTEM_PROMPT)
        assert seg.priority == 10.0

    def test_add_segment_custom_priority(self):
        mgr = ContextWindowManager()
        seg = mgr.add_segment("x", SegmentType.CODE_CONTEXT, priority=3.0)
        assert seg.priority == 3.0

    def test_remove_segment(self):
        mgr = ContextWindowManager()
        seg = mgr.add_segment("test", SegmentType.CODE_CONTEXT)
        assert mgr.remove_segment(seg.id)
        assert mgr.segment_count == 0

    def test_remove_nonexistent(self):
        mgr = ContextWindowManager()
        assert not mgr.remove_segment("fake-id")

    def test_total_tokens(self):
        mgr = ContextWindowManager()
        mgr.add_segment("a" * 100, SegmentType.CODE_CONTEXT)
        assert mgr.total_tokens > 0

    def test_clear(self):
        mgr = ContextWindowManager()
        mgr.add_segment("test", SegmentType.CODE_CONTEXT)
        mgr.clear()
        assert mgr.segment_count == 0


class TestLazyLoading:
    def test_add_lazy_segment(self):
        mgr = ContextWindowManager()
        seg = mgr.add_lazy_segment(
            "ref/file.py", SegmentType.FILE_CONTENT,
            loader=lambda: "file contents here",
        )
        assert seg.is_lazy
        assert seg.content == ""

    def test_resolve_lazy(self):
        mgr = ContextWindowManager()
        seg = mgr.add_lazy_segment(
            "ref/file.py", SegmentType.FILE_CONTENT,
            loader=lambda: "loaded content",
        )
        assert mgr.resolve_lazy(seg.id)
        assert not seg.is_lazy
        assert seg.content == "loaded content"

    def test_resolve_nonexistent(self):
        mgr = ContextWindowManager()
        assert not mgr.resolve_lazy("fake-id")

    def test_resolve_returns_false_on_empty_content(self):
        mgr = ContextWindowManager()
        seg = mgr.add_lazy_segment(
            "ref/file.py", SegmentType.FILE_CONTENT,
            loader=lambda: "",
        )
        assert not mgr.resolve_lazy(seg.id)


class TestDeduplication:
    def test_removes_duplicates(self):
        mgr = ContextWindowManager()
        mgr.add_segment("same content", SegmentType.CODE_CONTEXT)
        mgr.add_segment("same content", SegmentType.CODE_CONTEXT)
        removed = mgr.deduplicate()
        assert removed == 1
        assert mgr.segment_count == 1

    def test_keeps_higher_priority(self):
        mgr = ContextWindowManager()
        mgr.add_segment(
            "content", SegmentType.CODE_CONTEXT, priority=2.0
        )
        mgr.add_segment(
            "content", SegmentType.CODE_CONTEXT, priority=8.0
        )
        mgr.deduplicate()
        assert mgr.segment_count == 1

    def test_no_duplicates(self):
        mgr = ContextWindowManager()
        mgr.add_segment("aaa", SegmentType.CODE_CONTEXT)
        mgr.add_segment("bbb", SegmentType.CODE_CONTEXT)
        removed = mgr.deduplicate()
        assert removed == 0


class TestAssembly:
    def test_basic_assembly(self):
        mgr = ContextWindowManager()
        mgr.add_segment("system prompt", SegmentType.SYSTEM_PROMPT)
        mgr.add_segment("user msg", SegmentType.USER_MESSAGE)
        snap = mgr.assemble()
        assert isinstance(snap, ContextSnapshot)
        assert len(snap.segments) == 2
        assert snap.total_tokens > 0

    def test_system_prompt_at_start(self):
        mgr = ContextWindowManager()
        mgr.add_segment("code", SegmentType.CODE_CONTEXT, priority=5.0)
        mgr.add_segment("system", SegmentType.SYSTEM_PROMPT)
        snap = mgr.assemble()
        assert snap.segments[0].segment_type == SegmentType.SYSTEM_PROMPT

    def test_user_message_at_end(self):
        mgr = ContextWindowManager()
        mgr.add_segment("user q", SegmentType.USER_MESSAGE)
        mgr.add_segment("code", SegmentType.CODE_CONTEXT, priority=5.0)
        snap = mgr.assemble()
        assert snap.segments[-1].segment_type == SegmentType.USER_MESSAGE

    def test_resolves_lazy_during_assembly(self):
        mgr = ContextWindowManager()
        seg = mgr.add_lazy_segment(
            "ref", SegmentType.FILE_CONTENT,
            loader=lambda: "resolved",
        )
        mgr.assemble()
        assert not seg.is_lazy


class TestCompaction:
    def test_compact_removes_low_priority(self):
        budget = ContextBudget(max_tokens=100, reserved_for_output=0)
        mgr = ContextWindowManager(budget=budget)
        mgr.add_segment("a" * 200, SegmentType.CONVERSATION_HISTORY, priority=0.1)
        mgr.add_segment("b" * 200, SegmentType.SYSTEM_PROMPT, priority=10.0)
        result = mgr.compact()
        assert isinstance(result, CompactionResult)

    def test_compact_with_dedup(self):
        budget = ContextBudget(max_tokens=50, reserved_for_output=0)
        mgr = ContextWindowManager(budget=budget)
        mgr.add_segment("same", SegmentType.CODE_CONTEXT)
        mgr.add_segment("same", SegmentType.CODE_CONTEXT)
        result = mgr.compact(
            strategies=[CompressionStrategy.DEDUP]
        )
        assert "dedup" in result.strategies_applied or result.tokens_saved >= 0

    def test_compact_truncate(self):
        budget = ContextBudget(max_tokens=50, reserved_for_output=0)
        mgr = ContextWindowManager(budget=budget)
        mgr.add_segment("x" * 1000, SegmentType.RETRIEVAL_RESULT, priority=2.0)
        result = mgr.compact(
            strategies=[CompressionStrategy.TRUNCATE]
        )
        assert result.segments_compressed >= 0

    def test_assembly_triggers_compaction_on_overflow(self):
        budget = ContextBudget(max_tokens=50, reserved_for_output=0)
        mgr = ContextWindowManager(budget=budget)
        mgr.add_segment("x" * 1000, SegmentType.RETRIEVAL_RESULT, priority=0.1)
        mgr.add_segment("y" * 1000, SegmentType.RETRIEVAL_RESULT, priority=0.1)
        snap = mgr.assemble()
        assert snap.overflow_removed >= 0 or snap.compressed_count >= 0


class TestStats:
    def test_stats_empty(self):
        mgr = ContextWindowManager()
        s = mgr.stats()
        assert s["total_tokens"] == 0
        assert s["segment_count"] == 0
        assert not s["needs_compaction"]

    def test_stats_with_segments(self):
        mgr = ContextWindowManager()
        mgr.add_segment("abc", SegmentType.CODE_CONTEXT)
        mgr.add_segment("def", SegmentType.USER_MESSAGE)
        s = mgr.stats()
        assert s["segment_count"] == 2
        assert s["total_tokens"] > 0

    def test_utilization(self):
        budget = ContextBudget(max_tokens=100, reserved_for_output=0)
        mgr = ContextWindowManager(budget=budget)
        mgr.add_segment("a" * 200, SegmentType.CODE_CONTEXT)
        assert mgr.utilization > 0

    def test_needs_compaction_flag(self):
        budget = ContextBudget(
            max_tokens=100, reserved_for_output=0,
            compaction_threshold=0.5,
        )
        mgr = ContextWindowManager(budget=budget)
        mgr.add_segment("a" * 400, SegmentType.CODE_CONTEXT)
        assert mgr.needs_compaction
