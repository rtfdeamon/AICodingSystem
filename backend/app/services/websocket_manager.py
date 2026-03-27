"""WebSocket connection manager with Redis pub/sub for multi-worker broadcast."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Track WebSocket connections per user and per project.

    In multi-worker deployments, use :meth:`publish_event` /
    :meth:`subscribe_events` with Redis pub/sub so that events reach all
    workers.
    """

    def __init__(self) -> None:
        # user_id -> set of websockets
        self._user_connections: dict[str, set[WebSocket]] = {}
        # project_id -> set of user_ids currently viewing
        self._project_viewers: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, ws: WebSocket, user_id: str) -> None:
        """Accept the WebSocket and register the connection for *user_id*."""
        await ws.accept()
        async with self._lock:
            self._user_connections.setdefault(user_id, set()).add(ws)
        logger.info("WebSocket connected: user=%s", user_id)

    async def disconnect(self, ws: WebSocket, user_id: str) -> None:
        """Remove *ws* from tracked connections for *user_id*."""
        async with self._lock:
            conns = self._user_connections.get(user_id)
            if conns:
                conns.discard(ws)
                if not conns:
                    del self._user_connections[user_id]
            # Remove from all project viewer sets
            for viewers in self._project_viewers.values():
                viewers.discard(user_id)
        logger.info("WebSocket disconnected: user=%s", user_id)

    # ------------------------------------------------------------------
    # Project tracking
    # ------------------------------------------------------------------

    async def subscribe_project(self, user_id: str, project_id: str) -> None:
        """Mark *user_id* as viewing *project_id*."""
        async with self._lock:
            self._project_viewers.setdefault(project_id, set()).add(user_id)

    async def unsubscribe_project(self, user_id: str, project_id: str) -> None:
        """Remove *user_id* from *project_id* viewers."""
        async with self._lock:
            viewers = self._project_viewers.get(project_id)
            if viewers:
                viewers.discard(user_id)

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def _send_safe(self, ws: WebSocket, data: dict[str, Any]) -> bool:
        """Send JSON to *ws*, returning ``False`` if the socket is closed."""
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_json(data)
                return True
        except Exception:  # noqa: S110
            pass
        return False

    async def broadcast_to_project(self, project_id: str, event: dict[str, Any]) -> None:
        """Send *event* to every user currently viewing *project_id*."""
        async with self._lock:
            viewers = self._project_viewers.get(project_id, set()).copy()
            target_sockets: list[tuple[str, WebSocket]] = []
            for uid in viewers:
                for ws in self._user_connections.get(uid, set()).copy():
                    target_sockets.append((uid, ws))

        for _uid, ws in target_sockets:
            await self._send_safe(ws, event)

    async def broadcast_to_user(self, user_id: str, event: dict[str, Any]) -> None:
        """Send *event* to all connections belonging to *user_id*."""
        async with self._lock:
            sockets = list(self._user_connections.get(user_id, set()))

        for ws in sockets:
            await self._send_safe(ws, event)

    # ------------------------------------------------------------------
    # Redis pub/sub integration
    # ------------------------------------------------------------------

    async def publish_event(self, channel: str, event: dict[str, Any]) -> None:
        """Publish *event* to a Redis pub/sub channel.

        Falls back to a no-op warning if Redis is unavailable.
        """
        try:
            from app.redis import get_redis_pool

            redis = get_redis_pool()
            await redis.publish(channel, json.dumps(event, default=str))
            logger.debug("Published event to channel '%s'", channel)
        except Exception as exc:
            logger.warning("Failed to publish to Redis channel '%s': %s", channel, exc)

    async def subscribe_events(self, channel: str) -> None:
        """Subscribe to a Redis pub/sub channel and forward events locally.

        This should be run as a background task per channel.
        """
        try:
            from app.redis import get_redis_pool

            redis = get_redis_pool()
            pubsub = redis.pubsub()
            await pubsub.subscribe(channel)
            logger.info("Subscribed to Redis channel '%s'", channel)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        event = json.loads(message["data"])
                        project_id = event.get("project_id")
                        if project_id:
                            await self.broadcast_to_project(str(project_id), event)
                        user_id = event.get("target_user_id")
                        if user_id:
                            await self.broadcast_to_user(str(user_id), event)
                    except Exception as exc:
                        logger.error("Error processing pub/sub message: %s", exc)
        except Exception as exc:
            logger.warning("Redis subscription to '%s' failed: %s", channel, exc)


# Singleton instance used across the application
ws_manager = ConnectionManager()
