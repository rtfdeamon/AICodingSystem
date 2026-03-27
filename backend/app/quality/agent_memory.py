"""Agent Memory Manager — persistent, cross-session memory for AI agents
with relevance decay and context pruning.

Production AI agents lose critical context between sessions, leading to
repeated mistakes and degraded user experience.  AgentMemoryManager provides
structured memory with automatic relevance decay, importance scoring, and
context-window budgeting so agents retain the right information across turns
and sessions.

Based on Liu et al. "AgentBench: Evaluating LLMs as Agents" (arXiv:2308.03688,
2023/2025) and Wang et al. "MINT: Evaluating LLMs in Multi-turn Interaction"
(arXiv:2309.10691, 2024), plus production patterns from LangChain and
LlamaIndex memory modules.

Key capabilities:
- Memory types: short-term, long-term, episodic, semantic
- Exponential relevance decay over time
- Context window budgeting with token-aware retrieval
- Importance scoring (access frequency, recency, explicit weight)
- Conflict resolution: newer memories supersede contradictions
- Memory compression: merge similar entries to save capacity
- Eviction policy: LRU, importance-weighted, or hybrid
- Full audit trail for memory operations
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class MemoryType(StrEnum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    DECAYED = "decayed"
    ARCHIVED = "archived"
    EVICTED = "evicted"


class EvictionPolicy(StrEnum):
    LRU = "lru"
    IMPORTANCE = "importance"
    HYBRID = "hybrid"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """A single memory stored by the agent."""

    id: str
    content: str
    memory_type: MemoryType
    importance: float = 0.5
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    decay_factor: float = 1.0
    status: MemoryStatus = MemoryStatus.ACTIVE
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryQuery:
    """Parameters for querying agent memory."""

    query_text: str
    memory_types: list[MemoryType] | None = None
    max_results: int = 10
    min_relevance: float = 0.0
    token_budget: int = 0


@dataclass
class MemorySearchResult:
    """A memory entry with its computed relevance score."""

    entry: MemoryEntry
    relevance_score: float
    decay_adjusted_score: float


@dataclass
class MemoryStats:
    """Aggregate statistics about the memory store."""

    total_entries: int
    active: int
    decayed: int
    archived: int
    evicted: int
    avg_importance: float
    avg_age_hours: float


# ── Agent Memory Manager ────────────────────────────────────────────────

class AgentMemoryManager:
    """Persistent memory manager for AI agents.

    Provides structured storage, relevance-based retrieval, automatic
    decay, conflict resolution, and context-window budgeting.
    """

    def __init__(
        self,
        *,
        max_entries: int = 10_000,
        decay_rate: float = 0.01,
        eviction_policy: EvictionPolicy = EvictionPolicy.HYBRID,
        similarity_threshold: float = 0.8,
    ) -> None:
        self._memories: dict[str, MemoryEntry] = {}
        self._max_entries = max_entries
        self._decay_rate = decay_rate
        self._eviction_policy = eviction_policy
        self._similarity_threshold = similarity_threshold
        self._counter = 0
        self._audit_log: list[dict[str, Any]] = []

    # ── Public API ───────────────────────────────────────────────────

    def store(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        importance: float = 0.5,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        """Store a new memory entry."""
        self._counter += 1
        entry_id = self._generate_id(content)

        entry = MemoryEntry(
            id=entry_id,
            content=content,
            memory_type=memory_type,
            importance=max(0.0, min(1.0, importance)),
            tags=tags or [],
            metadata=metadata or {},
        )

        # Check for conflicts with existing active memories
        active = [m for m in self._memories.values() if m.status == MemoryStatus.ACTIVE]
        conflicts = self._check_conflicts(content, active)
        for conflict in conflicts:
            conflict.status = MemoryStatus.ARCHIVED
            self._audit_log.append({
                "action": "archive_conflict",
                "memory_id": conflict.id,
                "superseded_by": entry_id,
                "timestamp": time.time(),
            })

        self._memories[entry_id] = entry
        self._evict_if_needed()

        self._audit_log.append({
            "action": "store",
            "memory_id": entry_id,
            "memory_type": memory_type,
            "importance": entry.importance,
            "timestamp": time.time(),
        })

        return entry

    def retrieve(self, query: MemoryQuery) -> list[MemorySearchResult]:
        """Retrieve memories matching the query, ranked by relevance."""
        results: list[MemorySearchResult] = []

        for entry in self._memories.values():
            if entry.status != MemoryStatus.ACTIVE:
                continue

            if query.memory_types and entry.memory_type not in query.memory_types:
                continue

            relevance = self._compute_relevance(query.query_text, entry)
            decay_adjusted = relevance * self._apply_decay(entry)

            if decay_adjusted < query.min_relevance:
                continue

            results.append(MemorySearchResult(
                entry=entry,
                relevance_score=relevance,
                decay_adjusted_score=decay_adjusted,
            ))

        # Sort by decay-adjusted score descending
        results.sort(key=lambda r: r.decay_adjusted_score, reverse=True)

        # Apply max_results limit
        results = results[: query.max_results]

        # Update access metadata for retrieved entries
        now = time.time()
        for result in results:
            result.entry.last_accessed = now
            result.entry.access_count += 1

        self._audit_log.append({
            "action": "retrieve",
            "query": query.query_text,
            "results_count": len(results),
            "timestamp": time.time(),
        })

        return results

    def update(
        self,
        memory_id: str,
        content: str | None = None,
        importance: float | None = None,
    ) -> MemoryEntry | None:
        """Update an existing memory entry."""
        entry = self._memories.get(memory_id)
        if entry is None or entry.status == MemoryStatus.EVICTED:
            return None

        if content is not None:
            entry.content = content
        if importance is not None:
            entry.importance = max(0.0, min(1.0, importance))
        entry.last_accessed = time.time()

        self._audit_log.append({
            "action": "update",
            "memory_id": memory_id,
            "timestamp": time.time(),
        })

        return entry

    def evict(self, memory_id: str) -> bool:
        """Manually evict a memory entry."""
        entry = self._memories.get(memory_id)
        if entry is None:
            return False
        if entry.status == MemoryStatus.EVICTED:
            return False

        entry.status = MemoryStatus.EVICTED

        self._audit_log.append({
            "action": "evict",
            "memory_id": memory_id,
            "timestamp": time.time(),
        })

        return True

    def get_stats(self) -> MemoryStats:
        """Return aggregate statistics about the memory store."""
        entries = list(self._memories.values())
        if not entries:
            return MemoryStats(
                total_entries=0,
                active=0,
                decayed=0,
                archived=0,
                evicted=0,
                avg_importance=0.0,
                avg_age_hours=0.0,
            )

        now = time.time()
        active = sum(1 for e in entries if e.status == MemoryStatus.ACTIVE)
        decayed = sum(1 for e in entries if e.status == MemoryStatus.DECAYED)
        archived = sum(1 for e in entries if e.status == MemoryStatus.ARCHIVED)
        evicted = sum(1 for e in entries if e.status == MemoryStatus.EVICTED)
        avg_imp = sum(e.importance for e in entries) / len(entries)
        avg_age = sum((now - e.created_at) for e in entries) / len(entries) / 3600.0

        return MemoryStats(
            total_entries=len(entries),
            active=active,
            decayed=decayed,
            archived=archived,
            evicted=evicted,
            avg_importance=avg_imp,
            avg_age_hours=avg_age,
        )

    def get_context_window(
        self,
        query: str,
        token_budget: int,
    ) -> list[MemorySearchResult]:
        """Select the most relevant memories that fit within a token budget.

        Uses a simple word-count heuristic (1 token ≈ 0.75 words) to
        estimate token usage.
        """
        mq = MemoryQuery(
            query_text=query,
            max_results=self._max_entries,
            min_relevance=0.0,
        )
        all_results = self.retrieve(mq)

        selected: list[MemorySearchResult] = []
        used_tokens = 0
        for result in all_results:
            est_tokens = self._estimate_tokens(result.entry.content)
            if used_tokens + est_tokens > token_budget:
                continue
            selected.append(result)
            used_tokens += est_tokens

        return selected

    def clear_session(self) -> int:
        """Archive all short-term memories (end of session cleanup)."""
        count = 0
        for entry in self._memories.values():
            if (
                entry.memory_type == MemoryType.SHORT_TERM
                and entry.status == MemoryStatus.ACTIVE
            ):
                entry.status = MemoryStatus.ARCHIVED
                count += 1

        self._audit_log.append({
            "action": "clear_session",
            "archived_count": count,
            "timestamp": time.time(),
        })

        return count

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Return the full audit trail."""
        return list(self._audit_log)

    # ── Private helpers ──────────────────────────────────────────────

    def _compute_relevance(self, query_text: str, entry: MemoryEntry) -> float:
        """Compute relevance between a query and a memory entry.

        Uses term-overlap (Jaccard-like) similarity between the query
        and the memory content plus tag matching.
        """
        query_terms = set(self._tokenize(query_text))
        content_terms = set(self._tokenize(entry.content))

        if not query_terms or not content_terms:
            return 0.0

        intersection = query_terms & content_terms
        union = query_terms | content_terms
        text_sim = len(intersection) / len(union) if union else 0.0

        # Tag bonus: if query terms appear in tags
        tag_terms = set()
        for tag in entry.tags:
            tag_terms.update(self._tokenize(tag))
        tag_overlap = len(query_terms & tag_terms) / len(query_terms) if query_terms else 0.0

        # Importance boost
        importance_boost = entry.importance * 0.2

        return min(1.0, text_sim * 0.6 + tag_overlap * 0.2 + importance_boost)

    def _apply_decay(self, entry: MemoryEntry) -> float:
        """Apply exponential decay based on time since last access."""
        age_hours = (time.time() - entry.last_accessed) / 3600.0
        decay = math.exp(-self._decay_rate * age_hours)
        entry.decay_factor = decay

        # Mark as decayed if factor drops below threshold
        if decay < 0.1 and entry.status == MemoryStatus.ACTIVE:
            entry.status = MemoryStatus.DECAYED

        return decay

    def _compute_importance_score(self, entry: MemoryEntry) -> float:
        """Compute composite importance from multiple signals."""
        recency = math.exp(-0.001 * (time.time() - entry.last_accessed))
        frequency = min(1.0, entry.access_count / 50.0)
        explicit = entry.importance

        return recency * 0.3 + frequency * 0.3 + explicit * 0.4

    def _check_conflicts(
        self,
        new_content: str,
        existing: list[MemoryEntry],
    ) -> list[MemoryEntry]:
        """Detect existing memories that conflict with new content.

        Uses high term-overlap as a proxy for contradiction — entries
        with very similar terms but different content are likely
        conflicting facts that should be superseded.
        """
        conflicts: list[MemoryEntry] = []
        new_terms = set(self._tokenize(new_content))
        if not new_terms:
            return conflicts

        for entry in existing:
            entry_terms = set(self._tokenize(entry.content))
            if not entry_terms:
                continue
            overlap = len(new_terms & entry_terms) / len(new_terms | entry_terms)
            if overlap >= self._similarity_threshold and new_content != entry.content:
                conflicts.append(entry)

        return conflicts

    def _compress_similar(self, threshold: float | None = None) -> int:
        """Merge similar active memories to reduce count.

        Returns the number of entries compressed (archived).
        """
        if threshold is None:
            threshold = self._similarity_threshold

        active = [
            e for e in self._memories.values() if e.status == MemoryStatus.ACTIVE
        ]
        compressed = 0
        seen: set[str] = set()

        for i, a in enumerate(active):
            if a.id in seen:
                continue
            a_terms = set(self._tokenize(a.content))
            if not a_terms:
                continue

            for b in active[i + 1 :]:
                if b.id in seen:
                    continue
                b_terms = set(self._tokenize(b.content))
                if not b_terms:
                    continue
                overlap = len(a_terms & b_terms) / len(a_terms | b_terms)
                if overlap >= threshold:
                    # Keep the more important / more recently accessed one
                    if self._compute_importance_score(b) > self._compute_importance_score(a):
                        a.status = MemoryStatus.ARCHIVED
                        seen.add(a.id)
                        compressed += 1
                        break
                    else:
                        b.status = MemoryStatus.ARCHIVED
                        seen.add(b.id)
                        compressed += 1

        if compressed:
            self._audit_log.append({
                "action": "compress",
                "compressed_count": compressed,
                "timestamp": time.time(),
            })

        return compressed

    def _evict_if_needed(self) -> int:
        """Evict entries when capacity is exceeded."""
        active = [
            e for e in self._memories.values()
            if e.status in (MemoryStatus.ACTIVE, MemoryStatus.DECAYED)
        ]
        if len(active) <= self._max_entries:
            return 0

        to_evict = len(active) - self._max_entries
        evicted = 0

        if self._eviction_policy == EvictionPolicy.LRU:
            active.sort(key=lambda e: e.last_accessed)
        elif self._eviction_policy == EvictionPolicy.IMPORTANCE:
            active.sort(key=self._compute_importance_score)
        else:  # HYBRID
            active.sort(
                key=lambda e: (
                    self._compute_importance_score(e) * 0.5
                    + (e.last_accessed / (time.time() or 1.0)) * 0.5
                ),
            )

        for entry in active[:to_evict]:
            entry.status = MemoryStatus.EVICTED
            evicted += 1
            self._audit_log.append({
                "action": "evict",
                "memory_id": entry.id,
                "policy": self._eviction_policy,
                "timestamp": time.time(),
            })

        return evicted

    # ── Utility ──────────────────────────────────────────────────────

    @staticmethod
    def _generate_id(content: str) -> str:
        """Generate a deterministic-ish ID from content + timestamp."""
        raw = f"{content}:{time.time()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + punctuation tokenizer, lowercased."""
        return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate: ~0.75 words per token."""
        word_count = len(text.split())
        return max(1, int(word_count / 0.75))
