"""FastAPI application factory for the AI Coding Pipeline backend."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.config import settings
from app.database import close_db, init_db
from app.middleware.logging import RequestLoggingMiddleware, configure_logging
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.redis import close_redis, init_redis
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup/shutdown lifecycle hook.

    Connection errors for the database and Redis are caught and logged as
    warnings so the application can still start during local development
    (e.g. without Docker services running).
    """
    configure_logging()
    logger.info("Starting %s", settings.APP_NAME)

    # -- Database --
    try:
        await init_db()
    except Exception as exc:
        logger.warning(
            "Database initialisation failed — running without DB: %s",
            exc,
        )

    # -- Redis --
    try:
        await init_redis()
    except Exception as exc:
        logger.warning(
            "Redis initialisation failed — running without Redis: %s",
            exc,
        )

    yield  # Application is running

    # -- Shutdown --
    try:
        await close_redis()
    except Exception as exc:
        logger.warning("Error closing Redis: %s", exc)

    try:
        await close_db()
    except Exception as exc:
        logger.warning("Error closing database: %s", exc)

    logger.info("%s shutdown complete", settings.APP_NAME)


# ── App factory ─────────────────────────────────────────────────────
def create_app() -> FastAPI:
    """Build and return the configured :class:`FastAPI` application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # -- CORS --
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Custom middleware (outermost added last) --
    app.add_middleware(RateLimiterMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    # -- Routers --
    app.include_router(v1_router)

    # -- Health check --
    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "service": settings.APP_NAME}

    # -- WebSocket (supports both /ws?token=... and /ws/{user_id}) --
    @app.websocket("/ws")
    async def websocket_token(ws: WebSocket, token: str | None = None) -> None:
        """Token-based WebSocket auth used by the frontend."""
        if not token:
            await ws.close(code=4001, reason="Missing token")
            return
        try:
            from app.services.auth_service import decode_token

            payload = decode_token(token)
            user_id = payload["sub"]
        except Exception:
            await ws.close(code=4001, reason="Invalid token")
            return
        await _handle_ws(ws, user_id)

    @app.websocket("/ws/{user_id}")
    async def websocket_endpoint(ws: WebSocket, user_id: str) -> None:
        """Legacy path-based WebSocket endpoint."""
        await _handle_ws(ws, user_id)

    async def _handle_ws(ws: WebSocket, user_id: str) -> None:
        await ws_manager.connect(ws, user_id)
        try:
            while True:
                data = await ws.receive_json()
                msg_type = data.get("type", "")
                if msg_type == "ping":
                    await ws.send_json({"type": "pong"})
                elif msg_type == "subscribe_project":
                    project_id = data.get("project_id")
                    if project_id:
                        await ws_manager.subscribe_project(user_id, project_id)
                elif msg_type == "unsubscribe_project":
                    project_id = data.get("project_id")
                    if project_id:
                        await ws_manager.unsubscribe_project(user_id, project_id)
        except WebSocketDisconnect:
            await ws_manager.disconnect(ws, user_id)

    return app


app = create_app()
