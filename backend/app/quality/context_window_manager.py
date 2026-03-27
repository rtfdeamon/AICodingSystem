"""Context Window Manager -- intelligent context engineering.

Manages the limited LLM context window through just-in-time loading,
strategic compression, priority scoring, and "lost in the middle"
mitigation by placing critical information at edges.

Key features:
- Priority-scored context segments with position-aware placement
- Auto-compaction when approaching token limits
- Just-in-time reference resolution (lazy loading)
- Segment deduplication and relevance decay
- Context budget tracking and overflow prevention
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class SegmentType(StrEnum):
    SYSTEM_PROMPT = "system_prompt"
    USER_MESSAGE = "user_message"
    CODE_CONTEXT = "code_context"
    FILE_CONTENT = "file_content"
    TOOL_RESULT = "tool_result"
    CONVERSATION_HISTORY = "conversation_history"
    RETRIEVAL_RESULT = "retrieval_result"
    COMPRESSED_SUMMARY = "compressed_summary"


class ContextPosition(StrEnum):
    """Where to place segment in context window (lost-in-middle mitigation)."""
    START = "start"
    END = "end"
    MIDDLE = "middle"
    AUTO = "auto"


class CompressionStrategy(StrEnum):
    TRUNCATE = "truncate"
    SUMMARIZE = "summarize"
    REMOVE_LOW_PRIORITY = "remove_low_priority"
    DEDUP = "dedup"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class ContextSegment:
    """A discrete unit of context for the LLM window."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    segment_type: SegmentType = SegmentType.CODE_CONTEXT
    content: str = ""
    token_estimate: int = 0
    priority: float = 1.0  # 0.0-10.0, higher = more important
    position_hint: ContextPosition = ContextPosition.AUTO
    source_ref: str | None = None  # lazy-loadable reference
    is_lazy: bool = False  # True = content loaded on demand
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    content_hash: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.token_estimate and self.content:
            self.token_estimate = estimate_tokens(self.content)
        if not self.content_hash and self.content:
            self.content_hash = hashlib.sha256(
                self.content.encode()
            ).hexdigest()[:16]


@dataclass
class ContextBudget:
    """Budget configuration for context window."""

    max_tokens: int = 128_000
    reserved_for_output: int = 4_096
    compaction_threshold: float = 0.85  # trigger at 85% fill
    min_priority_cutoff: float = 0.5

    @property
    def usable_tokens(self) -> int:
        return self.max_tokens - self.reserved_for_output


@dataclass
class ContextSnapshot:
    """Point-in-time view of assembled context."""

    segments: list[ContextSegment]
    total_tokens: int
    budget: ContextBudget
    overflow_removed: int = 0
    duplicates_removed: int = 0
    compressed_count: int = 0

    @property
    def utilization(self) -> float:
        if self.budget.usable_tokens == 0:
            return 0.0
        return self.total_tokens / self.budget.usable_tokens

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.budget.usable_tokens - self.total_tokens)


@dataclass
class CompactionResult:
    """Result of running context compaction."""

    tokens_before: int
    tokens_after: int
    segments_removed: int
    segments_compressed: int
    strategies_applied: list[str]

    @property
    def tokens_saved(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def reduction_pct(self) -> float:
        if self.tokens_before == 0:
            return 0.0
        return (self.tokens_saved / self.tokens_before) * 100


# ── Helpers ──────────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token heuristic)."""
    return max(1, len(text) // 4)


def _relevance_decay(segment: ContextSegment, now: datetime) -> float:
    """Decay priority based on age (older = less relevant)."""
    age_seconds = (now - segment.created_at).total_seconds()
    # Half-life of 1 hour for conversation history, longer for code
    if segment.segment_type == SegmentType.CONVERSATION_HISTORY:
        half_life = 3600.0
    elif segment.segment_type == SegmentType.TOOL_RESULT:
        half_life = 1800.0
    else:
        half_life = 7200.0

    decay_factor = 0.5 ** (age_seconds / half_life) if half_life > 0 else 1.0
    return segment.priority * max(0.1, decay_factor)


# ── Priority defaults ────────────────────────────────────────────────────

SEGMENT_TYPE_BASE_PRIORITY: dict[SegmentType, float] = {
    SegmentType.SYSTEM_PROMPT: 10.0,
    SegmentType.USER_MESSAGE: 9.0,
    SegmentType.CODE_CONTEXT: 7.0,
    SegmentType.FILE_CONTENT: 6.0,
    SegmentType.TOOL_RESULT: 5.0,
    SegmentType.RETRIEVAL_RESULT: 4.0,
    SegmentType.CONVERSATION_HISTORY: 3.0,
    SegmentType.COMPRESSED_SUMMARY: 2.0,
}


# ── Context Window Manager ──────────────────────────────────────────────

class ContextWindowManager:
    """Manages context window assembly with priority placement and compression."""

    def __init__(self, budget: ContextBudget | None = None):
        self.budget = budget or ContextBudget()
        self._segments: list[ContextSegment] = []
        self._lazy_loaders: dict[str, callable] = {}
        self._compaction_history: list[CompactionResult] = []

    # ── Segment management ──────────────────────────────────────────

    def add_segment(
        self,
        content: str,
        segment_type: SegmentType,
        priority: float | None = None,
        position_hint: ContextPosition = ContextPosition.AUTO,
        source_ref: str | None = None,
        metadata: dict | None = None,
    ) -> ContextSegment:
        """Add a content segment to the context window."""
        if priority is None:
            priority = SEGMENT_TYPE_BASE_PRIORITY.get(segment_type, 1.0)

        segment = ContextSegment(
            segment_type=segment_type,
            content=content,
            priority=priority,
            position_hint=position_hint,
            source_ref=source_ref,
            metadata=metadata or {},
        )
        self._segments.append(segment)
        logger.debug(
            "Added segment %s (%s, ~%d tokens, priority=%.1f)",
            segment.id[:8],
            segment_type,
            segment.token_estimate,
            priority,
        )
        return segment

    def add_lazy_segment(
        self,
        source_ref: str,
        segment_type: SegmentType,
        loader: callable,
        estimated_tokens: int = 500,
        priority: float | None = None,
    ) -> ContextSegment:
        """Add a lazy-loaded segment (just-in-time context)."""
        if priority is None:
            priority = SEGMENT_TYPE_BASE_PRIORITY.get(segment_type, 1.0)

        segment = ContextSegment(
            segment_type=segment_type,
            content="",
            token_estimate=estimated_tokens,
            priority=priority,
            source_ref=source_ref,
            is_lazy=True,
        )
        self._segments.append(segment)
        self._lazy_loaders[segment.id] = loader
        return segment

    def resolve_lazy(self, segment_id: str) -> bool:
        """Resolve a lazy segment by loading its content."""
        loader = self._lazy_loaders.get(segment_id)
        if not loader:
            return False

        seg = next((s for s in self._segments if s.id == segment_id), None)
        if not seg or not seg.is_lazy:
            return False

        content = loader()
        if content:
            seg.content = content
            seg.token_estimate = estimate_tokens(content)
            seg.content_hash = hashlib.sha256(
                content.encode()
            ).hexdigest()[:16]
            seg.is_lazy = False
            del self._lazy_loaders[segment_id]
            return True
        return False

    def remove_segment(self, segment_id: str) -> bool:
        """Remove a segment by ID."""
        before = len(self._segments)
        self._segments = [s for s in self._segments if s.id != segment_id]
        return len(self._segments) < before

    # ── Deduplication ───────────────────────────────────────────────

    def deduplicate(self) -> int:
        """Remove duplicate segments (same content hash), keeping highest priority."""
        seen: dict[str, ContextSegment] = {}
        removed = 0

        for seg in self._segments:
            if not seg.content_hash:
                continue
            if seg.content_hash in seen:
                existing = seen[seg.content_hash]
                if seg.priority > existing.priority:
                    self._segments.remove(existing)
                    seen[seg.content_hash] = seg
                else:
                    self._segments.remove(seg)
                removed += 1
            else:
                seen[seg.content_hash] = seg

        if removed:
            logger.info("Deduplicated %d segments", removed)
        return removed

    # ── Assembly ────────────────────────────────────────────────────

    def assemble(self, resolve_lazy_refs: bool = True) -> ContextSnapshot:
        """Assemble context window with position-aware placement."""
        # 1. Resolve lazy segments if requested
        if resolve_lazy_refs:
            for seg in list(self._segments):
                if seg.is_lazy:
                    self.resolve_lazy(seg.id)

        # 2. Deduplicate
        dups_removed = self.deduplicate()

        # 3. Check if compaction needed
        total = sum(s.token_estimate for s in self._segments)
        overflow_removed = 0
        compressed = 0

        if total > self.budget.usable_tokens:
            result = self.compact()
            overflow_removed = result.segments_removed
            compressed = result.segments_compressed
            total = sum(s.token_estimate for s in self._segments)

        # 4. Sort by position-aware placement
        ordered = self._position_aware_sort()

        return ContextSnapshot(
            segments=ordered,
            total_tokens=total,
            budget=self.budget,
            overflow_removed=overflow_removed,
            duplicates_removed=dups_removed,
            compressed_count=compressed,
        )

    def _position_aware_sort(self) -> list[ContextSegment]:
        """Sort segments to mitigate 'lost in the middle' effect.

        Critical items go to start/end; lower priority fills middle.
        """
        start_segs: list[ContextSegment] = []
        end_segs: list[ContextSegment] = []
        middle_segs: list[ContextSegment] = []

        for seg in self._segments:
            hint = seg.position_hint
            if hint == ContextPosition.AUTO:
                # System prompts and high-priority at edges
                if seg.segment_type == SegmentType.SYSTEM_PROMPT:
                    hint = ContextPosition.START
                elif seg.segment_type == SegmentType.USER_MESSAGE:
                    hint = ContextPosition.END
                elif seg.priority >= 7.0:
                    hint = ContextPosition.START
                else:
                    hint = ContextPosition.MIDDLE

            if hint == ContextPosition.START:
                start_segs.append(seg)
            elif hint == ContextPosition.END:
                end_segs.append(seg)
            else:
                middle_segs.append(seg)

        # Sort each group by priority descending
        start_segs.sort(key=lambda s: s.priority, reverse=True)
        end_segs.sort(key=lambda s: s.priority, reverse=True)
        middle_segs.sort(key=lambda s: s.priority, reverse=True)

        return start_segs + middle_segs + end_segs

    # ── Compaction ──────────────────────────────────────────────────

    def compact(
        self,
        strategies: list[CompressionStrategy] | None = None,
    ) -> CompactionResult:
        """Run compaction to fit within budget."""
        if strategies is None:
            strategies = [
                CompressionStrategy.DEDUP,
                CompressionStrategy.REMOVE_LOW_PRIORITY,
                CompressionStrategy.TRUNCATE,
            ]

        tokens_before = sum(s.token_estimate for s in self._segments)
        removed = 0
        compressed = 0
        applied: list[str] = []

        for strategy in strategies:
            current = sum(s.token_estimate for s in self._segments)
            if current <= self.budget.usable_tokens:
                break

            if strategy == CompressionStrategy.DEDUP:
                r = self.deduplicate()
                if r:
                    removed += r
                    applied.append("dedup")

            elif strategy == CompressionStrategy.REMOVE_LOW_PRIORITY:
                now = datetime.now(UTC)
                scored = [
                    (seg, _relevance_decay(seg, now))
                    for seg in self._segments
                ]
                scored.sort(key=lambda x: x[1])

                while (
                    sum(s.token_estimate for s in self._segments)
                    > self.budget.usable_tokens
                    and scored
                ):
                    seg, score = scored.pop(0)
                    if score < self.budget.min_priority_cutoff:
                        self._segments.remove(seg)
                        removed += 1

                if removed:
                    applied.append("remove_low_priority")

            elif strategy == CompressionStrategy.TRUNCATE:
                # Truncate longest low-priority segments
                for seg in sorted(
                    self._segments,
                    key=lambda s: s.priority,
                ):
                    if (
                        sum(s.token_estimate for s in self._segments)
                        <= self.budget.usable_tokens
                    ):
                        break
                    if seg.priority < 5.0 and seg.token_estimate > 200:
                        half = len(seg.content) // 2
                        seg.content = (
                            seg.content[:half] + "\n... [truncated] ..."
                        )
                        seg.token_estimate = estimate_tokens(seg.content)
                        seg.content_hash = hashlib.sha256(
                            seg.content.encode()
                        ).hexdigest()[:16]
                        compressed += 1

                if compressed:
                    applied.append("truncate")

            elif strategy == CompressionStrategy.SUMMARIZE:
                applied.append("summarize")

        tokens_after = sum(s.token_estimate for s in self._segments)
        result = CompactionResult(
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            segments_removed=removed,
            segments_compressed=compressed,
            strategies_applied=applied,
        )
        self._compaction_history.append(result)
        logger.info(
            "Compaction: %d → %d tokens (saved %d, removed %d segs)",
            tokens_before,
            tokens_after,
            result.tokens_saved,
            removed,
        )
        return result

    # ── Stats ───────────────────────────────────────────────────────

    @property
    def total_tokens(self) -> int:
        return sum(s.token_estimate for s in self._segments)

    @property
    def segment_count(self) -> int:
        return len(self._segments)

    @property
    def utilization(self) -> float:
        if self.budget.usable_tokens == 0:
            return 0.0
        return self.total_tokens / self.budget.usable_tokens

    @property
    def needs_compaction(self) -> bool:
        return self.utilization >= self.budget.compaction_threshold

    def stats(self) -> dict:
        """Return context window statistics."""
        by_type: dict[str, int] = {}
        for seg in self._segments:
            by_type[seg.segment_type] = (
                by_type.get(seg.segment_type, 0) + seg.token_estimate
            )

        return {
            "total_tokens": self.total_tokens,
            "usable_tokens": self.budget.usable_tokens,
            "utilization_pct": round(self.utilization * 100, 1),
            "segment_count": self.segment_count,
            "lazy_pending": sum(1 for s in self._segments if s.is_lazy),
            "tokens_by_type": by_type,
            "needs_compaction": self.needs_compaction,
            "compaction_runs": len(self._compaction_history),
        }

    def clear(self):
        """Clear all segments."""
        self._segments.clear()
        self._lazy_loaders.clear()
