"""Notification schemas — request/response models for notifications."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.models.notification import Notification


class NotificationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    ticket_id: uuid.UUID | None = None
    channel: str
    title: str
    body: str
    is_read: bool
    sent_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_notification(cls, n: Notification) -> NotificationResponse:
        return cls(
            id=n.id,
            user_id=n.user_id,
            ticket_id=n.ticket_id,
            channel=n.channel.value,
            title=n.title,
            body=n.body,
            is_read=n.is_read,
            sent_at=n.sent_at.isoformat(),
        )


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    page: int
    per_page: int


class UnreadCountResponse(BaseModel):
    unread_count: int
