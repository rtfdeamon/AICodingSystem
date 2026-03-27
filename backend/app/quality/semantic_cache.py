"""Semantic Response Cache — caches AI responses for exact and semantic reuse.

Provides two-tier caching for AI model responses:
- Exact match: SHA-256 hash of normalised prompt text
- Semantic match: cosine similarity of simple word-frequency embeddings

Designed for in-memory use (MVP); can be backed by Redis / vector DB later.
"""

from __future__ import annotations

import hashlib
import logging
import math
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────


class CacheHitType(StrEnum):
    EXACT = "exact"
    SEMANTIC = "semantic"
    MISS = "miss"


@dataclass
class CacheEntry:
    """A single cached AI response."""

    id: str
    prompt_hash: str
    prompt_embedding: list[float]
    response: str
    model_id: str
    created_at: datetime
    ttl_seconds: int
    hit_count: int = 0
    last_hit_at: datetime | None = None


@dataclass
class CacheResult:
    """Outcome of a cache lookup."""

    hit_type: CacheHitType
    response: str | None
    similarity_score: float
    entry_id: str | None


@dataclass
class CacheStats:
    """Aggregated cache statistics."""

    total_requests: int = 0
    exact_hits: int = 0
    semantic_hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    avg_similarity: float = 0.0


# ── In-memory stores ─────────────────────────────────────────────────

_exact_cache: dict[str, CacheEntry] = {}
_semantic_cache: list[CacheEntry] = []

# Stats accumulators
_stats: dict[str, int | float] = {
    "total_requests": 0,
    "exact_hits": 0,
    "semantic_hits": 0,
    "misses": 0,
    "similarity_sum": 0.0,
}


# ── Helper functions ─────────────────────────────────────────────────


def compute_prompt_hash(prompt: str) -> str:
    """Return the SHA-256 hex digest of a whitespace-normalised, lower-cased prompt."""
    normalised = " ".join(prompt.lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()


def compute_simple_embedding(text: str) -> list[float]:
    """Build a simple word-frequency embedding (no ML dependencies).

    Tokenises on whitespace + lowercases, then returns a sorted-vocabulary
    frequency vector.  Adequate for testing; swap for a real encoder in prod.
    """
    words = text.lower().split()
    if not words:
        return []
    counts = Counter(words)
    total = len(words)
    vocab = sorted(counts.keys())
    return [counts[w] / total for w in vocab]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns 0.0 when either vector is zero-length or all-zeros.
    """
    if not a or not b:
        return 0.0
    # Pad to equal length
    length = max(len(a), len(b))
    va = list(a) + [0.0] * (length - len(a))
    vb = list(b) + [0.0] * (length - len(b))

    dot = sum(x * y for x, y in zip(va, vb, strict=False))
    norm_a = math.sqrt(sum(x * x for x in va))
    norm_b = math.sqrt(sum(x * x for x in vb))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Core API ─────────────────────────────────────────────────────────


def cache_lookup(
    prompt: str,
    similarity_threshold: float = 0.92,
) -> CacheResult:
    """Look up a prompt in the cache (exact first, then semantic).

    Parameters
    ----------
    prompt:
        The user prompt to look up.
    similarity_threshold:
        Minimum cosine similarity for a semantic hit (default 0.92).

    Returns
    -------
    CacheResult with hit_type, response, similarity_score, and entry_id.
    """
    _stats["total_requests"] += 1
    prompt_hash = compute_prompt_hash(prompt)

    # 1. Exact match
    entry = _exact_cache.get(prompt_hash)
    if entry is not None:
        now = datetime.now(UTC)
        age = (now - entry.created_at).total_seconds()
        if age <= entry.ttl_seconds:
            entry.hit_count += 1
            entry.last_hit_at = now
            _stats["exact_hits"] += 1
            _stats["similarity_sum"] += 1.0
            logger.debug("Exact cache hit for prompt hash %s", prompt_hash[:12])
            return CacheResult(
                hit_type=CacheHitType.EXACT,
                response=entry.response,
                similarity_score=1.0,
                entry_id=entry.id,
            )

    # 2. Semantic match
    embedding = compute_simple_embedding(prompt)
    best_score = 0.0
    best_entry: CacheEntry | None = None

    for candidate in _semantic_cache:
        now = datetime.now(UTC)
        age = (now - candidate.created_at).total_seconds()
        if age > candidate.ttl_seconds:
            continue
        score = cosine_similarity(embedding, candidate.prompt_embedding)
        if score > best_score:
            best_score = score
            best_entry = candidate

    _stats["similarity_sum"] += best_score

    if best_entry is not None and best_score >= similarity_threshold:
        now = datetime.now(UTC)
        best_entry.hit_count += 1
        best_entry.last_hit_at = now
        _stats["semantic_hits"] += 1
        logger.debug(
            "Semantic cache hit (score=%.4f) for entry %s",
            best_score,
            best_entry.id[:12],
        )
        return CacheResult(
            hit_type=CacheHitType.SEMANTIC,
            response=best_entry.response,
            similarity_score=best_score,
            entry_id=best_entry.id,
        )

    # 3. Miss
    _stats["misses"] += 1
    logger.debug("Cache miss for prompt hash %s", prompt_hash[:12])
    return CacheResult(
        hit_type=CacheHitType.MISS,
        response=None,
        similarity_score=best_score,
        entry_id=None,
    )


def cache_store(
    prompt: str,
    response: str,
    model_id: str,
    ttl_seconds: int = 3600,
) -> CacheEntry:
    """Store a prompt/response pair in both exact and semantic caches.

    Parameters
    ----------
    prompt:
        The original user prompt.
    response:
        The AI-generated response to cache.
    model_id:
        Identifier of the model that produced the response.
    ttl_seconds:
        Time-to-live in seconds (default 3600).

    Returns
    -------
    The newly created CacheEntry.
    """
    prompt_hash = compute_prompt_hash(prompt)
    embedding = compute_simple_embedding(prompt)
    entry = CacheEntry(
        id=str(uuid.uuid4()),
        prompt_hash=prompt_hash,
        prompt_embedding=embedding,
        response=response,
        model_id=model_id,
        created_at=datetime.now(UTC),
        ttl_seconds=ttl_seconds,
        hit_count=0,
        last_hit_at=None,
    )
    _exact_cache[prompt_hash] = entry
    _semantic_cache.append(entry)
    logger.info("Cached response for prompt hash %s (ttl=%ds)", prompt_hash[:12], ttl_seconds)
    return entry


def cache_invalidate(entry_id: str) -> bool:
    """Remove a specific cache entry by id.

    Returns True if the entry was found and removed, False otherwise.
    """
    # Remove from semantic cache
    found = False
    _semantic_cache[:] = [e for e in _semantic_cache if e.id != entry_id]

    # Remove from exact cache
    keys_to_remove = [k for k, v in _exact_cache.items() if v.id == entry_id]
    for key in keys_to_remove:
        del _exact_cache[key]
        found = True

    if found:
        logger.info("Invalidated cache entry %s", entry_id)
    return found


def evict_expired() -> int:
    """Remove all expired entries from both caches.

    Returns the number of entries evicted.
    """
    now = datetime.now(UTC)
    count = 0

    # Evict from semantic cache
    surviving: list[CacheEntry] = []
    for entry in _semantic_cache:
        age = (now - entry.created_at).total_seconds()
        if age > entry.ttl_seconds:
            count += 1
        else:
            surviving.append(entry)
    _semantic_cache[:] = surviving

    # Evict from exact cache
    expired_keys = [
        k
        for k, v in _exact_cache.items()
        if (now - v.created_at).total_seconds() > v.ttl_seconds
    ]
    for key in expired_keys:
        del _exact_cache[key]

    if count:
        logger.info("Evicted %d expired cache entries", count)
    return count


def get_cache_stats() -> CacheStats:
    """Return aggregated cache statistics."""
    total = int(_stats["total_requests"])
    exact = int(_stats["exact_hits"])
    semantic = int(_stats["semantic_hits"])
    misses = int(_stats["misses"])
    sim_sum = float(_stats["similarity_sum"])

    hit_rate = ((exact + semantic) / total * 100) if total > 0 else 0.0
    avg_sim = (sim_sum / total) if total > 0 else 0.0

    return CacheStats(
        total_requests=total,
        exact_hits=exact,
        semantic_hits=semantic,
        misses=misses,
        hit_rate=round(hit_rate, 1),
        avg_similarity=round(avg_sim, 4),
    )


def clear_cache() -> None:
    """Clear all caches and reset stats.  Intended for test teardown."""
    _exact_cache.clear()
    _semantic_cache.clear()
    _stats["total_requests"] = 0
    _stats["exact_hits"] = 0
    _stats["semantic_hits"] = 0
    _stats["misses"] = 0
    _stats["similarity_sum"] = 0.0
    logger.debug("Cache cleared")


def cache_entry_to_json(entry: CacheEntry) -> dict:
    """Serialise a CacheEntry to a JSON-friendly dict."""
    return {
        "id": entry.id,
        "prompt_hash": entry.prompt_hash,
        "prompt_embedding": entry.prompt_embedding,
        "response": entry.response,
        "model_id": entry.model_id,
        "created_at": entry.created_at.isoformat(),
        "ttl_seconds": entry.ttl_seconds,
        "hit_count": entry.hit_count,
        "last_hit_at": entry.last_hit_at.isoformat() if entry.last_hit_at else None,
    }
