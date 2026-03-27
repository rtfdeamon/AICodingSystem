"""Comment ORM model with self-referential threading support."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class Comment(Base):
    __tablename__ = "comments"

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
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="user",
        doc="One of: user, ai_agent, system.",
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Self-referential FK for threaded comments
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    ticket: Mapped[Ticket] = relationship(  # noqa: F821
        "Ticket", back_populates="comments", lazy="joined"
    )
    author: Mapped[User | None] = relationship("User", lazy="joined")  # noqa: F821
    parent: Mapped[Comment | None] = relationship("Comment", remote_side=[id], lazy="joined")
    replies: Mapped[list[Comment]] = relationship(
        "Comment", back_populates="parent", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Comment {self.id} ticket={self.ticket_id}>"
