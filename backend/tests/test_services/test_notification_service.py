"""Comprehensive tests for notification_service — multi-channel delivery."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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

# NOTE: Only async test methods use @pytest.mark.asyncio (via asyncio_mode=auto).
# Do NOT use module-level pytestmark to avoid warnings on sync tests.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ===================================================================
# send_notification
# ===================================================================


class TestSendNotificationInApp:
    """IN_APP channel tests."""

    async def test_creates_notification_and_dispatches_ws(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="in-app@example.com")
        ticket = await create_test_ticket()

        with patch("app.services.notification_service.ws_manager") as mock_ws:
            mock_ws.broadcast_to_user = AsyncMock()
            notification = await send_notification(
                db=db_session,
                user_id=user.id,
                channel="in_app",
                title="Test Title",
                body="Test Body",
                ticket_id=ticket.id,
            )

        assert notification.title == "Test Title"
        assert notification.body == "Test Body"
        assert notification.channel == NotificationChannel.IN_APP
        assert notification.user_id == user.id
        assert notification.ticket_id == ticket.id
        mock_ws.broadcast_to_user.assert_awaited_once()

    async def test_in_app_without_ticket_id(
        self,
        db_session: AsyncSession,
        create_test_user,
    ) -> None:
        user = await create_test_user(email="in-app-no-ticket@example.com")

        with patch("app.services.notification_service.ws_manager") as mock_ws:
            mock_ws.broadcast_to_user = AsyncMock()
            notification = await send_notification(
                db=db_session,
                user_id=user.id,
                channel="in_app",
                title="No Ticket",
                body="No ticket body",
            )

        assert notification.ticket_id is None
        mock_ws.broadcast_to_user.assert_awaited_once()


class TestSendNotificationSlack:
    """SLACK channel tests."""

    async def test_creates_notification_and_calls_send_slack(
        self,
        db_session: AsyncSession,
        create_test_user,
    ) -> None:
        user = await create_test_user(email="slack-notif@example.com")

        with (
            patch("app.services.notification_service.ws_manager"),
            patch(
                "app.services.notification_service.send_slack",
                new_callable=AsyncMock,
            ) as mock_send_slack,
        ):
            notification = await send_notification(
                db=db_session,
                user_id=user.id,
                channel="slack",
                title="Slack Title",
                body="Slack Body",
            )

        assert notification.channel == NotificationChannel.SLACK
        mock_send_slack.assert_awaited_once()


class TestSendNotificationTelegram:
    """TELEGRAM channel tests."""

    async def test_creates_notification_and_calls_send_telegram(
        self,
        db_session: AsyncSession,
        create_test_user,
    ) -> None:
        user = await create_test_user(email="tg-notif@example.com")

        with (
            patch("app.services.notification_service.ws_manager"),
            patch(
                "app.services.notification_service.send_telegram",
                new_callable=AsyncMock,
            ) as mock_send_tg,
        ):
            notification = await send_notification(
                db=db_session,
                user_id=user.id,
                channel="telegram",
                title="TG Title",
                body="TG Body",
            )

        assert notification.channel == NotificationChannel.TELEGRAM
        mock_send_tg.assert_awaited_once()


# ===================================================================
# send_slack
# ===================================================================


class TestSendSlack:
    """Slack delivery tests."""

    async def test_no_bot_token_returns_false(self) -> None:
        with patch("app.services.notification_service.settings") as mock_settings:
            mock_settings.SLACK_BOT_TOKEN = None
            result = await send_slack("#general", "hello")
        assert result is False

    async def test_webhook_url_posts_to_webhook(self) -> None:
        mock_client, _ = _mock_httpx_client(
            response_status=200, response_json={"ok": True}
        )
        webhook_url = "https://hooks.slack.com/services/T00/B00/XXX"

        with (
            patch("app.services.notification_service.settings") as mock_settings,
            patch(
                "app.services.notification_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.SLACK_BOT_TOKEN = "xoxb-fake"
            result = await send_slack(webhook_url, "hello webhook")

        assert result is True
        mock_client.post.assert_awaited_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == webhook_url
        assert call_args[1]["json"] == {"text": "hello webhook"}

    async def test_channel_name_posts_to_slack_api(self) -> None:
        mock_client, _ = _mock_httpx_client(
            response_status=200, response_json={"ok": True}
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
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://slack.com/api/chat.postMessage"
        assert "Bearer xoxb-fake-token" in call_args[1]["headers"]["Authorization"]
        assert call_args[1]["json"]["channel"] == "#alerts"

    async def test_none_channel_defaults_to_general(self) -> None:
        mock_client, _ = _mock_httpx_client(
            response_status=200, response_json={"ok": True}
        )

        with (
            patch("app.services.notification_service.settings") as mock_settings,
            patch(
                "app.services.notification_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.SLACK_BOT_TOKEN = "xoxb-fake"
            result = await send_slack(None, "default channel")

        assert result is True
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["channel"] == "#general"

    async def test_http_error_returns_false(self) -> None:
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

    async def test_api_error_ok_false_returns_false(self) -> None:
        mock_client, _ = _mock_httpx_client(
            response_status=200, response_json={"ok": False, "error": "channel_not_found"}
        )

        with (
            patch("app.services.notification_service.settings") as mock_settings,
            patch(
                "app.services.notification_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.SLACK_BOT_TOKEN = "xoxb-fake"
            result = await send_slack("#nonexistent", "msg")

        assert result is False

    async def test_network_error_returns_false(self) -> None:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.RequestError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.notification_service.settings") as mock_settings,
            patch(
                "app.services.notification_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.SLACK_BOT_TOKEN = "xoxb-fake"
            result = await send_slack("#general", "network fail")

        assert result is False


# ===================================================================
# send_telegram
# ===================================================================


class TestSendTelegram:
    """Telegram delivery tests."""

    async def test_no_bot_token_returns_false(self) -> None:
        with patch("app.services.notification_service.settings") as mock_settings:
            mock_settings.TELEGRAM_BOT_TOKEN = None
            result = await send_telegram("12345", "hello")
        assert result is False

    async def test_no_chat_id_returns_false(self) -> None:
        with patch("app.services.notification_service.settings") as mock_settings:
            mock_settings.TELEGRAM_BOT_TOKEN = "fake-token"
            result = await send_telegram(None, "hello")
        assert result is False

    async def test_successful_send_returns_true(self) -> None:
        mock_client, _ = _mock_httpx_client(
            response_status=200, response_json={"ok": True}
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
        call_args = mock_client.post.call_args
        assert "fake-token" in call_args[0][0]
        assert call_args[1]["json"]["chat_id"] == "12345"

    async def test_http_error_returns_false(self) -> None:
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

    async def test_api_error_ok_false_returns_false(self) -> None:
        mock_client, _ = _mock_httpx_client(
            response_status=200,
            response_json={"ok": False, "description": "Bad Request"},
        )

        with (
            patch("app.services.notification_service.settings") as mock_settings,
            patch(
                "app.services.notification_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.TELEGRAM_BOT_TOKEN = "fake-token"
            result = await send_telegram("12345", "api error")

        assert result is False

    async def test_network_error_returns_false(self) -> None:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.RequestError("Timeout")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.notification_service.settings") as mock_settings,
            patch(
                "app.services.notification_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            mock_settings.TELEGRAM_BOT_TOKEN = "fake-token"
            result = await send_telegram("12345", "timeout")

        assert result is False


# ===================================================================
# notify_on_transition
# ===================================================================


class TestNotifyOnTransition:
    """Transition notification tests."""

    async def test_known_transition_label(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="known-label@example.com")
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

        # One call because assignee == reporter (deduped)
        mock_ws.broadcast_to_user.assert_awaited_once()

    async def test_unknown_transition_falls_back(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="unknown-label@example.com")
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

    async def test_notifies_both_assignee_and_reporter(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        assignee = await create_test_user(email="assignee@example.com")
        reporter = await create_test_user(email="reporter@example.com")
        ticket = await create_test_ticket()
        ticket.assignee_id = assignee.id
        ticket.reporter_id = reporter.id
        await db_session.flush()

        with patch("app.services.notification_service.ws_manager") as mock_ws:
            mock_ws.broadcast_to_user = AsyncMock()
            await notify_on_transition(
                db=db_session,
                ticket=ticket,
                from_column="backlog",
                to_column="ai_planning",
            )

        assert mock_ws.broadcast_to_user.await_count == 2

    async def test_unique_user_ids_deduped(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        """When assignee == reporter, only one notification is sent."""
        user = await create_test_user(email="same-user@example.com")
        ticket = await create_test_ticket()
        ticket.assignee_id = user.id
        ticket.reporter_id = user.id
        await db_session.flush()

        with patch("app.services.notification_service.ws_manager") as mock_ws:
            mock_ws.broadcast_to_user = AsyncMock()
            await notify_on_transition(
                db=db_session,
                ticket=ticket,
                from_column="ai_coding",
                to_column="code_review",
            )

        mock_ws.broadcast_to_user.assert_awaited_once()

    async def test_no_assignee_no_reporter_no_notifications(
        self,
        db_session: AsyncSession,
        create_test_ticket,
    ) -> None:
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

    async def test_exception_in_send_notification_does_not_propagate(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="exception@example.com")
        ticket = await create_test_ticket()
        ticket.assignee_id = user.id
        await db_session.flush()

        with patch(
            "app.services.notification_service.send_notification",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB error"),
        ):
            # Should not raise
            await notify_on_transition(
                db=db_session,
                ticket=ticket,
                from_column="backlog",
                to_column="ai_planning",
            )


# ===================================================================
# _format_slack_message
# ===================================================================


class TestFormatSlackMessage:
    """Slack message formatting tests."""

    def test_with_ticket_id(self) -> None:
        tid = uuid.uuid4()
        msg = _format_slack_message("Title", "Body", tid)
        assert "*Title*" in msg
        assert "Body" in msg
        assert str(tid) in msg

    def test_without_ticket_id(self) -> None:
        msg = _format_slack_message("Title", "Body")
        assert "*Title*" in msg
        assert "Body" in msg
        assert "Ticket:" not in msg


# ===================================================================
# TRANSITION_LABELS coverage
# ===================================================================


class TestTransitionLabels:
    """Verify transition label constants."""

    def test_contains_expected_keys(self) -> None:
        assert ("backlog", "ai_planning") in TRANSITION_LABELS
        assert ("staging_verification", "production") in TRANSITION_LABELS
        assert ("code_review", "ai_coding") in TRANSITION_LABELS
        assert ("ai_planning", "plan_review") in TRANSITION_LABELS

    def test_all_labels_are_strings(self) -> None:
        for key, label in TRANSITION_LABELS.items():
            assert isinstance(label, str), f"Label for {key} is not a string"
            assert len(label) > 0
