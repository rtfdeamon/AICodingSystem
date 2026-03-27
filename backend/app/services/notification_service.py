"""Multi-channel notification service — in-app, Slack, and Telegram."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.notification import Notification, NotificationChannel
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

# Maps column transitions to human-readable status descriptions
TRANSITION_LABELS: dict[tuple[str, str], str] = {
    ("backlog", "ai_planning"): "moved to AI Planning",
    ("ai_planning", "plan_review"): "AI plan ready for review",
    ("plan_review", "ai_coding"): "plan approved, AI coding started",
    ("plan_review", "backlog"): "plan rejected, returned to backlog",
    ("ai_coding", "code_review"): "AI code ready for review",
    ("code_review", "staging"): "code approved, deploying to staging",
    ("code_review", "ai_coding"): "changes requested, returned to AI coding",
    ("staging", "staging_verification"): "staging deploy complete, verifying",
    ("staging_verification", "production"): "verified, deploying to production",
    ("staging_verification", "ai_coding"): "staging verification failed, rework needed",
}


async def send_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    channel: str,
    title: str,
    body: str,
    ticket_id: uuid.UUID | None = None,
) -> Notification:
    """Send a notification to a user via the specified channel.

    Parameters
    ----------
    db:
        Database session.
    user_id:
        Target user ID.
    channel:
        Delivery channel: in_app, slack, or telegram.
    title:
        Notification title/subject.
    body:
        Notification body text.
    ticket_id:
        Optional ticket reference.

    Returns
    -------
    The persisted Notification record.
    """
    notification = Notification(
        user_id=user_id,
        ticket_id=ticket_id,
        channel=NotificationChannel(channel),
        title=title,
        body=body,
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)

    # Dispatch based on channel
    if channel == NotificationChannel.IN_APP.value or channel == NotificationChannel.IN_APP:
        await _send_in_app(user_id, notification)
    elif channel == NotificationChannel.SLACK.value or channel == NotificationChannel.SLACK:
        await send_slack(None, _format_slack_message(title, body, ticket_id))
    elif channel == NotificationChannel.TELEGRAM.value or channel == NotificationChannel.TELEGRAM:
        await send_telegram(None, f"*{title}*\n{body}")

    logger.info("Notification sent: user=%s channel=%s title='%s'", user_id, channel, title)
    return notification


async def _send_in_app(user_id: uuid.UUID, notification: Notification) -> None:
    """Push notification via WebSocket to all user connections."""
    event = {
        "type": "notification",
        "data": {
            "id": str(notification.id),
            "title": notification.title,
            "body": notification.body,
            "ticket_id": str(notification.ticket_id) if notification.ticket_id else None,
            "sent_at": notification.sent_at.isoformat() if notification.sent_at else None,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await ws_manager.broadcast_to_user(str(user_id), event)


def _format_slack_message(title: str, body: str, ticket_id: uuid.UUID | None = None) -> str:
    """Format a notification as a Slack message with markdown."""
    msg = f"*{title}*\n{body}"
    if ticket_id:
        msg += f"\n_Ticket: {ticket_id}_"
    return msg


async def send_slack(
    webhook_url_or_channel: str | None,
    message: str,
) -> bool:
    """Send a message to Slack via Bot API or incoming webhook.

    Parameters
    ----------
    webhook_url_or_channel:
        Slack channel name (e.g. "#pipeline-alerts") or a full webhook URL.
        If None, uses the default bot token and #general channel.
    message:
        Message text (supports Slack markdown/mrkdwn).

    Returns
    -------
    True if the message was sent successfully.
    """
    bot_token = settings.SLACK_BOT_TOKEN
    if not bot_token:
        logger.warning("SLACK_BOT_TOKEN not configured; skipping Slack notification")
        return False

    is_webhook = webhook_url_or_channel and webhook_url_or_channel.startswith("https://")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if is_webhook and webhook_url_or_channel:
                resp = await client.post(
                    webhook_url_or_channel,
                    json={"text": message},
                )
            else:
                channel = webhook_url_or_channel or "#general"
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={
                        "channel": channel,
                        "text": message,
                        "mrkdwn": True,
                    },
                )

            if resp.status_code == 200:
                data = resp.json() if not is_webhook else {"ok": True}
                if data.get("ok", True):
                    logger.info("Slack message sent to %s", webhook_url_or_channel or "#general")
                    return True
                else:
                    logger.error("Slack API error: %s", data.get("error"))
                    return False
            else:
                logger.error("Slack HTTP error: %d", resp.status_code)
                return False
    except httpx.RequestError as exc:
        logger.error("Failed to send Slack message: %s", exc)
        return False


async def send_telegram(
    chat_id: str | None,
    message: str,
) -> bool:
    """Send a message via Telegram Bot API.

    Parameters
    ----------
    chat_id:
        Telegram chat ID. If None, skips sending.
    message:
        Message text (supports Markdown).

    Returns
    -------
    True if the message was sent successfully.
    """
    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not configured; skipping Telegram notification")
        return False

    if not chat_id:
        logger.warning("No chat_id provided for Telegram notification")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                },
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    logger.info("Telegram message sent to chat %s", chat_id)
                    return True
                else:
                    logger.error("Telegram API error: %s", data.get("description"))
                    return False
            else:
                logger.error("Telegram HTTP error: %d", resp.status_code)
                return False
    except httpx.RequestError as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False


async def notify_on_transition(
    db: AsyncSession,
    ticket: Any,
    from_column: str,
    to_column: str,
) -> None:
    """Send automatic notifications when a ticket transitions between columns.

    Notifies the ticket assignee and reporter (if different) about
    the column transition.

    Parameters
    ----------
    db:
        Database session.
    ticket:
        The Ticket ORM object.
    from_column:
        Source column name.
    to_column:
        Destination column name.
    """
    transition_label = TRANSITION_LABELS.get(
        (from_column, to_column),
        f"moved from {from_column} to {to_column}",
    )

    title = f"Ticket #{ticket.ticket_number}: {transition_label}"
    body = f"'{ticket.title}' has been {transition_label}."

    # Collect unique user IDs to notify
    user_ids: set[uuid.UUID] = set()
    if ticket.assignee_id:
        user_ids.add(ticket.assignee_id)
    if ticket.reporter_id:
        user_ids.add(ticket.reporter_id)

    for uid in user_ids:
        try:
            await send_notification(
                db=db,
                user_id=uid,
                channel=NotificationChannel.IN_APP.value,
                title=title,
                body=body,
                ticket_id=ticket.id,
            )
        except Exception as exc:
            logger.error(
                "Failed to send transition notification to user %s: %s",
                uid,
                exc,
            )
