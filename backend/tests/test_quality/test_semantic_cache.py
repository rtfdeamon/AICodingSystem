"""Tests for semantic response cache module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.quality.semantic_cache import (
    CacheHitType,
    cache_entry_to_json,
    cache_invalidate,
    cache_lookup,
    cache_store,
    clear_cache,
    compute_prompt_hash,
    compute_simple_embedding,
    cosine_similarity,
    evict_expired,
    get_cache_stats,
)

# ── Fixtures / helpers ────────────────────────────────────────────────


def _setup() -> None:
    """Reset cache state before each logical test group."""
    clear_cache()


# ── Prompt hash ───────────────────────────────────────────────────────


class TestPromptHash:
    def test_deterministic(self) -> None:
        h1 = compute_prompt_hash("hello world")
        h2 = compute_prompt_hash("hello world")
        assert h1 == h2

    def test_normalises_whitespace(self) -> None:
        h1 = compute_prompt_hash("hello   world")
        h2 = compute_prompt_hash("hello world")
        assert h1 == h2

    def test_case_insensitive(self) -> None:
        h1 = compute_prompt_hash("Hello World")
        h2 = compute_prompt_hash("hello world")
        assert h1 == h2

    def test_different_prompts_differ(self) -> None:
        h1 = compute_prompt_hash("hello world")
        h2 = compute_prompt_hash("goodbye world")
        assert h1 != h2


# ── Cosine similarity ────────────────────────────────────────────────


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert cosine_similarity(v, v) == 1.0

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-9

    def test_empty_vectors(self) -> None:
        assert cosine_similarity([], []) == 0.0

    def test_one_empty_vector(self) -> None:
        assert cosine_similarity([1.0, 2.0], []) == 0.0

    def test_zero_vector(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_different_lengths_padded(self) -> None:
        # shorter vector padded with zeros
        a = [1.0, 0.0, 0.0]
        b = [1.0]
        assert cosine_similarity(a, b) == 1.0


# ── Simple embedding ─────────────────────────────────────────────────


class TestSimpleEmbedding:
    def test_empty_text(self) -> None:
        assert compute_simple_embedding("") == []

    def test_single_word(self) -> None:
        emb = compute_simple_embedding("hello")
        assert emb == [1.0]

    def test_repeated_word(self) -> None:
        emb = compute_simple_embedding("go go go")
        assert emb == [1.0]

    def test_two_words_equal_frequency(self) -> None:
        emb = compute_simple_embedding("alpha beta")
        assert len(emb) == 2
        assert all(abs(v - 0.5) < 1e-9 for v in emb)


# ── Exact cache hits ─────────────────────────────────────────────────


class TestExactCacheHit:
    def setup_method(self) -> None:
        _setup()

    def test_exact_hit_returns_response(self) -> None:
        cache_store("What is Python?", "A programming language", "gpt-4")
        result = cache_lookup("What is Python?")
        assert result.hit_type == CacheHitType.EXACT
        assert result.response == "A programming language"
        assert result.similarity_score == 1.0

    def test_exact_hit_normalised_prompt(self) -> None:
        cache_store("what is python?", "A language", "gpt-4")
        result = cache_lookup("  What   Is   Python?  ")
        assert result.hit_type == CacheHitType.EXACT


# ── Semantic cache hits ──────────────────────────────────────────────


class TestSemanticCacheHit:
    def setup_method(self) -> None:
        _setup()

    def test_similar_prompt_returns_semantic_hit(self) -> None:
        cache_store("explain python programming language", "Python is ...", "gpt-4")
        # Same words, slightly different order — high similarity
        result = cache_lookup(
            "explain python programming language please",
            similarity_threshold=0.5,
        )
        assert result.hit_type in (CacheHitType.EXACT, CacheHitType.SEMANTIC)
        assert result.response is not None


# ── Cache miss ────────────────────────────────────────────────────────


class TestCacheMiss:
    def setup_method(self) -> None:
        _setup()

    def test_empty_cache_returns_miss(self) -> None:
        result = cache_lookup("anything")
        assert result.hit_type == CacheHitType.MISS
        assert result.response is None
        assert result.entry_id is None

    def test_different_prompt_returns_miss(self) -> None:
        cache_store("What is Python?", "A language", "gpt-4")
        result = cache_lookup("What is the weather today?")
        assert result.hit_type == CacheHitType.MISS


# ── TTL expiration ────────────────────────────────────────────────────


class TestTTLExpiration:
    def setup_method(self) -> None:
        _setup()

    def test_expired_entry_is_miss(self) -> None:
        entry = cache_store("What is Python?", "A language", "gpt-4", ttl_seconds=1)
        # Patch created_at to be in the past
        entry.created_at = datetime.now(UTC) - timedelta(seconds=10)
        result = cache_lookup("What is Python?")
        assert result.hit_type == CacheHitType.MISS

    def test_evict_expired_removes_entries(self) -> None:
        entry = cache_store("old prompt", "old response", "gpt-4", ttl_seconds=1)
        entry.created_at = datetime.now(UTC) - timedelta(seconds=10)
        evicted = evict_expired()
        assert evicted == 1

    def test_evict_keeps_valid_entries(self) -> None:
        cache_store("fresh prompt", "fresh response", "gpt-4", ttl_seconds=9999)
        evicted = evict_expired()
        assert evicted == 0


# ── Cache invalidation ───────────────────────────────────────────────


class TestCacheInvalidation:
    def setup_method(self) -> None:
        _setup()

    def test_invalidate_existing_entry(self) -> None:
        entry = cache_store("prompt", "response", "gpt-4")
        assert cache_invalidate(entry.id) is True
        result = cache_lookup("prompt")
        assert result.hit_type == CacheHitType.MISS

    def test_invalidate_nonexistent_entry(self) -> None:
        assert cache_invalidate("nonexistent-id") is False


# ── Hit count tracking ───────────────────────────────────────────────


class TestHitCountTracking:
    def setup_method(self) -> None:
        _setup()

    def test_hit_count_increments(self) -> None:
        entry = cache_store("prompt", "response", "gpt-4")
        assert entry.hit_count == 0
        cache_lookup("prompt")
        assert entry.hit_count == 1
        cache_lookup("prompt")
        assert entry.hit_count == 2

    def test_last_hit_at_updated(self) -> None:
        entry = cache_store("prompt", "response", "gpt-4")
        assert entry.last_hit_at is None
        cache_lookup("prompt")
        assert entry.last_hit_at is not None


# ── Cache stats ──────────────────────────────────────────────────────


class TestCacheStats:
    def setup_method(self) -> None:
        _setup()

    def test_initial_stats_zero(self) -> None:
        stats = get_cache_stats()
        assert stats.total_requests == 0
        assert stats.hit_rate == 0.0

    def test_stats_after_hit_and_miss(self) -> None:
        cache_store("prompt", "response", "gpt-4")
        cache_lookup("prompt")  # exact hit
        cache_lookup("totally different prompt")  # miss
        stats = get_cache_stats()
        assert stats.total_requests == 2
        assert stats.exact_hits == 1
        assert stats.misses == 1
        assert stats.hit_rate == 50.0


# ── JSON serialisation ───────────────────────────────────────────────


class TestJsonSerialisation:
    def setup_method(self) -> None:
        _setup()

    def test_basic_serialisation(self) -> None:
        entry = cache_store("prompt", "response", "gpt-4")
        data = cache_entry_to_json(entry)
        assert data["id"] == entry.id
        assert data["response"] == "response"
        assert data["model_id"] == "gpt-4"
        assert data["last_hit_at"] is None
        assert isinstance(data["created_at"], str)

    def test_serialisation_after_hit(self) -> None:
        entry = cache_store("prompt", "response", "gpt-4")
        cache_lookup("prompt")
        data = cache_entry_to_json(entry)
        assert data["hit_count"] == 1
        assert data["last_hit_at"] is not None


# ── Clear cache ──────────────────────────────────────────────────────


class TestClearCache:
    def test_clear_resets_everything(self) -> None:
        cache_store("prompt", "response", "gpt-4")
        cache_lookup("prompt")
        clear_cache()
        stats = get_cache_stats()
        assert stats.total_requests == 0
        result = cache_lookup("prompt")
        assert result.hit_type == CacheHitType.MISS
