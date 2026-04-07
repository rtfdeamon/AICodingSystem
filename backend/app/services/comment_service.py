"""Comment CRUD service with threaded comment support."""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.schemas.comment import CommentCreate, CommentResponse, CommentUpdate

logger = logging.getLogger(__name__)


async def create_comment(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    author_id: uuid.UUID,
    data: CommentCreate,
) -> Comment:
    """Create a new comment (optionally threaded via *parent_id*)."""
    # Validate parent exists if specified
    if data.parent_id is not None:
        parent = await db.execute(
            select(Comment).where(
                Comment.id == data.parent_id,
                Comment.ticket_id == ticket_id,
            )
        )
        if parent.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found on this ticket.",
            )

    comment = Comment(
        ticket_id=ticket_id,
        author_id=author_id,
        author_type="user",
        body=data.body,
        parent_id=data.parent_id,
    )
    db.add(comment)
    await db.flush()
    await db.refresh(comment)

    # Eagerly load the author relationship for the response
    if comment.author_id:
        from app.models.user import User
        result = await db.execute(
            select(User).where(User.id == comment.author_id)
        )
        comment.author = result.scalar_one_or_none()

    logger.info("Comment created: %s on ticket %s", comment.id, ticket_id)
    return comment


async def list_comments(
    db: AsyncSession,
    ticket_id: uuid.UUID,
) -> list[CommentResponse]:
    """Return all comments for a ticket, threaded (top-level first with replies)."""
    result = await db.execute(
        select(Comment).where(Comment.ticket_id == ticket_id).order_by(Comment.created_at.asc())
    )
    comments = list(result.scalars().all())

    # Build threaded structure: return top-level comments; replies are nested
    # via the ORM relationship.  For the API we flatten but include parent_id
    # so the frontend can reconstruct the tree.
    return [CommentResponse.from_orm_comment(c) for c in comments]


async def update_comment(
    db: AsyncSession,
    comment_id: uuid.UUID,
    data: CommentUpdate,
) -> Comment:
    """Update a comment's body."""
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found.",
        )

    comment.body = data.body
    await db.flush()
    await db.refresh(comment)

    logger.info("Comment updated: %s", comment_id)
    return comment


async def delete_comment(db: AsyncSession, comment_id: uuid.UUID) -> None:
    """Delete a comment."""
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found.",
        )

    await db.delete(comment)
    logger.info("Comment deleted: %s", comment_id)
