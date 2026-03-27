"""Notification endpoints — list, read, and count notifications."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class NotificationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    ticket_id: uuid.UUID | None = None
    channel: str
    title: str
    body: str
    is_read: bool
    sent_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_notification(cls, n: Notification) -> NotificationResponse:
        return cls(
            id=n.id,
            user_id=n.user_id,
            ticket_id=n.ticket_id,
            channel=n.channel.value,
            title=n.title,
            body=n.body,
            is_read=n.is_read,
            sent_at=n.sent_at.isoformat(),
        )


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    page: int
    per_page: int


class UnreadCountResponse(BaseModel):
    unread_count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
) -> NotificationListResponse:
    """List the current user's notifications (paginated)."""
    base_query = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        base_query = base_query.where(Notification.is_read == False)  # noqa: E712

    # Total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginated results
    query = (
        base_query.order_by(Notification.sent_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    notifications = result.scalars().all()

    return NotificationListResponse(
        items=[NotificationResponse.from_orm_notification(n) for n in notifications],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> NotificationResponse:
    """Mark a single notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == current_user.id
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )

    notification.is_read = True
    await db.flush()
    await db.refresh(notification)

    return NotificationResponse.from_orm_notification(notification)


@router.post("/notifications/read-all", response_model=dict[str, Any])
async def mark_all_read(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Mark all notifications as read for the current user."""
    result = await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
    )
    updated_count = result.rowcount  # type: ignore[attr-defined]

    logger.info("Marked %d notifications as read for user %s", updated_count, current_user.id)
    return {"marked_read": updated_count}


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UnreadCountResponse:
    """Get the count of unread notifications for the current user."""
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    count = result.scalar() or 0
    return UnreadCountResponse(unread_count=count)
