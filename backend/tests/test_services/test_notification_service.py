"""Tests for notification_service — multi-channel notification delivery."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationChannel
from app.services.notification_service import (
    TRANSITION_LABELS,
    _format_slack_message,
    notify_on_transition,
    send_notification,
    send_slack,
    send_telegram,
)


def _mock_httpx_client(response_status=200, response_json=None):
    """Create a mock httpx.AsyncClient that works as async context manager."""
    mock_response = MagicMock()
    mock_response.status_code = response_status
    mock_response.json.return_value = response_json or {}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client, mock_response


# ---------------------------------------------------------------------------
# send_notification — in_app channel
# ---------------------------------------------------------------------------


async def test_send_notification_in_app(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """In-app notification is persisted and dispatched via WS."""
    user = await create_test_user(email="notif-user@example.com")
    ticket = await create_test_ticket()

    with patch("app.services.notification_service.ws_manager") as mock_ws:
        mock_ws.broadcast_to_user = AsyncMock()

        notification = await send_notification(
            db=db_session,
            user_id=user.id,
            channel="in_app",
            title="Test title",
            body="Test body",
            ticket_id=ticket.id,
        )

    assert notification.title == "Test title"
    assert notification.body == "Test body"
    assert notification.channel == NotificationChannel.IN_APP
    assert notification.user_id == user.id
    mock_ws.broadcast_to_user.assert_awaited_once()


# ---------------------------------------------------------------------------
# send_slack
# ---------------------------------------------------------------------------


async def test_send_slack_no_token():
    """Returns False when SLACK_BOT_TOKEN is not configured."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.SLACK_BOT_TOKEN = None
        result = await send_slack("#general", "hello")
    assert result is False


async def test_send_slack_success():
    """Sends a message via Slack Bot API when token is present."""
    mock_client, _ = _mock_httpx_client(
        response_status=200,
        response_json={"ok": True},
    )

    with (
        patch("app.services.notification_service.settings") as mock_settings,
        patch(
            "app.services.notification_service.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        mock_settings.SLACK_BOT_TOKEN = "xoxb-fake-token"
        result = await send_slack("#alerts", "test message")

    assert result is True


async def test_send_slack_webhook():
    """Uses webhook URL directly when provided."""
    mock_client, _ = _mock_httpx_client(
        response_status=200,
        response_json={"ok": True},
    )

    with (
        patch("app.services.notification_service.settings") as mock_settings,
        patch(
            "app.services.notification_service.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        mock_settings.SLACK_BOT_TOKEN = "xoxb-fake"
        result = await send_slack(
            "https://hooks.slack.com/services/T00/B00/XXX",
            "hello",
        )

    assert result is True


async def test_send_slack_http_error():
    """Returns False on HTTP error from Slack."""
    mock_client, _ = _mock_httpx_client(response_status=500)

    with (
        patch("app.services.notification_service.settings") as mock_settings,
        patch(
            "app.services.notification_service.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        mock_settings.SLACK_BOT_TOKEN = "xoxb-fake"
        result = await send_slack("#general", "fail")

    assert result is False


# ---------------------------------------------------------------------------
# send_telegram
# ---------------------------------------------------------------------------


async def test_send_telegram_no_token():
    """Returns False when TELEGRAM_BOT_TOKEN is not configured."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.TELEGRAM_BOT_TOKEN = None
        result = await send_telegram("12345", "hello")
    assert result is False


async def test_send_telegram_no_chat_id():
    """Returns False when chat_id is None."""
    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.TELEGRAM_BOT_TOKEN = "fake-token"
        result = await send_telegram(None, "hello")
    assert result is False


async def test_send_telegram_success():
    """Sends a message via Telegram Bot API."""
    mock_client, _ = _mock_httpx_client(
        response_status=200,
        response_json={"ok": True},
    )

    with (
        patch("app.services.notification_service.settings") as mock_settings,
        patch(
            "app.services.notification_service.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        mock_settings.TELEGRAM_BOT_TOKEN = "fake-token"
        result = await send_telegram("12345", "test msg")

    assert result is True


async def test_send_telegram_http_error():
    """Returns False on HTTP error from Telegram."""
    mock_client, _ = _mock_httpx_client(response_status=403)

    with (
        patch("app.services.notification_service.settings") as mock_settings,
        patch(
            "app.services.notification_service.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        mock_settings.TELEGRAM_BOT_TOKEN = "fake-token"
        result = await send_telegram("12345", "fail")

    assert result is False


# ---------------------------------------------------------------------------
# _format_slack_message
# ---------------------------------------------------------------------------


def test_format_slack_message_with_ticket():
    """Includes ticket ID in the message when provided."""
    tid = uuid.uuid4()
    msg = _format_slack_message("Title", "Body", tid)
    assert "Title" in msg
    assert "Body" in msg
    assert str(tid) in msg


def test_format_slack_message_without_ticket():
    """Works without ticket ID."""
    msg = _format_slack_message("Title", "Body")
    assert "Title" in msg
    assert "Body" in msg


# ---------------------------------------------------------------------------
# notify_on_transition
# ---------------------------------------------------------------------------


async def test_notify_on_transition_known_label(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Sends notifications with a known transition label."""
    user = await create_test_user(email="transition-user@example.com")
    ticket = await create_test_ticket()
    ticket.assignee_id = user.id
    ticket.reporter_id = user.id
    await db_session.flush()

    with patch("app.services.notification_service.ws_manager") as mock_ws:
        mock_ws.broadcast_to_user = AsyncMock()

        await notify_on_transition(
            db=db_session,
            ticket=ticket,
            from_column="backlog",
            to_column="ai_planning",
        )

    # Should have sent in-app notification
    mock_ws.broadcast_to_user.assert_awaited_once()


async def test_notify_on_transition_unknown_label(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Falls back to generic transition description for unknown transitions."""
    user = await create_test_user(email="unknown-trans@example.com")
    ticket = await create_test_ticket()
    ticket.assignee_id = user.id
    await db_session.flush()

    with patch("app.services.notification_service.ws_manager") as mock_ws:
        mock_ws.broadcast_to_user = AsyncMock()

        await notify_on_transition(
            db=db_session,
            ticket=ticket,
            from_column="staging",
            to_column="production",
        )

    mock_ws.broadcast_to_user.assert_awaited_once()


async def test_notify_on_transition_no_users(
    db_session: AsyncSession,
    create_test_ticket,
):
    """No notifications sent when ticket has no assignee/reporter."""
    ticket = await create_test_ticket()

    with patch("app.services.notification_service.ws_manager") as mock_ws:
        mock_ws.broadcast_to_user = AsyncMock()

        await notify_on_transition(
            db=db_session,
            ticket=ticket,
            from_column="backlog",
            to_column="ai_planning",
        )

    mock_ws.broadcast_to_user.assert_not_awaited()


# ---------------------------------------------------------------------------
# TRANSITION_LABELS coverage
# ---------------------------------------------------------------------------


def test_transition_labels_contains_expected_keys():
    """TRANSITION_LABELS has entries for critical pipeline transitions."""
    assert ("backlog", "ai_planning") in TRANSITION_LABELS
    assert ("staging_verification", "production") in TRANSITION_LABELS
    assert ("code_review", "ai_coding") in TRANSITION_LABELS
