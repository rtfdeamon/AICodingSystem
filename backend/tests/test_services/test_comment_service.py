"""Tests for comment_service — CRUD with threaded comment support."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.comment import CommentCreate, CommentUpdate
from app.services.comment_service import (
    create_comment,
    delete_comment,
    list_comments,
    update_comment,
)

# ---------------------------------------------------------------------------
# create_comment
# ---------------------------------------------------------------------------


async def test_create_comment(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Creates a top-level comment on a ticket."""
    user = await create_test_user(email="commenter@example.com")
    ticket = await create_test_ticket()

    data = CommentCreate(body="Hello, this is a comment")
    comment = await create_comment(
        db=db_session,
        ticket_id=ticket.id,
        author_id=user.id,
        data=data,
    )

    assert comment.body == "Hello, this is a comment"
    assert comment.ticket_id == ticket.id
    assert comment.author_id == user.id
    assert comment.parent_id is None


async def test_create_threaded_comment(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Creates a reply to an existing comment."""
    user = await create_test_user(email="threader@example.com")
    ticket = await create_test_ticket()

    # Create parent comment
    parent_data = CommentCreate(body="Parent comment")
    parent = await create_comment(
        db=db_session,
        ticket_id=ticket.id,
        author_id=user.id,
        data=parent_data,
    )

    # Create reply
    reply_data = CommentCreate(body="Reply to parent", parent_id=parent.id)
    reply = await create_comment(
        db=db_session,
        ticket_id=ticket.id,
        author_id=user.id,
        data=reply_data,
    )

    assert reply.parent_id == parent.id
    assert reply.body == "Reply to parent"


async def test_create_comment_invalid_parent(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Raises 404 when parent_id does not exist on the ticket."""
    user = await create_test_user(email="invalid-parent@example.com")
    ticket = await create_test_ticket()

    data = CommentCreate(body="Reply", parent_id=uuid.uuid4())

    with pytest.raises(HTTPException) as exc_info:
        await create_comment(
            db=db_session,
            ticket_id=ticket.id,
            author_id=user.id,
            data=data,
        )

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# list_comments
# ---------------------------------------------------------------------------


async def test_list_comments_empty(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Returns empty list when ticket has no comments."""
    ticket = await create_test_ticket()
    result = await list_comments(db=db_session, ticket_id=ticket.id)
    assert result == []


async def test_list_comments_multiple(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Returns all comments for a ticket ordered by creation time."""
    user = await create_test_user(email="lister@example.com")
    ticket = await create_test_ticket()

    for i in range(3):
        data = CommentCreate(body=f"Comment {i}")
        await create_comment(
            db=db_session,
            ticket_id=ticket.id,
            author_id=user.id,
            data=data,
        )

    result = await list_comments(db=db_session, ticket_id=ticket.id)
    assert len(result) == 3
    assert result[0].body == "Comment 0"
    assert result[2].body == "Comment 2"


# ---------------------------------------------------------------------------
# update_comment
# ---------------------------------------------------------------------------


async def test_update_comment(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Updates a comment body."""
    user = await create_test_user(email="updater@example.com")
    ticket = await create_test_ticket()

    data = CommentCreate(body="Original body")
    comment = await create_comment(
        db=db_session,
        ticket_id=ticket.id,
        author_id=user.id,
        data=data,
    )

    updated = await update_comment(
        db=db_session,
        comment_id=comment.id,
        data=CommentUpdate(body="Updated body"),
    )

    assert updated.body == "Updated body"


async def test_update_comment_not_found(db_session: AsyncSession):
    """Raises 404 when comment does not exist."""
    with pytest.raises(HTTPException) as exc_info:
        await update_comment(
            db=db_session,
            comment_id=uuid.uuid4(),
            data=CommentUpdate(body="new body"),
        )

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# delete_comment
# ---------------------------------------------------------------------------


async def test_delete_comment(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Deletes a comment successfully."""
    user = await create_test_user(email="deleter@example.com")
    ticket = await create_test_ticket()

    data = CommentCreate(body="To be deleted")
    comment = await create_comment(
        db=db_session,
        ticket_id=ticket.id,
        author_id=user.id,
        data=data,
    )

    await delete_comment(db=db_session, comment_id=comment.id)

    # Verify deletion
    result = await list_comments(db=db_session, ticket_id=ticket.id)
    assert len(result) == 0


async def test_delete_comment_not_found(db_session: AsyncSession):
    """Raises 404 when comment does not exist."""
    with pytest.raises(HTTPException) as exc_info:
        await delete_comment(db=db_session, comment_id=uuid.uuid4())

    assert exc_info.value.status_code == 404
