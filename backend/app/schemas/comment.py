"""Pydantic schemas for Comment CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommentCreate(BaseModel):
    """Payload for adding a comment to a ticket."""

    body: str = Field(min_length=1, max_length=10_000)
    parent_id: uuid.UUID | None = None


class CommentUpdate(BaseModel):
    """Payload for editing a comment."""

    body: str = Field(min_length=1, max_length=10_000)


class CommentResponse(BaseModel):
    """Public representation of a comment."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID | None = None
    author_type: str
    body: str
    parent_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
