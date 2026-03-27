"""Redis-backed sliding-window rate limiter middleware."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.redis import get_redis_pool

logger = logging.getLogger(__name__)

# ── Default rate-limit profiles ─────────────────────────────────────
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    # (max_requests, window_seconds)
    "default": (100, 60),
    "ai": (10, 60),
}

# Path prefixes considered AI-intensive endpoints
_AI_PREFIXES = (
    "/api/v1/ai/",
    "/api/v1/pipeline/",
    "/api/v1/agents/",
)


def _get_profile(path: str) -> tuple[str, int, int]:
    """Return ``(profile_name, max_requests, window_seconds)`` for *path*."""
    for prefix in _AI_PREFIXES:
        if path.startswith(prefix):
            limit, window = _RATE_LIMITS["ai"]
            return "ai", limit, window
    limit, window = _RATE_LIMITS["default"]
    return "default", limit, window


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter using Redis sorted sets.

    Each client is identified by IP address.  AI-specific endpoints get a
    stricter limit (10 req/min) while all other routes default to 100 req/min.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip health checks
        if request.url.path in ("/health", "/api/v1/ping"):
            return await call_next(request)

        try:
            redis = get_redis_pool()
        except RuntimeError:
            # Redis not available — fail open so the app still works
            logger.warning("Rate limiter skipped: Redis pool not available")
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        profile, max_requests, window = _get_profile(request.url.path)
        key = f"rate_limit:{profile}:{client_ip}"
        now = time.time()
        window_start = now - window

        pipe = redis.pipeline(transaction=True)
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)
        # Add current request timestamp
        pipe.zadd(key, {str(now): now})
        # Count requests in window
        pipe.zcard(key)
        # Set TTL so keys auto-expire
        pipe.expire(key, window + 1)
        results = await pipe.execute()

        request_count: int = results[2]

        if request_count > max_requests:
            retry_after = int(window - (now - window_start))
            logger.warning(
                "Rate limit exceeded: client=%s profile=%s count=%d limit=%d",
                client_ip,
                profile,
                request_count,
                max_requests,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again later.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + retry_after)),
                },
            )

        response = await call_next(request)
        remaining = max(0, max_requests - request_count)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(now + window))
        return response
