"""Notification ORM model — stores user notifications across channels."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow


class NotificationChannel(enum.StrEnum):
    IN_APP = "in_app"
    SLACK = "slack"
    TELEGRAM = "telegram"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        primary_key=True,
        default=generate_uuid,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel_enum", create_constraint=True),
        nullable=False,
        default=NotificationChannel.IN_APP,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Notification user={self.user_id} channel={self.channel.value} read={self.is_read}>"
        )
