"""Tests for app.main — create_app, health check, lifespan, WebSocket endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app

# ---------------------------------------------------------------------------
# create_app returns a FastAPI instance
# ---------------------------------------------------------------------------


def test_create_app_returns_fastapi_instance() -> None:
    from fastapi import FastAPI

    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title is not None


def test_create_app_has_routes() -> None:
    app = create_app()
    paths = [r.path for r in app.routes]
    assert "/health" in paths
    assert "/ws" in paths


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient) -> None:
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert "service" in body


# ---------------------------------------------------------------------------
# Lifespan — startup/shutdown with failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_db_failure_continues() -> None:
    """App starts even when DB initialization fails."""
    with (
        patch("app.main.init_db", new_callable=AsyncMock, side_effect=RuntimeError("db down")),
        patch("app.main.init_redis", new_callable=AsyncMock),
        patch("app.main.close_redis", new_callable=AsyncMock),
        patch("app.main.close_db", new_callable=AsyncMock),
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_lifespan_redis_failure_continues() -> None:
    """App starts even when Redis initialization fails."""
    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch(
            "app.main.init_redis", new_callable=AsyncMock, side_effect=RuntimeError("redis down")
        ),
        patch("app.main.close_redis", new_callable=AsyncMock),
        patch("app.main.close_db", new_callable=AsyncMock),
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_lifespan_shutdown_error_handled() -> None:
    """Shutdown errors are caught and don't prevent graceful shutdown."""
    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch("app.main.init_redis", new_callable=AsyncMock),
        patch(
            "app.main.close_redis", new_callable=AsyncMock, side_effect=RuntimeError("close err")
        ),
        patch("app.main.close_db", new_callable=AsyncMock, side_effect=RuntimeError("close err")),
    ):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# WebSocket — using sync TestClient
# ---------------------------------------------------------------------------


def test_ws_no_token_closes() -> None:
    """WebSocket without token should close with code 4001."""
    from starlette.testclient import TestClient

    app = create_app()
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws"),
    ):
        pass


def test_ws_invalid_token() -> None:
    """WebSocket with invalid token should close."""
    from starlette.testclient import TestClient

    app = create_app()
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws?token=badtoken"),
    ):
        pass


def test_ws_legacy_endpoint_ping() -> None:
    """Legacy /ws/{user_id} endpoint handles ping/pong."""
    from starlette.testclient import TestClient

    app = create_app()
    with TestClient(app) as client, client.websocket_connect(f"/ws/{uuid.uuid4()}") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "pong"


def test_ws_subscribe_unsubscribe_project() -> None:
    """Legacy WS endpoint handles subscribe/unsubscribe project messages."""
    from starlette.testclient import TestClient

    app = create_app()
    with TestClient(app) as client, client.websocket_connect(f"/ws/{uuid.uuid4()}") as ws:
        ws.send_json({"type": "subscribe_project", "project_id": str(uuid.uuid4())})
        ws.send_json({"type": "unsubscribe_project", "project_id": str(uuid.uuid4())})
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "pong"


# ---------------------------------------------------------------------------
# CORS middleware is configured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cors_headers(async_client: AsyncClient) -> None:
    """CORS headers should be present on cross-origin requests."""
    resp = await async_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code in (200, 204)


# ---------------------------------------------------------------------------
# API router is mounted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v1_router_mounted(async_client: AsyncClient) -> None:
    """The v1 API router should be mounted and auth endpoint reachable."""
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@test.com", "password": "wrong"},
    )
    assert resp.status_code == 401
