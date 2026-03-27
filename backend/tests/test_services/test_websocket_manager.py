"""Tests for the WebSocket ConnectionManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.websocket_manager import ConnectionManager

pytestmark = pytest.mark.asyncio


def _mock_ws(connected: bool = True) -> MagicMock:
    """Create a mock WebSocket."""
    from starlette.websockets import WebSocketState

    ws = AsyncMock()
    ws.client_state = WebSocketState.CONNECTED if connected else WebSocketState.DISCONNECTED
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


async def test_connect_and_disconnect() -> None:
    mgr = ConnectionManager()
    ws = _mock_ws()
    user_id = "user-1"

    await mgr.connect(ws, user_id)
    ws.accept.assert_called_once()

    assert user_id in mgr._user_connections
    assert ws in mgr._user_connections[user_id]

    await mgr.disconnect(ws, user_id)
    assert user_id not in mgr._user_connections


async def test_subscribe_and_unsubscribe_project() -> None:
    mgr = ConnectionManager()
    user_id = "user-1"
    project_id = "project-abc"

    await mgr.subscribe_project(user_id, project_id)
    assert user_id in mgr._project_viewers[project_id]

    await mgr.unsubscribe_project(user_id, project_id)
    assert user_id not in mgr._project_viewers.get(project_id, set())


async def test_broadcast_to_project() -> None:
    mgr = ConnectionManager()
    ws1 = _mock_ws()
    ws2 = _mock_ws()
    user_1 = "user-1"
    user_2 = "user-2"
    project_id = "project-abc"

    await mgr.connect(ws1, user_1)
    await mgr.connect(ws2, user_2)
    await mgr.subscribe_project(user_1, project_id)
    await mgr.subscribe_project(user_2, project_id)

    event = {"type": "ticket.moved", "data": {"ticket_id": "t1"}}
    await mgr.broadcast_to_project(project_id, event)

    ws1.send_json.assert_called_once_with(event)
    ws2.send_json.assert_called_once_with(event)


async def test_broadcast_to_project_only_subscribers() -> None:
    mgr = ConnectionManager()
    ws1 = _mock_ws()
    ws2 = _mock_ws()
    user_1 = "user-1"
    user_2 = "user-2"

    await mgr.connect(ws1, user_1)
    await mgr.connect(ws2, user_2)
    await mgr.subscribe_project(user_1, "project-abc")
    # user_2 is NOT subscribed

    event = {"type": "ticket.created", "data": {}}
    await mgr.broadcast_to_project("project-abc", event)

    ws1.send_json.assert_called_once_with(event)
    ws2.send_json.assert_not_called()


async def test_broadcast_to_user() -> None:
    mgr = ConnectionManager()
    ws = _mock_ws()
    user_id = "user-1"

    await mgr.connect(ws, user_id)

    event = {"type": "notification", "data": {"message": "hello"}}
    await mgr.broadcast_to_user(user_id, event)

    ws.send_json.assert_called_once_with(event)


async def test_broadcast_to_disconnected_socket() -> None:
    mgr = ConnectionManager()
    ws = _mock_ws(connected=False)
    user_id = "user-1"

    # Manually add since connect would call accept
    async with mgr._lock:
        mgr._user_connections.setdefault(user_id, set()).add(ws)
        mgr._project_viewers.setdefault("p1", set()).add(user_id)

    event = {"type": "test", "data": {}}
    await mgr.broadcast_to_project("p1", event)

    ws.send_json.assert_not_called()


async def test_multiple_connections_per_user() -> None:
    mgr = ConnectionManager()
    ws1 = _mock_ws()
    ws2 = _mock_ws()
    user_id = "user-1"

    await mgr.connect(ws1, user_id)
    await mgr.connect(ws2, user_id)

    assert len(mgr._user_connections[user_id]) == 2

    event = {"type": "notification", "data": {}}
    await mgr.broadcast_to_user(user_id, event)

    ws1.send_json.assert_called_once_with(event)
    ws2.send_json.assert_called_once_with(event)


async def test_disconnect_cleans_project_viewers() -> None:
    mgr = ConnectionManager()
    ws = _mock_ws()
    user_id = "user-1"

    await mgr.connect(ws, user_id)
    await mgr.subscribe_project(user_id, "project-1")
    await mgr.subscribe_project(user_id, "project-2")

    await mgr.disconnect(ws, user_id)

    assert user_id not in mgr._project_viewers.get("project-1", set())
    assert user_id not in mgr._project_viewers.get("project-2", set())


async def test_send_safe_returns_true_on_success() -> None:
    mgr = ConnectionManager()
    ws = _mock_ws(connected=True)
    result = await mgr._send_safe(ws, {"type": "test"})
    assert result is True
    ws.send_json.assert_awaited_once()


async def test_send_safe_returns_false_on_exception() -> None:
    mgr = ConnectionManager()
    ws = _mock_ws(connected=True)
    ws.send_json.side_effect = RuntimeError("broken")
    result = await mgr._send_safe(ws, {"type": "test"})
    assert result is False


async def test_send_safe_returns_false_when_disconnected() -> None:
    mgr = ConnectionManager()
    ws = _mock_ws(connected=False)
    result = await mgr._send_safe(ws, {"type": "test"})
    assert result is False
    ws.send_json.assert_not_awaited()


async def test_publish_event_success() -> None:
    from unittest.mock import patch

    mgr = ConnectionManager()
    mock_redis = AsyncMock()

    with patch(
        "app.redis.get_redis_pool",
        return_value=mock_redis,
    ):
        await mgr.publish_event("ch-1", {"type": "test"})
        mock_redis.publish.assert_awaited_once()


async def test_publish_event_redis_unavailable() -> None:
    from unittest.mock import patch

    mgr = ConnectionManager()

    with patch(
        "app.redis.get_redis_pool",
        side_effect=RuntimeError("no redis"),
    ):
        await mgr.publish_event("ch-1", {"type": "test"})  # Should not raise


async def test_disconnect_nonexistent_user() -> None:
    mgr = ConnectionManager()
    ws = _mock_ws()
    await mgr.disconnect(ws, "nonexistent")  # Should not raise


async def test_unsubscribe_nonexistent_project() -> None:
    mgr = ConnectionManager()
    await mgr.unsubscribe_project("user-1", "nonexistent")  # Should not raise


async def test_broadcast_to_empty_project() -> None:
    mgr = ConnectionManager()
    await mgr.broadcast_to_project("empty-project", {"type": "test"})  # Should not raise


async def test_broadcast_to_user_no_connections() -> None:
    mgr = ConnectionManager()
    await mgr.broadcast_to_user("unknown-user", {"type": "test"})  # Should not raise
