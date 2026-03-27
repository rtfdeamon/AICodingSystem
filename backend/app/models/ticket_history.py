"""TicketHistory ORM model — audit trail for ticket state changes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base
from app.models.base_types import DBUUID, generate_uuid, utcnow

if TYPE_CHECKING:
    from app.models.ticket import Ticket
    from app.models.user import User


class TicketHistory(Base):
    __tablename__ = "ticket_history"

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
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        DBUUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="user",
        doc="One of: user, ai_agent, system.",
    )

    # Transition details
    from_column: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_column: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action: Mapped[str] = mapped_column(
        String(64), nullable=False, doc="E.g. moved, created, assigned, commented."
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow, nullable=False
    )

    # Relationships
    ticket: Mapped[Ticket] = relationship(  # noqa: F821
        "Ticket", back_populates="history", lazy="joined"
    )
    actor: Mapped[User | None] = relationship("User", lazy="joined")  # noqa: F821

    def __repr__(self) -> str:
        return f"<TicketHistory {self.action} ticket={self.ticket_id}>"
