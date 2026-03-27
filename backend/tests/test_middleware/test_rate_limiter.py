"""Tests for app.middleware.rate_limiter — _get_profile and RateLimiterMiddleware."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.middleware.rate_limiter import RateLimiterMiddleware, _get_profile

# ---------------------------------------------------------------------------
# _get_profile
# ---------------------------------------------------------------------------


class TestGetProfile:
    def test_get_profile_default(self):
        """A normal path should return the default profile (100 req/60s)."""
        name, max_req, window = _get_profile("/api/v1/projects/")
        assert name == "default"
        assert max_req == 100
        assert window == 60

    def test_get_profile_ai_endpoint(self):
        """AI-prefixed paths should return the ai profile (10 req/60s)."""
        for path in ("/api/v1/ai/generate", "/api/v1/pipeline/run", "/api/v1/agents/list"):
            name, max_req, window = _get_profile(path)
            assert name == "ai", f"Expected ai profile for {path}"
            assert max_req == 10
            assert window == 60


# ---------------------------------------------------------------------------
# Middleware integration tests
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with the rate-limiter middleware."""
    app = FastAPI()
    app.add_middleware(RateLimiterMiddleware)

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})

    @app.get("/api/v1/ping")
    async def ping():
        return JSONResponse({"pong": True})

    @app.get("/api/v1/stuff")
    async def stuff():
        return JSONResponse({"data": 1})

    return app


@pytest.mark.asyncio
class TestRateLimiterMiddleware:
    async def test_health_check_bypass(self):
        """Requests to /health and /api/v1/ping should bypass rate limiting entirely."""
        app = _make_app()
        transport = ASGITransport(app=app)

        # Even if Redis is unavailable the health endpoints should work,
        # but more importantly they should NOT trigger any Redis calls.
        with patch(
            "app.middleware.rate_limiter.get_redis_pool", side_effect=RuntimeError("no redis")
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp_health = await client.get("/health")
                resp_ping = await client.get("/api/v1/ping")

        assert resp_health.status_code == 200
        assert resp_ping.status_code == 200
        # These bypassed endpoints should NOT have rate-limit headers
        assert "X-RateLimit-Limit" not in resp_health.headers
        assert "X-RateLimit-Limit" not in resp_ping.headers

    async def test_redis_unavailable_fail_open(self):
        """When Redis is unavailable the middleware should fail open and let requests through."""
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch(
            "app.middleware.rate_limiter.get_redis_pool",
            side_effect=RuntimeError("pool not initialised"),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/stuff")

        assert resp.status_code == 200
        # No rate-limit headers when Redis is down
        assert "X-RateLimit-Limit" not in resp.headers
