"""Attachment ORM model for file uploads on tickets."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        primary_key=True,
        default=generate_uuid,
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploader_id: Mapped[uuid.UUID] = mapped_column(
        DBUUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        doc="Original filename as uploaded by the user.",
    )
    content_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="MIME type of the uploaded file.",
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="File size in bytes.",
    )
    storage_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        doc="Local filesystem path where the file is stored.",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        nullable=False,
    )

    # Relationships
    ticket: Mapped[Ticket] = relationship(  # noqa: F821
        "Ticket", lazy="joined"
    )
    uploader: Mapped[User] = relationship(  # noqa: F821
        "User", lazy="joined"
    )

    def __repr__(self) -> str:
        return f"<Attachment {self.id} filename={self.filename!r}>"
