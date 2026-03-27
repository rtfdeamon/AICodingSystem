"""Retry strategy — exponential backoff, circuit breaker, and model fallback for LLM API calls."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CircuitState(StrEnum):
    """States for the circuit breaker pattern."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ErrorCategory(StrEnum):
    """Categorised error types for retry decisions."""

    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN = "unknown"


# Categories that must never be retried.
_NON_RETRYABLE: frozenset[ErrorCategory] = frozenset(
    {ErrorCategory.AUTH_ERROR, ErrorCategory.INVALID_REQUEST}
)


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RetryConfig:
    """Tunables for the exponential-backoff retry logic."""

    max_retries: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter_factor: float = 0.5
    retry_on: set[ErrorCategory] = field(
        default_factory=lambda: {
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.SERVER_ERROR,
            ErrorCategory.TIMEOUT,
            ErrorCategory.UNKNOWN,
        }
    )


@dataclass
class CircuitBreakerConfig:
    """Tunables for the circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 3


# ---------------------------------------------------------------------------
# Retry attempt record
# ---------------------------------------------------------------------------


@dataclass
class RetryAttempt:
    """Immutable record of a single retry attempt."""

    attempt_number: int
    delay: float
    error_category: ErrorCategory | None
    timestamp: float
    success: bool


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Implements the circuit breaker pattern.

    * **CLOSED** — requests flow normally; consecutive failures are counted.
    * **OPEN** — requests are blocked until *recovery_timeout* elapses.
    * **HALF_OPEN** — a limited number of probe requests are allowed through.
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._half_open_calls: int = 0
        self._last_failure_time: float = 0.0

    # -- public interface ---------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Return the current state, promoting OPEN -> HALF_OPEN when the
        recovery timeout has elapsed."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._config.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info("Circuit breaker transitioned OPEN -> HALF_OPEN")
        return self._state

    def can_execute(self) -> bool:
        """Return ``True`` if a request is allowed under the current state."""
        current = self.state  # may promote OPEN -> HALF_OPEN
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return self._half_open_calls < self._config.half_open_max_calls
        return False  # OPEN

    def record_success(self) -> None:
        """Record a successful call."""
        self._success_count += 1
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self._config.half_open_max_calls:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0
                logger.info("Circuit breaker transitioned HALF_OPEN -> CLOSED")
        elif self._state == CircuitState.CLOSED:
            # Reset consecutive failure streak on success.
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open re-opens immediately.
            self._state = CircuitState.OPEN
            self._half_open_calls = 0
            logger.warning("Circuit breaker transitioned HALF_OPEN -> OPEN (probe failed)")
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self._config.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker transitioned CLOSED -> OPEN "
                    "(failures=%d, threshold=%d)",
                    self._failure_count,
                    self._config.failure_threshold,
                )

    def reset(self) -> None:
        """Unconditionally reset the breaker to CLOSED with zero counters."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0


# ---------------------------------------------------------------------------
# Retry strategy
# ---------------------------------------------------------------------------


class RetryStrategy:
    """Coordinates retry logic, delay calculation, and circuit breaking.

    Parameters
    ----------
    config:
        Retry timing / policy configuration.
    circuit_config:
        Circuit breaker thresholds.
    """

    def __init__(
        self,
        config: RetryConfig | None = None,
        circuit_config: CircuitBreakerConfig | None = None,
    ) -> None:
        self._config = config or RetryConfig()
        self._circuit_breaker = CircuitBreaker(circuit_config or CircuitBreakerConfig())
        self._attempts: list[RetryAttempt] = []

    # -- public interface ---------------------------------------------------

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Return the underlying :class:`CircuitBreaker` instance."""
        return self._circuit_breaker

    def calculate_delay(self, attempt: int, error_category: ErrorCategory) -> float:
        """Compute the delay before the next retry.

        Formula: ``min(base_delay * 2^attempt + jitter, max_delay)``

        Rate-limit errors receive a 2x multiplier on the base delay.
        """
        base = self._config.base_delay
        if error_category == ErrorCategory.RATE_LIMIT:
            base *= 2.0

        exponential = base * (2 ** attempt)
        max_jitter = self._config.jitter_factor * base
        jitter = random.uniform(0, max_jitter)  # noqa: S311
        return min(exponential + jitter, self._config.max_delay)

    def should_retry(self, attempt: int, error_category: ErrorCategory) -> bool:
        """Decide whether a retry should be attempted.

        Returns ``False`` when:
        * The error category is non-retryable (AUTH_ERROR, INVALID_REQUEST).
        * The maximum number of retries has been reached.
        * The circuit breaker is blocking requests.
        * The error category is not in the configured *retry_on* set.
        """
        if error_category in _NON_RETRYABLE:
            return False
        if attempt >= self._config.max_retries:
            return False
        if not self._circuit_breaker.can_execute():
            return False
        return error_category in self._config.retry_on

    @staticmethod
    def classify_error(error: Exception) -> ErrorCategory:
        """Map an exception to an :class:`ErrorCategory`.

        Uses a simple heuristic based on exception type name and message
        content so that no external dependencies are required.
        """
        type_name = type(error).__name__.lower()
        message = str(error).lower()

        # Rate-limit indicators
        if "ratelimit" in type_name or "rate" in message and "limit" in message:
            return ErrorCategory.RATE_LIMIT
        if "429" in message:
            return ErrorCategory.RATE_LIMIT

        # Timeout indicators
        if "timeout" in type_name or "timeout" in message:
            return ErrorCategory.TIMEOUT
        if isinstance(error, (TimeoutError,)):
            return ErrorCategory.TIMEOUT

        # Auth indicators
        if "auth" in type_name or "unauthorized" in message or "403" in message or "401" in message:
            return ErrorCategory.AUTH_ERROR

        # Invalid request indicators
        if "invalid" in type_name or "validation" in type_name:
            return ErrorCategory.INVALID_REQUEST
        if "400" in message and "bad request" in message:
            return ErrorCategory.INVALID_REQUEST

        # Server error indicators
        if "server" in type_name or "500" in message or "502" in message or "503" in message:
            return ErrorCategory.SERVER_ERROR
        if isinstance(error, (ConnectionError, OSError)):
            return ErrorCategory.SERVER_ERROR

        return ErrorCategory.UNKNOWN

    def record_attempt(self, attempt: RetryAttempt) -> None:
        """Append a :class:`RetryAttempt` and update the circuit breaker."""
        self._attempts.append(attempt)
        if attempt.success:
            self._circuit_breaker.record_success()
        else:
            self._circuit_breaker.record_failure()

    def get_stats(self) -> dict:
        """Return aggregate statistics about recorded attempts."""
        total = len(self._attempts)
        successes = sum(1 for a in self._attempts if a.success)
        failures = total - successes
        total_delay = sum(a.delay for a in self._attempts)

        by_category: dict[str, int] = {}
        for a in self._attempts:
            if a.error_category is not None:
                key = a.error_category.value
                by_category[key] = by_category.get(key, 0) + 1

        return {
            "total_attempts": total,
            "successes": successes,
            "failures": failures,
            "total_delay": round(total_delay, 4),
            "circuit_state": self._circuit_breaker.state.value,
            "errors_by_category": by_category,
        }
