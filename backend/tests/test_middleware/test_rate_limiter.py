"""Tests for app.middleware.rate_limiter — _get_profile and RateLimiterMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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

    def test_get_profile_root_path(self):
        """Root path should use default profile."""
        name, max_req, window = _get_profile("/")
        assert name == "default"
        assert max_req == 100

    def test_get_profile_partial_ai_prefix_no_match(self):
        """Paths that only partially match AI prefixes should get default."""
        name, _, _ = _get_profile("/api/v1/aistuff")
        assert name == "default"

    def test_get_profile_agents_subpath(self):
        """Deeper sub-paths under AI prefixes should still match."""
        name, max_req, window = _get_profile("/api/v1/agents/abc/execute")
        assert name == "ai"
        assert max_req == 10
        assert window == 60


# ---------------------------------------------------------------------------
# Helpers
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

    @app.get("/api/v1/ai/generate")
    async def ai_generate():
        return JSONResponse({"result": "generated"})

    return app


def _mock_redis_pipeline(request_count: int = 1):
    """Return a mock Redis object whose pipeline returns *request_count*."""
    mock_pipe = MagicMock()
    mock_pipe.zremrangebyscore = MagicMock()
    mock_pipe.zadd = MagicMock()
    mock_pipe.zcard = MagicMock()
    mock_pipe.expire = MagicMock()
    # pipeline().execute() returns [zrem_result, zadd, zcard, expire]
    mock_pipe.execute = AsyncMock(return_value=[0, True, request_count, True])

    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    return mock_redis


# ---------------------------------------------------------------------------
# Middleware integration tests
# ---------------------------------------------------------------------------


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

    async def test_normal_request_returns_rate_limit_headers(self):
        """A normal request within limits should include X-RateLimit-* headers."""
        mock_redis = _mock_redis_pipeline(request_count=5)
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/stuff")

        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "100"
        assert resp.headers["X-RateLimit-Remaining"] == "95"  # 100 - 5
        assert "X-RateLimit-Reset" in resp.headers

    async def test_rate_limit_exceeded_returns_429(self):
        """When request count exceeds max, should return 429 with Retry-After."""
        mock_redis = _mock_redis_pipeline(request_count=101)
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/stuff")

        assert resp.status_code == 429
        body = resp.json()
        assert body["detail"] == "Rate limit exceeded. Try again later."
        assert "retry_after" in body
        assert resp.headers["Retry-After"]
        assert resp.headers["X-RateLimit-Limit"] == "100"
        assert resp.headers["X-RateLimit-Remaining"] == "0"
        assert "X-RateLimit-Reset" in resp.headers

    async def test_ai_endpoint_uses_stricter_limit(self):
        """AI endpoints should use the ai profile with limit=10."""
        mock_redis = _mock_redis_pipeline(request_count=3)
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/ai/generate")

        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "10"
        assert resp.headers["X-RateLimit-Remaining"] == "7"  # 10 - 3

    async def test_ai_endpoint_exceeded_returns_429(self):
        """AI endpoints should return 429 when exceeding 10 requests."""
        mock_redis = _mock_redis_pipeline(request_count=11)
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/ai/generate")

        assert resp.status_code == 429
        assert resp.headers["X-RateLimit-Limit"] == "10"
        assert resp.headers["X-RateLimit-Remaining"] == "0"

    async def test_remaining_does_not_go_negative(self):
        """X-RateLimit-Remaining should be 0, never negative, at the limit boundary."""
        mock_redis = _mock_redis_pipeline(request_count=100)
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/stuff")

        # 100 == max, so not exceeded, remaining = max(0, 100-100) = 0
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Remaining"] == "0"

    async def test_redis_pipeline_called_correctly(self):
        """Verify the Redis pipeline commands are invoked in the correct order."""
        mock_redis = _mock_redis_pipeline(request_count=1)
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/v1/stuff")

        pipe = mock_redis.pipeline.return_value
        pipe.zremrangebyscore.assert_called_once()
        pipe.zadd.assert_called_once()
        pipe.zcard.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_awaited_once()

    async def test_redis_key_includes_profile_and_ip(self):
        """The Redis key should include the profile name and client IP."""
        mock_redis = _mock_redis_pipeline(request_count=1)
        pipe = mock_redis.pipeline.return_value
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/v1/stuff")

        # zremrangebyscore is called with the key as first arg
        call_args = pipe.zremrangebyscore.call_args
        key = call_args[0][0]
        assert key.startswith("rate_limit:default:")

    async def test_ai_endpoint_redis_key_has_ai_profile(self):
        """AI endpoint requests should use 'rate_limit:ai:' key prefix."""
        mock_redis = _mock_redis_pipeline(request_count=1)
        pipe = mock_redis.pipeline.return_value
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/v1/ai/generate")

        call_args = pipe.zremrangebyscore.call_args
        key = call_args[0][0]
        assert key.startswith("rate_limit:ai:")

    async def test_expire_set_to_window_plus_one(self):
        """The TTL on the key should be window + 1 seconds."""
        mock_redis = _mock_redis_pipeline(request_count=1)
        pipe = mock_redis.pipeline.return_value
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/v1/stuff")

        # expire called with (key, window + 1) — default window is 60
        expire_args = pipe.expire.call_args[0]
        assert expire_args[1] == 61  # 60 + 1

    async def test_client_ip_unknown_when_no_client(self):
        """When request.client is None, IP should default to 'unknown'."""
        mock_redis = _mock_redis_pipeline(request_count=1)
        pipe = mock_redis.pipeline.return_value
        app = _make_app()
        transport = ASGITransport(app=app)

        with (
            patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis),
            patch(
                "app.middleware.rate_limiter.Request.client",
                new_callable=lambda: property(lambda self: None),
            ),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/v1/stuff")

        call_args = pipe.zremrangebyscore.call_args
        key = call_args[0][0]
        assert "unknown" in key

    async def test_rate_limit_logging_on_exceed(self):
        """Rate limit exceeded should trigger a warning log."""
        mock_redis = _mock_redis_pipeline(request_count=101)
        app = _make_app()
        transport = ASGITransport(app=app)

        with (
            patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis),
            patch("app.middleware.rate_limiter.logger") as mock_logger,
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/v1/stuff")

        mock_logger.warning.assert_called_once()
        log_msg = mock_logger.warning.call_args[0][0]
        assert "Rate limit exceeded" in log_msg

    async def test_redis_unavailable_logs_warning(self):
        """When Redis is unavailable a warning should be logged."""
        app = _make_app()
        transport = ASGITransport(app=app)

        with (
            patch(
                "app.middleware.rate_limiter.get_redis_pool",
                side_effect=RuntimeError("no pool"),
            ),
            patch("app.middleware.rate_limiter.logger") as mock_logger,
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/v1/stuff")

        mock_logger.warning.assert_called_once()
        assert "Redis pool not available" in mock_logger.warning.call_args[0][0]

    async def test_single_request_remaining_is_max_minus_one(self):
        """First request in window should show remaining = max - 1."""
        mock_redis = _mock_redis_pipeline(request_count=1)
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/stuff")

        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Remaining"] == "99"

    async def test_429_body_contains_retry_after_field(self):
        """The 429 JSON body should include a numeric retry_after value."""
        mock_redis = _mock_redis_pipeline(request_count=101)
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/v1/stuff")

        body = resp.json()
        assert isinstance(body["retry_after"], int)

    async def test_pipeline_transaction_mode(self):
        """Pipeline should be created with transaction=True."""
        mock_redis = _mock_redis_pipeline(request_count=1)
        app = _make_app()
        transport = ASGITransport(app=app)

        with patch("app.middleware.rate_limiter.get_redis_pool", return_value=mock_redis):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/v1/stuff")

        mock_redis.pipeline.assert_called_once_with(transaction=True)
