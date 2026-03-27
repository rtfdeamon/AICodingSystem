"""Tests for Agent Resilience Manager module."""

from __future__ import annotations

import time

from app.quality.agent_resilience import (
    AgentResilienceManager,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    ProviderStatus,
    RateLimitInfo,
    RetryConfig,
    calculate_backoff,
    clear_call_log,
    get_call_log,
    get_resilience_stats,
    parse_rate_limit_headers,
)


class TestCircuitBreaker:
    """Circuit breaker state machine tests."""

    def test_initial_state_closed(self) -> None:
        cb = CircuitBreaker(provider="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request()

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker(
            provider="test",
            config=CircuitBreakerConfig(failure_threshold=3),
        )
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_rejects_requests(self) -> None:
        cb = CircuitBreaker(
            provider="test",
            config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=999),
        )
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.allow_request()

    def test_half_open_after_timeout(self) -> None:
        cb = CircuitBreaker(
            provider="test",
            config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
        )
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.allow_request()
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self) -> None:
        cb = CircuitBreaker(
            provider="test",
            config=CircuitBreakerConfig(
                failure_threshold=1,
                recovery_timeout=0.01,
                success_threshold=2,
            ),
        )
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # transitions to half-open
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self) -> None:
        cb = CircuitBreaker(
            provider="test",
            config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
        )
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # half-open
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_failure_count(self) -> None:
        cb = CircuitBreaker(
            provider="test",
            config=CircuitBreakerConfig(failure_threshold=3),
        )
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0

    def test_total_trips_counted(self) -> None:
        cb = CircuitBreaker(
            provider="test",
            config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01),
        )
        cb.record_failure()  # trip 1
        assert cb.total_trips == 1
        time.sleep(0.02)
        cb.allow_request()  # half-open
        cb.record_failure()  # trip 2
        assert cb.total_trips == 2


class TestRetryBackoff:
    """Exponential backoff calculation tests."""

    def test_basic_backoff(self) -> None:
        config = RetryConfig(base_delay=1.0, backoff_factor=2.0, jitter=False)
        assert calculate_backoff(0, config) == 1.0
        assert calculate_backoff(1, config) == 2.0
        assert calculate_backoff(2, config) == 4.0

    def test_max_delay_cap(self) -> None:
        config = RetryConfig(base_delay=1.0, backoff_factor=2.0, max_delay=10.0, jitter=False)
        assert calculate_backoff(10, config) == 10.0

    def test_jitter_adds_randomness(self) -> None:
        config = RetryConfig(base_delay=1.0, backoff_factor=2.0, jitter=True)
        delays = {calculate_backoff(1, config) for _ in range(20)}
        assert len(delays) > 1  # should vary

    def test_rate_limit_retry_after(self) -> None:
        config = RetryConfig()
        rl = RateLimitInfo(retry_after=30.0)
        assert calculate_backoff(0, config, rl) == 30.0


class TestRateLimitParsing:
    """Parse rate-limit headers."""

    def test_retry_after(self) -> None:
        info = parse_rate_limit_headers({"Retry-After": "42"})
        assert info.retry_after == 42.0

    def test_lowercase_headers(self) -> None:
        info = parse_rate_limit_headers({"retry-after": "10"})
        assert info.retry_after == 10.0

    def test_rate_limit_limit(self) -> None:
        info = parse_rate_limit_headers({"X-RateLimit-Limit": "100"})
        assert info.limit == 100

    def test_rate_limit_remaining(self) -> None:
        info = parse_rate_limit_headers({"X-RateLimit-Remaining": "5"})
        assert info.remaining == 5

    def test_rate_limit_reset(self) -> None:
        info = parse_rate_limit_headers({"X-RateLimit-Reset": "1700000000"})
        assert info.reset_at == 1700000000.0

    def test_empty_headers(self) -> None:
        info = parse_rate_limit_headers({})
        assert info.retry_after is None
        assert info.limit is None

    def test_invalid_values_ignored(self) -> None:
        info = parse_rate_limit_headers({"Retry-After": "not-a-number"})
        assert info.retry_after is None


class TestResilienceManager:
    """Resilience manager tests."""

    def setup_method(self) -> None:
        clear_call_log()

    def test_default_providers(self) -> None:
        mgr = AgentResilienceManager()
        assert "claude" in mgr.breakers
        assert "openai" in mgr.breakers
        assert "gemini" in mgr.breakers

    def test_custom_providers(self) -> None:
        mgr = AgentResilienceManager(providers=["a", "b"])
        assert "a" in mgr.breakers
        assert "b" in mgr.breakers

    def test_can_call_healthy(self) -> None:
        mgr = AgentResilienceManager()
        assert mgr.can_call("claude")

    def test_can_call_unknown_provider(self) -> None:
        mgr = AgentResilienceManager()
        assert mgr.can_call("unknown_provider")

    def test_record_success(self) -> None:
        mgr = AgentResilienceManager()
        mgr.record_success("claude", latency_ms=150.0)
        health = mgr.provider_health("claude")
        assert health.total_calls == 1
        assert health.avg_latency_ms == 150.0

    def test_record_failure(self) -> None:
        mgr = AgentResilienceManager()
        mgr.record_failure("openai", error="timeout")
        health = mgr.provider_health("openai")
        assert health.total_errors == 1

    def test_circuit_opens_on_failures(self) -> None:
        mgr = AgentResilienceManager(
            breaker_config=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=999),
        )
        mgr.record_failure("claude")
        mgr.record_failure("claude")
        assert not mgr.can_call("claude")

    def test_get_healthy_provider_preferred(self) -> None:
        mgr = AgentResilienceManager()
        assert mgr.get_healthy_provider("claude") == "claude"

    def test_get_healthy_provider_fallback(self) -> None:
        mgr = AgentResilienceManager(
            breaker_config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=999),
        )
        mgr.record_failure("claude")
        result = mgr.get_healthy_provider("claude")
        assert result is not None
        assert result != "claude"

    def test_get_healthy_provider_none(self) -> None:
        mgr = AgentResilienceManager(
            providers=["a"],
            breaker_config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=999),
        )
        mgr.record_failure("a")
        assert mgr.get_healthy_provider("a") is None

    def test_fallback_chain(self) -> None:
        mgr = AgentResilienceManager()
        chain = mgr.get_fallback_chain("claude")
        assert chain[0] == "claude"
        assert len(chain) == 3

    def test_fallback_chain_skips_unavailable(self) -> None:
        mgr = AgentResilienceManager(
            breaker_config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=999),
        )
        mgr.record_failure("claude")
        chain = mgr.get_fallback_chain("claude")
        assert "claude" not in chain

    def test_provider_health_status(self) -> None:
        mgr = AgentResilienceManager()
        health = mgr.provider_health("claude")
        assert health.status == ProviderStatus.HEALTHY

    def test_provider_health_degraded(self) -> None:
        mgr = AgentResilienceManager()
        # 50% error rate → degraded
        mgr.record_success("claude")
        mgr.record_failure("claude")
        mgr.record_failure("claude")
        health = mgr.provider_health("claude")
        assert health.status == ProviderStatus.DEGRADED

    def test_provider_health_unavailable(self) -> None:
        mgr = AgentResilienceManager(
            breaker_config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=999),
        )
        mgr.record_failure("claude")
        health = mgr.provider_health("claude")
        assert health.status == ProviderStatus.UNAVAILABLE

    def test_all_health(self) -> None:
        mgr = AgentResilienceManager()
        health_list = mgr.all_health()
        assert len(health_list) == 3

    def test_reset_provider(self) -> None:
        mgr = AgentResilienceManager(
            breaker_config=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=999),
        )
        mgr.record_failure("claude")
        assert not mgr.can_call("claude")
        mgr.reset_provider("claude")
        assert mgr.can_call("claude")


class TestCallLog:
    """Call log and stats tests."""

    def setup_method(self) -> None:
        clear_call_log()

    def test_log_recorded(self) -> None:
        mgr = AgentResilienceManager()
        mgr.record_success("claude", latency_ms=100)
        mgr.record_failure("openai", error="timeout")
        log = get_call_log()
        assert len(log) == 2

    def test_clear_log(self) -> None:
        mgr = AgentResilienceManager()
        mgr.record_success("claude")
        clear_call_log()
        assert len(get_call_log()) == 0

    def test_empty_stats(self) -> None:
        stats = get_resilience_stats()
        assert stats["total_calls"] == 0

    def test_stats_computed(self) -> None:
        mgr = AgentResilienceManager()
        mgr.record_success("claude")
        mgr.record_success("claude")
        mgr.record_failure("openai")
        stats = get_resilience_stats()
        assert stats["total_calls"] == 3
        assert stats["success_count"] == 2
        assert stats["failure_count"] == 1
        assert stats["by_provider"]["claude"]["success"] == 2

    def test_success_rate(self) -> None:
        mgr = AgentResilienceManager()
        mgr.record_success("claude")
        mgr.record_failure("claude")
        stats = get_resilience_stats()
        assert stats["success_rate"] == 0.5
