"""Tests for retry_strategy — exponential backoff, circuit breaker, and model fallback."""

from __future__ import annotations

import time

import pytest

from app.workflows.retry_strategy import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    ErrorCategory,
    RetryAttempt,
    RetryConfig,
    RetryStrategy,
)

# ---------------------------------------------------------------------------
# Exponential backoff calculation
# ---------------------------------------------------------------------------


def test_exponential_backoff_increases_with_attempt():
    """Delay grows exponentially with the attempt number."""
    strategy = RetryStrategy(config=RetryConfig(base_delay=1.0, jitter_factor=0.0))

    d0 = strategy.calculate_delay(0, ErrorCategory.SERVER_ERROR)
    d1 = strategy.calculate_delay(1, ErrorCategory.SERVER_ERROR)
    d2 = strategy.calculate_delay(2, ErrorCategory.SERVER_ERROR)

    assert d0 == pytest.approx(1.0)
    assert d1 == pytest.approx(2.0)
    assert d2 == pytest.approx(4.0)


def test_backoff_base_delay_scaling():
    """A different base_delay scales all delays proportionally."""
    strategy = RetryStrategy(config=RetryConfig(base_delay=2.0, jitter_factor=0.0))

    assert strategy.calculate_delay(0, ErrorCategory.SERVER_ERROR) == pytest.approx(2.0)
    assert strategy.calculate_delay(1, ErrorCategory.SERVER_ERROR) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Jitter randomness
# ---------------------------------------------------------------------------


def test_jitter_adds_randomness():
    """With non-zero jitter_factor the delay varies across invocations."""
    strategy = RetryStrategy(config=RetryConfig(base_delay=1.0, jitter_factor=0.5))

    delays = {strategy.calculate_delay(2, ErrorCategory.SERVER_ERROR) for _ in range(50)}
    # With randomness we expect more than a single unique value.
    assert len(delays) > 1


def test_jitter_is_non_negative():
    """Jitter never makes the delay shorter than the raw exponential value."""
    strategy = RetryStrategy(config=RetryConfig(base_delay=1.0, jitter_factor=0.5))

    for _ in range(100):
        delay = strategy.calculate_delay(1, ErrorCategory.SERVER_ERROR)
        # base_delay * 2^1 == 2.0; jitter is additive and >= 0
        assert delay >= 2.0


# ---------------------------------------------------------------------------
# Max delay cap
# ---------------------------------------------------------------------------


def test_max_delay_caps_result():
    """Delay never exceeds max_delay regardless of attempt number."""
    strategy = RetryStrategy(
        config=RetryConfig(base_delay=1.0, max_delay=10.0, jitter_factor=0.0)
    )

    assert strategy.calculate_delay(20, ErrorCategory.SERVER_ERROR) == pytest.approx(10.0)


def test_max_delay_with_jitter():
    """Even with jitter the delay is capped at max_delay."""
    strategy = RetryStrategy(
        config=RetryConfig(base_delay=1.0, max_delay=10.0, jitter_factor=1.0)
    )

    for _ in range(100):
        assert strategy.calculate_delay(20, ErrorCategory.SERVER_ERROR) <= 10.0


# ---------------------------------------------------------------------------
# Rate-limit special handling
# ---------------------------------------------------------------------------


def test_rate_limit_double_delay():
    """Rate-limit errors receive a 2x multiplier on the base delay."""
    strategy = RetryStrategy(config=RetryConfig(base_delay=1.0, jitter_factor=0.0))

    normal = strategy.calculate_delay(0, ErrorCategory.SERVER_ERROR)
    rate_limited = strategy.calculate_delay(0, ErrorCategory.RATE_LIMIT)

    assert rate_limited == pytest.approx(normal * 2)


# ---------------------------------------------------------------------------
# Non-retryable errors
# ---------------------------------------------------------------------------


def test_auth_error_not_retried():
    """AUTH_ERROR should never be retried."""
    strategy = RetryStrategy()
    assert strategy.should_retry(0, ErrorCategory.AUTH_ERROR) is False


def test_invalid_request_not_retried():
    """INVALID_REQUEST should never be retried."""
    strategy = RetryStrategy()
    assert strategy.should_retry(0, ErrorCategory.INVALID_REQUEST) is False


# ---------------------------------------------------------------------------
# should_retry decision logic
# ---------------------------------------------------------------------------


def test_should_retry_within_limit():
    """Retries are allowed when below max_retries for retryable errors."""
    strategy = RetryStrategy(config=RetryConfig(max_retries=5))
    assert strategy.should_retry(0, ErrorCategory.SERVER_ERROR) is True
    assert strategy.should_retry(4, ErrorCategory.SERVER_ERROR) is True


def test_should_retry_at_limit():
    """No retry when attempt equals max_retries."""
    strategy = RetryStrategy(config=RetryConfig(max_retries=3))
    assert strategy.should_retry(3, ErrorCategory.SERVER_ERROR) is False


def test_should_retry_respects_retry_on_set():
    """Only errors in retry_on are retried."""
    strategy = RetryStrategy(
        config=RetryConfig(retry_on={ErrorCategory.TIMEOUT})
    )
    assert strategy.should_retry(0, ErrorCategory.TIMEOUT) is True
    assert strategy.should_retry(0, ErrorCategory.SERVER_ERROR) is False


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def test_classify_timeout_error():
    """TimeoutError is classified as TIMEOUT."""
    assert RetryStrategy.classify_error(TimeoutError("timed out")) == ErrorCategory.TIMEOUT


def test_classify_connection_error():
    """ConnectionError is classified as SERVER_ERROR."""
    assert RetryStrategy.classify_error(ConnectionError("refused")) == ErrorCategory.SERVER_ERROR


def test_classify_rate_limit_by_message():
    """An exception whose message mentions '429' is classified as RATE_LIMIT."""
    err = Exception("HTTP 429 Too Many Requests")
    assert RetryStrategy.classify_error(err) == ErrorCategory.RATE_LIMIT


def test_classify_auth_error_by_message():
    """An exception mentioning '401' is classified as AUTH_ERROR."""
    err = Exception("HTTP 401 Unauthorized")
    assert RetryStrategy.classify_error(err) == ErrorCategory.AUTH_ERROR


def test_classify_unknown_error():
    """An unrecognised exception falls through to UNKNOWN."""
    assert RetryStrategy.classify_error(Exception("something weird")) == ErrorCategory.UNKNOWN


# ---------------------------------------------------------------------------
# Circuit breaker state transitions
# ---------------------------------------------------------------------------


def test_circuit_breaker_starts_closed():
    """A fresh circuit breaker is in CLOSED state."""
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_opens_after_threshold():
    """Enough consecutive failures trip the breaker to OPEN."""
    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_blocks_when_open():
    """An OPEN breaker rejects execution."""
    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
    cb.record_failure()
    assert cb.can_execute() is False


def test_circuit_breaker_half_open_after_recovery():
    """After recovery_timeout elapses the breaker transitions to HALF_OPEN."""
    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout=9999.0))
    cb.record_failure()
    # With a very large timeout the breaker stays OPEN.
    assert cb.state == CircuitState.OPEN

    # Now use a zero-timeout breaker to verify the promotion path.
    cb2 = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.0))
    cb2.record_failure()
    # recovery_timeout=0 means the very next state access promotes to HALF_OPEN.
    assert cb2.state == CircuitState.HALF_OPEN
    assert cb2.can_execute() is True


def test_circuit_breaker_closes_after_half_open_successes():
    """Enough successes in HALF_OPEN move the breaker back to CLOSED."""
    cb = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.0, half_open_max_calls=2)
    )
    cb.record_failure()
    # Force HALF_OPEN via state access (recovery_timeout=0).
    assert cb.state == CircuitState.HALF_OPEN

    cb.record_success()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_reopens_on_half_open_failure():
    """A failure during HALF_OPEN immediately re-opens the breaker."""
    # Use recovery_timeout=0 to get into HALF_OPEN, then swap to a large
    # timeout so that re-opening actually sticks when we check state.
    cb = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.0, half_open_max_calls=3)
    )
    cb.record_failure()
    assert cb.state == CircuitState.HALF_OPEN  # promoted because timeout=0

    # Set a large recovery timeout so the next OPEN state persists.
    cb._config = CircuitBreakerConfig(
        failure_threshold=1, recovery_timeout=9999.0,
        half_open_max_calls=3,
    )
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False


# ---------------------------------------------------------------------------
# Circuit breaker recovery / reset
# ---------------------------------------------------------------------------


def test_circuit_breaker_reset():
    """reset() returns the breaker to pristine CLOSED state."""
    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1))
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True


# ---------------------------------------------------------------------------
# Stats tracking
# ---------------------------------------------------------------------------


def test_get_stats_empty():
    """Stats on a fresh strategy are all zeroes."""
    strategy = RetryStrategy()
    stats = strategy.get_stats()
    assert stats["total_attempts"] == 0
    assert stats["successes"] == 0
    assert stats["failures"] == 0


def test_get_stats_records_attempts():
    """Stats correctly aggregate recorded attempts."""
    strategy = RetryStrategy()

    now = time.time()
    strategy.record_attempt(RetryAttempt(
        attempt_number=0, delay=1.0,
        error_category=ErrorCategory.SERVER_ERROR,
        timestamp=now, success=False,
    ))
    strategy.record_attempt(RetryAttempt(
        attempt_number=1, delay=2.0,
        error_category=ErrorCategory.SERVER_ERROR,
        timestamp=now, success=False,
    ))
    strategy.record_attempt(RetryAttempt(
        attempt_number=2, delay=0.0,
        error_category=None,
        timestamp=now, success=True,
    ))

    stats = strategy.get_stats()
    assert stats["total_attempts"] == 3
    assert stats["successes"] == 1
    assert stats["failures"] == 2
    assert stats["total_delay"] == pytest.approx(3.0)
    assert stats["errors_by_category"]["server_error"] == 2


def test_should_retry_blocked_by_open_circuit():
    """should_retry returns False when the circuit breaker is OPEN."""
    strategy = RetryStrategy(
        circuit_config=CircuitBreakerConfig(failure_threshold=1),
    )
    # Trip the breaker via record_attempt.
    strategy.record_attempt(RetryAttempt(
        attempt_number=0, delay=0.0,
        error_category=ErrorCategory.SERVER_ERROR,
        timestamp=time.time(), success=False,
    ))
    assert strategy.circuit_breaker.state == CircuitState.OPEN
    assert strategy.should_retry(0, ErrorCategory.SERVER_ERROR) is False
