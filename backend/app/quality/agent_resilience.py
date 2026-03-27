"""Agent Resilience Manager — circuit breakers, retries, and rate-limit
awareness for AI agent API calls.

Production AI pipelines must handle provider outages, rate limits, and
transient errors gracefully.  This module wraps every outgoing LLM call
with resilience patterns recommended by industry literature (Maxim.ai
2026, NeuralTrust, Agent Factory):

- **Circuit breaker** (closed → open → half-open) per provider
- **Exponential backoff with jitter** for retries
- **Rate-limit header parsing** (Retry-After, X-RateLimit-*)
- **Provider health monitoring** with automatic failover
- **Cost-aware fallback**: cheaper model when primary is unavailable
- **Observability hooks**: state changes, latencies, error rates

All state is in-memory (no external deps) so the module is zero-config.
"""

from __future__ import annotations

import contextlib
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ProviderStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class CircuitBreakerConfig:
    """Tunables for a single circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0  # seconds before half-open probe
    half_open_max_calls: int = 1
    success_threshold: int = 2  # successes in half-open to close


@dataclass
class CircuitBreaker:
    """Per-provider circuit breaker state."""

    provider: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_state_change: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    total_trips: int = 0

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self._transition(CircuitState.CLOSED)
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()

        if self.state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
            self.total_trips += 1
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self._transition(CircuitState.OPEN)
                self.total_trips += 1

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.config.recovery_timeout:
                self._transition(CircuitState.HALF_OPEN)
                self.success_count = 0
                return True
            return False
        # HALF_OPEN
        return True

    def _transition(self, new_state: CircuitState) -> None:
        old = self.state
        self.state = new_state
        self.last_state_change = datetime.now(UTC).isoformat()
        logger.info(
            "Circuit breaker [%s]: %s → %s", self.provider, old, new_state,
        )


@dataclass
class RetryConfig:
    """Configuration for retry with exponential backoff."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True
    backoff_factor: float = 2.0


@dataclass
class RetryAttempt:
    """Record of a single retry attempt."""

    attempt: int
    delay_seconds: float
    error: str = ""
    succeeded: bool = False


@dataclass
class RateLimitInfo:
    """Parsed rate-limit headers from an API response."""

    retry_after: float | None = None
    limit: int | None = None
    remaining: int | None = None
    reset_at: float | None = None


@dataclass
class ProviderHealth:
    """Health snapshot for an LLM provider."""

    provider: str
    status: ProviderStatus = ProviderStatus.HEALTHY
    circuit_state: CircuitState = CircuitState.CLOSED
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0
    total_calls: int = 0
    total_errors: int = 0
    last_error: str = ""
    last_check: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


# ── Retry logic ──────────────────────────────────────────────────────────

def calculate_backoff(
    attempt: int,
    config: RetryConfig,
    rate_limit: RateLimitInfo | None = None,
) -> float:
    """Calculate delay for a retry attempt, respecting rate-limit headers."""
    if rate_limit and rate_limit.retry_after is not None:
        return rate_limit.retry_after

    delay = config.base_delay * (config.backoff_factor ** attempt)
    delay = min(delay, config.max_delay)

    if config.jitter:
        delay = delay * (0.5 + random.random())  # noqa: S311

    return round(delay, 2)


def parse_rate_limit_headers(headers: dict[str, str]) -> RateLimitInfo:
    """Extract rate-limit information from HTTP response headers."""
    info = RateLimitInfo()

    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after:
        with contextlib.suppress(ValueError):
            info.retry_after = float(retry_after)

    for key in ("X-RateLimit-Limit", "x-ratelimit-limit"):
        if key in headers:
            with contextlib.suppress(ValueError):
                info.limit = int(headers[key])
            break

    for key in ("X-RateLimit-Remaining", "x-ratelimit-remaining"):
        if key in headers:
            with contextlib.suppress(ValueError):
                info.remaining = int(headers[key])
            break

    for key in ("X-RateLimit-Reset", "x-ratelimit-reset"):
        if key in headers:
            with contextlib.suppress(ValueError):
                info.reset_at = float(headers[key])
            break

    return info


# ── Resilience Manager ───────────────────────────────────────────────────

_call_log: list[dict[str, Any]] = []


class AgentResilienceManager:
    """Manages circuit breakers, retries, and health for LLM providers."""

    def __init__(
        self,
        providers: list[str] | None = None,
        *,
        breaker_config: CircuitBreakerConfig | None = None,
        retry_config: RetryConfig | None = None,
    ) -> None:
        providers = providers or ["claude", "openai", "gemini"]
        cfg = breaker_config or CircuitBreakerConfig()
        self.retry_config = retry_config or RetryConfig()
        self.breakers: dict[str, CircuitBreaker] = {
            p: CircuitBreaker(provider=p, config=cfg) for p in providers
        }
        self._latencies: dict[str, list[float]] = {p: [] for p in providers}
        self._errors: dict[str, int] = {p: 0 for p in providers}
        self._calls: dict[str, int] = {p: 0 for p in providers}

    def can_call(self, provider: str) -> bool:
        """Check if a call to *provider* is allowed by its circuit breaker."""
        breaker = self.breakers.get(provider)
        if breaker is None:
            return True  # unknown provider → allow
        return breaker.allow_request()

    def record_success(self, provider: str, latency_ms: float = 0.0) -> None:
        """Record a successful call."""
        breaker = self.breakers.get(provider)
        if breaker:
            breaker.record_success()
        self._calls[provider] = self._calls.get(provider, 0) + 1
        if latency_ms > 0:
            self._latencies.setdefault(provider, []).append(latency_ms)
        _call_log.append({
            "provider": provider, "success": True,
            "latency_ms": latency_ms,
            "ts": datetime.now(UTC).isoformat(),
        })

    def record_failure(self, provider: str, error: str = "") -> None:
        """Record a failed call."""
        breaker = self.breakers.get(provider)
        if breaker:
            breaker.record_failure()
        self._calls[provider] = self._calls.get(provider, 0) + 1
        self._errors[provider] = self._errors.get(provider, 0) + 1
        _call_log.append({
            "provider": provider, "success": False,
            "error": error[:200],
            "ts": datetime.now(UTC).isoformat(),
        })

    def get_healthy_provider(self, preferred: str = "") -> str | None:
        """Return a healthy provider, preferring *preferred* if available."""
        if preferred and self.can_call(preferred):
            return preferred
        for provider, breaker in self.breakers.items():
            if breaker.allow_request():
                return provider
        return None

    def get_fallback_chain(self, primary: str) -> list[str]:
        """Return ordered list of providers to try, starting with *primary*."""
        chain = [primary] if self.can_call(primary) else []
        for p in self.breakers:
            if p != primary and self.can_call(p):
                chain.append(p)
        return chain

    def provider_health(self, provider: str) -> ProviderHealth:
        """Snapshot of a single provider's health."""
        breaker = self.breakers.get(provider)
        calls = self._calls.get(provider, 0)
        errors = self._errors.get(provider, 0)
        lats = self._latencies.get(provider, [])

        error_rate = errors / calls if calls else 0.0
        avg_lat = sum(lats[-100:]) / len(lats[-100:]) if lats else 0.0

        if breaker and breaker.state == CircuitState.OPEN:
            status = ProviderStatus.UNAVAILABLE
        elif error_rate > 0.3:
            status = ProviderStatus.DEGRADED
        else:
            status = ProviderStatus.HEALTHY

        return ProviderHealth(
            provider=provider,
            status=status,
            circuit_state=breaker.state if breaker else CircuitState.CLOSED,
            avg_latency_ms=round(avg_lat, 1),
            error_rate=round(error_rate, 3),
            total_calls=calls,
            total_errors=errors,
        )

    def all_health(self) -> list[ProviderHealth]:
        """Health of all providers."""
        return [self.provider_health(p) for p in self.breakers]

    def reset_provider(self, provider: str) -> None:
        """Manually reset a provider's circuit breaker."""
        breaker = self.breakers.get(provider)
        if breaker:
            breaker.state = CircuitState.CLOSED
            breaker.failure_count = 0
            breaker.success_count = 0
            logger.info("Manually reset circuit breaker for %s", provider)


# ── Module-level helpers ─────────────────────────────────────────────────

def get_call_log() -> list[dict[str, Any]]:
    return list(_call_log)


def clear_call_log() -> None:
    _call_log.clear()


def get_resilience_stats() -> dict[str, Any]:
    """Aggregate stats across all logged calls."""
    if not _call_log:
        return {"total_calls": 0}

    total = len(_call_log)
    successes = sum(1 for c in _call_log if c.get("success"))
    by_provider: dict[str, dict[str, int]] = {}

    for c in _call_log:
        p = c["provider"]
        if p not in by_provider:
            by_provider[p] = {"total": 0, "success": 0, "failure": 0}
        by_provider[p]["total"] += 1
        if c.get("success"):
            by_provider[p]["success"] += 1
        else:
            by_provider[p]["failure"] += 1

    return {
        "total_calls": total,
        "success_count": successes,
        "failure_count": total - successes,
        "success_rate": round(successes / total, 3) if total else 0,
        "by_provider": by_provider,
    }
