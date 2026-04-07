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


class CommentUserInfo(BaseModel):
    """Minimal user info embedded in comment responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    avatar_url: str | None = None


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
    user: CommentUserInfo | None = None

    @classmethod
    def from_orm_comment(cls, comment: object) -> CommentResponse:
        """Build response with embedded user info from the ORM relationship."""
        author = getattr(comment, "author", None)
        user_info = None
        if author:
            user_info = CommentUserInfo(
                id=author.id,
                full_name=author.full_name,
                email=author.email,
                avatar_url=author.avatar_url,
            )
        return cls(
            id=comment.id,  # type: ignore[attr-defined]
            ticket_id=comment.ticket_id,  # type: ignore[attr-defined]
            author_id=comment.author_id,  # type: ignore[attr-defined]
            author_type=comment.author_type,  # type: ignore[attr-defined]
            body=comment.body,  # type: ignore[attr-defined]
            parent_id=comment.parent_id,  # type: ignore[attr-defined]
            created_at=comment.created_at,  # type: ignore[attr-defined]
            updated_at=comment.updated_at,  # type: ignore[attr-defined]
            user=user_info,
        )
