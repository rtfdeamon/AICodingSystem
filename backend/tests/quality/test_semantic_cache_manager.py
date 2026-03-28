"""Tests for Semantic Cache Manager."""

from __future__ import annotations

import pytest

from app.quality.semantic_cache_manager import (
    BatchCacheReport,
    CacheEntry,
    CacheLayer,
    CacheStats,
    GateDecision,
    SemanticCacheManager,
    _cosine_similarity,
    _hash_prompt,
    _longest_common_prefix_len,
    _simple_embedding,
)

# ── Helper tests ─────────────────────────────────────────────────────────

class TestHashPrompt:
    def test_deterministic(self):
        assert _hash_prompt("hello") == _hash_prompt("hello")

    def test_different_inputs(self):
        assert _hash_prompt("hello") != _hash_prompt("world")

    def test_empty_string(self):
        h = _hash_prompt("")
        assert isinstance(h, str) and len(h) == 64


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)

    def test_empty_vectors(self):
        assert _cosine_similarity([], []) == 0.0

    def test_different_lengths(self):
        assert _cosine_similarity([1, 2], [1, 2, 3]) == 0.0

    def test_zero_vector(self):
        assert _cosine_similarity([0, 0], [1, 1]) == 0.0


class TestSimpleEmbedding:
    def test_correct_dimension(self):
        emb = _simple_embedding("test", dim=32)
        assert len(emb) == 32

    def test_normalized(self):
        emb = _simple_embedding("hello world", dim=64)
        magnitude = sum(v * v for v in emb) ** 0.5
        assert magnitude == pytest.approx(1.0, abs=0.01)

    def test_similar_texts(self):
        e1 = _simple_embedding("review this code change")
        e2 = _simple_embedding("review this code change please")
        sim = _cosine_similarity(e1, e2)
        assert sim > 0.8

    def test_different_texts(self):
        e1 = _simple_embedding("hello world")
        e2 = _simple_embedding("xyz 12345 !@#$%")
        sim = _cosine_similarity(e1, e2)
        assert sim < 0.9

    def test_empty_text(self):
        emb = _simple_embedding("")
        assert all(v == 0.0 for v in emb)


class TestLongestCommonPrefix:
    def test_identical(self):
        assert _longest_common_prefix_len("abc", "abc") == 3

    def test_partial(self):
        assert _longest_common_prefix_len("abcdef", "abcxyz") == 3

    def test_no_common(self):
        assert _longest_common_prefix_len("abc", "xyz") == 0

    def test_empty(self):
        assert _longest_common_prefix_len("", "abc") == 0


# ── Cache manager tests ─────────────────────────────────────────────────

class TestSemanticCacheManager:
    def setup_method(self):
        self.cache = SemanticCacheManager(
            max_entries=100,
            ttl_seconds=3600,
            semantic_threshold=0.90,
            prefix_min_ratio=0.85,
        )

    def test_put_returns_entry(self):
        entry = self.cache.put("prompt", "response", model="claude-sonnet")
        assert isinstance(entry, CacheEntry)
        assert entry.response == "response"
        assert entry.model == "claude-sonnet"

    def test_exact_hit(self):
        self.cache.put("hello world", "response1")
        result = self.cache.lookup("hello world")
        assert result.hit is True
        assert result.layer == CacheLayer.EXACT
        assert result.similarity == 1.0

    def test_exact_miss(self):
        self.cache.put("hello world", "response1")
        result = self.cache.lookup("goodbye world")
        assert result.layer in (CacheLayer.SEMANTIC, CacheLayer.MISS)

    def test_prefix_hit(self):
        # Long shared prefix
        base = "You are a code reviewer. Review this Python code: " * 3
        self.cache.put(base + "def foo(): pass", "review1")
        result = self.cache.lookup(base + "def bar(): pass")
        assert result.hit is True
        assert result.layer in (CacheLayer.PREFIX, CacheLayer.EXACT, CacheLayer.SEMANTIC)

    def test_semantic_hit(self):
        self.cache.put("review this code change", "looks good")
        result = self.cache.lookup("review this code change")
        # Exact match since identical
        assert result.hit is True

    def test_miss(self):
        result = self.cache.lookup("completely new prompt")
        assert result.hit is False
        assert result.layer == CacheLayer.MISS

    def test_model_filtering(self):
        self.cache.put("prompt", "response", model="claude-sonnet")
        # Exact match works regardless of model (hash-based)
        result = self.cache.lookup("prompt", model="gpt-4o")
        assert result.hit is True  # exact match ignores model

    def test_invalidate(self):
        self.cache.put("prompt", "response")
        assert self.cache.invalidate("prompt") is True
        result = self.cache.lookup("prompt")
        assert result.hit is False

    def test_invalidate_nonexistent(self):
        assert self.cache.invalidate("nope") is False

    def test_clear(self):
        self.cache.put("p1", "r1")
        self.cache.put("p2", "r2")
        count = self.cache.clear()
        assert count == 2
        assert self.cache.lookup("p1").hit is False

    def test_lru_eviction(self):
        small_cache = SemanticCacheManager(max_entries=3)
        small_cache.put("p1", "r1")
        small_cache.put("p2", "r2")
        small_cache.put("p3", "r3")
        small_cache.put("p4", "r4")  # Should evict p1
        assert small_cache.lookup("p1").hit is False
        assert small_cache.lookup("p4").hit is True

    def test_access_count(self):
        self.cache.put("prompt", "response")
        self.cache.lookup("prompt")
        self.cache.lookup("prompt")
        entry = self.cache._exact[_hash_prompt("prompt")]
        assert entry.access_count == 2

    def test_cost_saved_tracked(self):
        self.cache.put("prompt", "response", prompt_tokens=1000, response_tokens=500)
        result = self.cache.lookup("prompt")
        assert result.cost_saved_usd > 0


class TestCacheStats:
    def setup_method(self):
        self.cache = SemanticCacheManager()

    def test_initial_stats(self):
        stats = self.cache.stats()
        assert isinstance(stats, CacheStats)
        assert stats.total_lookups == 0
        assert stats.entries_count == 0

    def test_stats_after_hits(self):
        self.cache.put("p1", "r1")
        self.cache.lookup("p1")
        self.cache.lookup("p1")
        stats = self.cache.stats()
        assert stats.exact_hits == 2
        assert stats.hit_rate > 0

    def test_stats_after_misses(self):
        self.cache.lookup("miss1")
        self.cache.lookup("miss2")
        stats = self.cache.stats()
        assert stats.misses == 2
        assert stats.hit_rate == 0.0
        assert stats.gate_decision == GateDecision.UNHEALTHY

    def test_healthy_hit_rate(self):
        self.cache.put("p1", "r1")
        for _ in range(10):
            self.cache.lookup("p1")
        stats = self.cache.stats()
        assert stats.gate_decision == GateDecision.HEALTHY

    def test_cost_savings(self):
        self.cache.put("p1", "r1", prompt_tokens=5000, response_tokens=2000)
        self.cache.lookup("p1")
        stats = self.cache.stats()
        assert stats.estimated_cost_saved_usd > 0

    def test_latency_savings(self):
        self.cache.put("p1", "r1")
        self.cache.lookup("p1")
        stats = self.cache.stats()
        assert stats.estimated_latency_saved_ms > 0

    def test_eviction_count(self):
        small = SemanticCacheManager(max_entries=2)
        small.put("p1", "r1")
        small.put("p2", "r2")
        small.put("p3", "r3")
        stats = small.stats()
        assert stats.evictions == 1


class TestBatchCacheLookup:
    def setup_method(self):
        self.cache = SemanticCacheManager()

    def test_batch_all_hits(self):
        self.cache.put("p1", "r1")
        self.cache.put("p2", "r2")
        report = self.cache.batch_lookup(["p1", "p2"])
        assert isinstance(report, BatchCacheReport)
        assert report.hits == 2
        assert report.hit_rate == 1.0

    def test_batch_all_misses(self):
        report = self.cache.batch_lookup(["miss1", "miss2"])
        assert report.hits == 0
        assert report.hit_rate == 0.0

    def test_batch_mixed(self):
        self.cache.put("p1", "r1")
        report = self.cache.batch_lookup(["p1", "miss1"])
        assert report.hits == 1
        assert report.hit_rate == 0.5

    def test_batch_empty(self):
        report = self.cache.batch_lookup([])
        assert report.total_lookups == 0

    def test_batch_cost(self):
        self.cache.put("p1", "r1", prompt_tokens=1000, response_tokens=500)
        report = self.cache.batch_lookup(["p1"])
        assert report.total_cost_saved_usd > 0

    def test_batch_gate_decision(self):
        # All misses → unhealthy
        report = self.cache.batch_lookup(["m1", "m2", "m3"])
        assert report.gate_decision == GateDecision.UNHEALTHY
