"""Pydantic schemas for WebSocket event payloads."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class WSEventType(StrEnum):
    """Recognised WebSocket event types."""

    TICKET_CREATED = "ticket.created"
    TICKET_UPDATED = "ticket.updated"
    TICKET_MOVED = "ticket.moved"
    TICKET_DELETED = "ticket.deleted"
    COMMENT_ADDED = "comment.added"
    COMMENT_UPDATED = "comment.updated"
    COMMENT_DELETED = "comment.deleted"
    AI_STATUS = "ai.status"
    PIPELINE_PROGRESS = "pipeline.progress"
    USER_JOINED = "user.joined"
    USER_LEFT = "user.left"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class WSEvent(BaseModel):
    """Envelope for every WebSocket message."""

    type: WSEventType
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TicketMovedEvent(BaseModel):
    """Data payload when a ticket changes columns."""

    ticket_id: uuid.UUID
    from_column: str
    to_column: str
    actor_id: uuid.UUID | None = None
    actor_type: str = "user"


class AIStatusEvent(BaseModel):
    """Data payload for AI pipeline status updates."""

    ticket_id: uuid.UUID
    stage: str
    status: str  # running, completed, failed
    message: str | None = None
    progress: float | None = Field(default=None, ge=0.0, le=1.0)


class PipelineProgressEvent(BaseModel):
    """Detailed pipeline step progress."""

    ticket_id: uuid.UUID
    step: str
    step_index: int
    total_steps: int
    status: str
    output: str | None = None
