"""Comment CRUD endpoints with threaded reply support."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentResponse, CommentUpdate
from app.services import comment_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/tickets/{ticket_id}/comments",
    response_model=list[CommentResponse],
)
async def list_comments(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> list[CommentResponse]:
    """List all comments for a ticket (threaded via parent_id)."""
    return await comment_service.list_comments(db, ticket_id)


@router.post(
    "/tickets/{ticket_id}/comments",
    response_model=CommentResponse,
    status_code=201,
)
async def create_comment(
    ticket_id: uuid.UUID,
    data: CommentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CommentResponse:
    """Add a comment to a ticket.  Optionally reply to a parent comment."""
    comment = await comment_service.create_comment(db, ticket_id, current_user.id, data)
    return CommentResponse.model_validate(comment)


@router.patch("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: uuid.UUID,
    data: CommentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> CommentResponse:
    """Update a comment's body."""
    comment = await comment_service.update_comment(db, comment_id, data)
    return CommentResponse.model_validate(comment)


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Delete a comment."""
    await comment_service.delete_comment(db, comment_id)
