"""Tests for Agent Memory Manager."""

from __future__ import annotations

import time

import pytest

from app.quality.agent_memory import (
    AgentMemoryManager,
    EvictionPolicy,
    MemoryEntry,
    MemoryQuery,
    MemorySearchResult,
    MemoryStats,
    MemoryStatus,
    MemoryType,
)


@pytest.fixture
def manager() -> AgentMemoryManager:
    return AgentMemoryManager()


@pytest.fixture
def small_manager() -> AgentMemoryManager:
    """Manager with tiny capacity for eviction tests."""
    return AgentMemoryManager(max_entries=5)


@pytest.fixture
def populated_manager(manager: AgentMemoryManager) -> AgentMemoryManager:
    manager.store(
        "The deployment uses Kubernetes on AWS",
        MemoryType.LONG_TERM, 0.8, ["infra"],
    )
    manager.store(
        "User prefers dark mode in the UI",
        MemoryType.SEMANTIC, 0.6, ["prefs"],
    )
    manager.store(
        "Debug session found null pointer in auth module",
        MemoryType.EPISODIC, 0.9, ["debug", "auth"],
    )
    manager.store(
        "Current task is refactoring the payment service",
        MemoryType.SHORT_TERM, 0.7, ["task"],
    )
    return manager


class TestStore:
    def test_store_returns_entry(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("test content", MemoryType.SHORT_TERM)
        assert isinstance(entry, MemoryEntry)
        assert entry.content == "test content"
        assert entry.memory_type == MemoryType.SHORT_TERM

    def test_store_sets_defaults(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("hello world")
        assert entry.importance == 0.5
        assert entry.status == MemoryStatus.ACTIVE
        assert entry.access_count == 0
        assert entry.tags == []
        assert entry.metadata == {}

    def test_store_with_tags_and_metadata(self, manager: AgentMemoryManager) -> None:
        entry = manager.store(
            "tagged memory",
            tags=["alpha", "beta"],
            metadata={"source": "test"},
        )
        assert entry.tags == ["alpha", "beta"]
        assert entry.metadata == {"source": "test"}

    def test_importance_clamped_high(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("over", importance=5.0)
        assert entry.importance == 1.0

    def test_importance_clamped_low(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("under", importance=-1.0)
        assert entry.importance == 0.0

    def test_store_generates_unique_ids(self, manager: AgentMemoryManager) -> None:
        e1 = manager.store("content A")
        e2 = manager.store("content B")
        assert e1.id != e2.id

    def test_store_audit_logged(self, manager: AgentMemoryManager) -> None:
        manager.store("auditable")
        log = manager.get_audit_log()
        assert any(entry["action"] == "store" for entry in log)


class TestRetrieve:
    def test_retrieve_by_text(self, populated_manager: AgentMemoryManager) -> None:
        query = MemoryQuery(query_text="Kubernetes deployment AWS")
        results = populated_manager.retrieve(query)
        assert len(results) >= 1
        assert isinstance(results[0], MemorySearchResult)

    def test_retrieve_respects_memory_type_filter(
        self, populated_manager: AgentMemoryManager,
    ) -> None:
        query = MemoryQuery(
            query_text="deployment",
            memory_types=[MemoryType.SHORT_TERM],
        )
        results = populated_manager.retrieve(query)
        for r in results:
            assert r.entry.memory_type == MemoryType.SHORT_TERM

    def test_retrieve_respects_max_results(self, populated_manager: AgentMemoryManager) -> None:
        query = MemoryQuery(query_text="the", max_results=2)
        results = populated_manager.retrieve(query)
        assert len(results) <= 2

    def test_retrieve_respects_min_relevance(self, populated_manager: AgentMemoryManager) -> None:
        query = MemoryQuery(query_text="Kubernetes", min_relevance=0.9)
        results = populated_manager.retrieve(query)
        for r in results:
            assert r.decay_adjusted_score >= 0.9

    def test_retrieve_updates_access_count(self, populated_manager: AgentMemoryManager) -> None:
        query = MemoryQuery(query_text="Kubernetes deployment AWS")
        results = populated_manager.retrieve(query)
        if results:
            assert results[0].entry.access_count >= 1

    def test_retrieve_empty_query(self, populated_manager: AgentMemoryManager) -> None:
        query = MemoryQuery(query_text="")
        results = populated_manager.retrieve(query)
        # Empty query yields zero text similarity; results may still appear
        # due to importance boost, but all relevance scores should be 0.0
        for r in results:
            assert r.relevance_score == 0.0

    def test_retrieve_no_match(self, populated_manager: AgentMemoryManager) -> None:
        query = MemoryQuery(query_text="xyzzy frobnicator", min_relevance=0.5)
        results = populated_manager.retrieve(query)
        assert len(results) == 0

    def test_retrieve_sorted_by_decay_adjusted(self, populated_manager: AgentMemoryManager) -> None:
        query = MemoryQuery(query_text="the")
        results = populated_manager.retrieve(query)
        scores = [r.decay_adjusted_score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestUpdate:
    def test_update_content(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("old content")
        updated = manager.update(entry.id, content="new content")
        assert updated is not None
        assert updated.content == "new content"

    def test_update_importance(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("some content", importance=0.3)
        updated = manager.update(entry.id, importance=0.9)
        assert updated is not None
        assert updated.importance == 0.9

    def test_update_nonexistent(self, manager: AgentMemoryManager) -> None:
        result = manager.update("nonexistent-id", content="x")
        assert result is None

    def test_update_evicted_returns_none(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("soon gone")
        manager.evict(entry.id)
        result = manager.update(entry.id, content="too late")
        assert result is None


class TestEvict:
    def test_evict_success(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("to evict")
        assert manager.evict(entry.id) is True
        assert entry.status == MemoryStatus.EVICTED

    def test_evict_nonexistent(self, manager: AgentMemoryManager) -> None:
        assert manager.evict("nonexistent") is False

    def test_evict_already_evicted(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("to evict")
        manager.evict(entry.id)
        assert manager.evict(entry.id) is False

    def test_evicted_not_retrieved(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("evictable content about Kubernetes")
        manager.evict(entry.id)
        query = MemoryQuery(query_text="Kubernetes")
        results = manager.retrieve(query)
        assert all(r.entry.id != entry.id for r in results)


class TestDecay:
    def test_decay_factor_fresh(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("fresh memory")
        decay = manager._apply_decay(entry)
        # Just created, decay should be near 1.0
        assert decay > 0.99

    def test_decay_factor_decreases_with_age(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("aging memory")
        # Simulate 100 hours old
        entry.last_accessed = time.time() - 360_000
        decay = manager._apply_decay(entry)
        assert decay < 0.5

    def test_decay_marks_status(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("very old")
        # Simulate very old (1000 hours)
        entry.last_accessed = time.time() - 3_600_000
        manager._apply_decay(entry)
        assert entry.status == MemoryStatus.DECAYED


class TestConflictResolution:
    def test_conflict_archives_old(self) -> None:
        mgr = AgentMemoryManager(similarity_threshold=0.6)
        e1 = mgr.store("The API uses REST with JSON responses")
        _e2 = mgr.store("The API uses REST with XML responses")
        # e1 should be archived because e2 supersedes it (high overlap)
        assert e1.status == MemoryStatus.ARCHIVED

    def test_no_conflict_for_different_content(self, manager: AgentMemoryManager) -> None:
        e1 = manager.store("The sky is blue")
        _e2 = manager.store("Python is a programming language")
        assert e1.status == MemoryStatus.ACTIVE


class TestCompression:
    def test_compress_merges_similar(self, manager: AgentMemoryManager) -> None:
        manager.store("The database uses PostgreSQL for storage operations")
        manager.store("The database uses PostgreSQL for storage tasks")
        count = manager._compress_similar(threshold=0.5)
        assert count >= 1

    def test_compress_no_op_on_dissimilar(self, manager: AgentMemoryManager) -> None:
        manager.store("apples and oranges")
        manager.store("quantum physics theories")
        count = manager._compress_similar()
        assert count == 0


class TestEvictionPolicy:
    def test_evict_when_over_capacity(self, small_manager: AgentMemoryManager) -> None:
        for i in range(7):
            small_manager.store(f"memory number {i} with unique words set{i}")
        stats = small_manager.get_stats()
        active = stats.active + stats.decayed
        assert active <= 5

    def test_lru_eviction(self) -> None:
        mgr = AgentMemoryManager(max_entries=3, eviction_policy=EvictionPolicy.LRU)
        e1 = mgr.store("first entry about alpha")
        _e2 = mgr.store("second entry about beta")
        _e3 = mgr.store("third entry about gamma")
        # Access e1 to make it recent
        e1.last_accessed = time.time()
        _e4 = mgr.store("fourth entry about delta")
        # e1 was accessed most recently, so one of the others should be evicted
        assert e1.status == MemoryStatus.ACTIVE

    def test_importance_eviction(self) -> None:
        mgr = AgentMemoryManager(max_entries=3, eviction_policy=EvictionPolicy.IMPORTANCE)
        e1 = mgr.store("low importance entry alpha", importance=0.1)
        _e2 = mgr.store("high importance entry beta", importance=0.9)
        _e3 = mgr.store("high importance entry gamma", importance=0.9)
        _e4 = mgr.store("high importance entry delta", importance=0.9)
        # Low importance should be evicted first
        assert e1.status == MemoryStatus.EVICTED


class TestStats:
    def test_stats_empty(self, manager: AgentMemoryManager) -> None:
        stats = manager.get_stats()
        assert isinstance(stats, MemoryStats)
        assert stats.total_entries == 0
        assert stats.avg_importance == 0.0

    def test_stats_populated(self, populated_manager: AgentMemoryManager) -> None:
        stats = populated_manager.get_stats()
        assert stats.total_entries == 4
        assert stats.active >= 1
        assert stats.avg_importance > 0.0
        assert stats.avg_age_hours >= 0.0


class TestContextWindow:
    def test_context_window_respects_budget(self, populated_manager: AgentMemoryManager) -> None:
        results = populated_manager.get_context_window("deployment", token_budget=10)
        total_est = sum(
            populated_manager._estimate_tokens(r.entry.content) for r in results
        )
        assert total_est <= 10

    def test_context_window_returns_most_relevant(
        self, populated_manager: AgentMemoryManager,
    ) -> None:
        results = populated_manager.get_context_window("Kubernetes deployment", token_budget=500)
        assert len(results) >= 1


class TestClearSession:
    def test_clear_session_archives_short_term(self, populated_manager: AgentMemoryManager) -> None:
        count = populated_manager.clear_session()
        assert count >= 1
        # Verify no active short-term memories remain
        for entry in populated_manager._memories.values():
            if entry.memory_type == MemoryType.SHORT_TERM:
                assert entry.status != MemoryStatus.ACTIVE

    def test_clear_session_keeps_long_term(self, populated_manager: AgentMemoryManager) -> None:
        populated_manager.clear_session()
        long_term = [
            e for e in populated_manager._memories.values()
            if e.memory_type == MemoryType.LONG_TERM and e.status == MemoryStatus.ACTIVE
        ]
        assert len(long_term) >= 1


class TestAuditLog:
    def test_audit_log_tracks_operations(self, manager: AgentMemoryManager) -> None:
        entry = manager.store("audit test")
        manager.retrieve(MemoryQuery(query_text="audit"))
        manager.update(entry.id, content="updated")
        manager.evict(entry.id)

        log = manager.get_audit_log()
        actions = [e["action"] for e in log]
        assert "store" in actions
        assert "retrieve" in actions
        assert "update" in actions
        assert "evict" in actions

    def test_audit_log_is_copy(self, manager: AgentMemoryManager) -> None:
        manager.store("something")
        log = manager.get_audit_log()
        log.clear()
        assert len(manager.get_audit_log()) > 0


class TestTokenEstimation:
    def test_estimate_tokens_short(self, manager: AgentMemoryManager) -> None:
        tokens = manager._estimate_tokens("hello world")
        assert tokens >= 1

    def test_estimate_tokens_long(self, manager: AgentMemoryManager) -> None:
        text = " ".join(["word"] * 100)
        tokens = manager._estimate_tokens(text)
        assert tokens > 100
