"""Tests for logging middleware — CorrelationIDFilter, configure_logging."""

from __future__ import annotations

import logging
import uuid

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.middleware.logging import (
    CorrelationIDFilter,
    RequestLoggingMiddleware,
    configure_logging,
    correlation_id_ctx,
)

# ---------------------------------------------------------------------------
# CorrelationIDFilter
# ---------------------------------------------------------------------------


class TestCorrelationIDFilter:
    def test_correlation_id_filter_default(self):
        """When no correlation_id is set in the ContextVar the filter injects the default '-'."""
        # Reset to default
        token = correlation_id_ctx.set("-")
        try:
            filt = CorrelationIDFilter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="hello",
                args=None,
                exc_info=None,
            )
            result = filt.filter(record)
            assert result is True
            assert record.correlation_id == "-"  # type: ignore[attr-defined]
        finally:
            correlation_id_ctx.reset(token)

    def test_correlation_id_filter_with_value(self):
        """When a correlation_id is set the filter injects it into the record."""
        token = correlation_id_ctx.set("abc-123")
        try:
            filt = CorrelationIDFilter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="hello",
                args=None,
                exc_info=None,
            )
            result = filt.filter(record)
            assert result is True
            assert record.correlation_id == "abc-123"  # type: ignore[attr-defined]
        finally:
            correlation_id_ctx.reset(token)


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


class TestConfigureLogging:
    def test_configure_logging_sets_root_handler(self):
        """configure_logging should set exactly one handler on the root logger."""
        configure_logging()
        root = logging.getLogger()
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        # The handler should have the CorrelationIDFilter attached
        filter_types = [type(f) for f in handler.filters]
        assert CorrelationIDFilter in filter_types


# ---------------------------------------------------------------------------
# RequestLoggingMiddleware
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with the logging middleware."""
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ping")
    async def ping():
        return JSONResponse({"ok": True})

    return app


@pytest.mark.asyncio
class TestRequestLoggingMiddleware:
    async def test_middleware_generates_correlation_id(self):
        """When no X-Correlation-ID header is sent the middleware generates one."""
        app = _make_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/ping")

        assert resp.status_code == 200
        cid = resp.headers.get("X-Correlation-ID")
        assert cid is not None
        # Should be a valid UUID4
        uuid.UUID(cid, version=4)

    async def test_middleware_uses_provided_correlation_id(self):
        """When the request includes X-Correlation-ID the middleware echoes it back."""
        app = _make_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/ping", headers={"X-Correlation-ID": "my-custom-id"})

        assert resp.status_code == 200
        assert resp.headers["X-Correlation-ID"] == "my-custom-id"

    async def test_middleware_adds_response_headers(self):
        """The middleware should add both X-Correlation-ID and X-Response-Time-Ms headers."""
        app = _make_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/ping")

        assert "X-Correlation-ID" in resp.headers
        assert "X-Response-Time-Ms" in resp.headers
        # Response time should be a float-parseable string
        float(resp.headers["X-Response-Time-Ms"])
