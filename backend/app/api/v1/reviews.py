"""Code review endpoints — human and AI reviews for tickets."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.review import Review, ReviewDecision, ReviewerType
from app.models.ticket import ColumnName, Ticket
from app.models.user import User
from app.services.kanban_service import move_ticket

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class InlineCommentSchema(BaseModel):
    file: str
    line: int
    comment: str
    severity: str = Field(pattern=r"^(critical|warning|suggestion|style)$")


class ReviewCreate(BaseModel):
    decision: str = Field(pattern=r"^(approved|rejected|changes_requested)$")
    body: str | None = None
    inline_comments: list[InlineCommentSchema] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    reviewer_id: uuid.UUID | None = None
    reviewer_type: str
    agent_name: str | None = None
    decision: str
    body: str | None = None
    inline_comments: list[dict[str, Any]] | None = None
    log_id: uuid.UUID | None = None
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_review(cls, review: Review) -> ReviewResponse:
        return cls(
            id=review.id,
            ticket_id=review.ticket_id,
            reviewer_id=review.reviewer_id,
            reviewer_type=review.reviewer_type.value,
            agent_name=review.agent_name,
            decision=review.decision.value,
            body=review.body,
            inline_comments=review.inline_comments,
            log_id=review.log_id,
            created_at=review.created_at.isoformat(),
        )


class AiReviewTriggerResponse(BaseModel):
    review_id: uuid.UUID
    summary: str
    comment_count: int
    total_cost_usd: float
    agent_reviews: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/tickets/{ticket_id}/reviews", response_model=list[ReviewResponse])
async def list_reviews(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> list[ReviewResponse]:
    """List all reviews for a ticket."""
    result = await db.execute(
        select(Review).where(Review.ticket_id == ticket_id).order_by(Review.created_at.desc())
    )
    reviews = result.scalars().all()
    return [ReviewResponse.from_orm_review(r) for r in reviews]


@router.post(
    "/tickets/{ticket_id}/reviews",
    response_model=ReviewResponse,
    status_code=201,
)
async def submit_review(
    ticket_id: uuid.UUID,
    data: ReviewCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ReviewResponse:
    """Submit a human code review for a ticket.

    If the decision is 'approved', the ticket will automatically move
    to the staging column.
    """
    # Verify ticket exists
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    inline_comments_data: list[dict[str, Any]] | None = None
    if data.inline_comments:
        inline_comments_data = [c.model_dump() for c in data.inline_comments]

    review = Review(
        ticket_id=ticket_id,
        reviewer_id=current_user.id,
        reviewer_type=ReviewerType.USER,
        decision=ReviewDecision(data.decision),
        body=data.body,
        inline_comments=inline_comments_data,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)

    # If approved and ticket is in code_review, move to staging
    if data.decision == "approved":
        from_col = (
            ticket.column_name.value
            if isinstance(ticket.column_name, ColumnName)
            else ticket.column_name
        )
        if from_col == ColumnName.CODE_REVIEW.value:
            try:
                await move_ticket(
                    db=db,
                    ticket_id=ticket_id,
                    to_column=ColumnName.STAGING.value,
                    actor_id=current_user.id,
                    actor_role=current_user.role,
                    comment="Auto-moved after code review approval.",
                )
            except HTTPException:
                logger.warning(
                    "Could not auto-move ticket %s to staging after approval",
                    ticket_id,
                )

    # If changes_requested, move back to ai_coding
    elif data.decision == "changes_requested":
        from_col = (
            ticket.column_name.value
            if isinstance(ticket.column_name, ColumnName)
            else ticket.column_name
        )
        if from_col == ColumnName.CODE_REVIEW.value:
            try:
                await move_ticket(
                    db=db,
                    ticket_id=ticket_id,
                    to_column=ColumnName.AI_CODING.value,
                    actor_id=current_user.id,
                    actor_role=current_user.role,
                    comment="Changes requested during code review.",
                )
            except HTTPException:
                logger.warning(
                    "Could not auto-move ticket %s back to ai_coding after changes requested",
                    ticket_id,
                )

    logger.info(
        "Review submitted for ticket %s by user %s: %s",
        ticket_id,
        current_user.id,
        data.decision,
    )

    return ReviewResponse.from_orm_review(review)


@router.post(
    "/tickets/{ticket_id}/reviews/ai-trigger",
    response_model=AiReviewTriggerResponse,
    status_code=201,
)
async def trigger_ai_review(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AiReviewTriggerResponse:
    """Trigger an AI code review for a ticket.

    Runs Claude and Codex in parallel to review the ticket's code diff.
    """
    from app.agents.review_agent import review_code, review_result_to_json

    # Get ticket
    ticket_result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")

    # Build context from ticket description
    ticket_desc = f"Title: {ticket.title}\n"
    if ticket.description:
        ticket_desc += f"Description: {ticket.description}\n"
    if ticket.acceptance_criteria:
        ticket_desc += f"Acceptance Criteria: {ticket.acceptance_criteria}\n"

    # Use PR URL or branch name for diff context
    diff_context = ""
    if ticket.pr_url:
        diff_context = f"PR URL: {ticket.pr_url}\n"
    if ticket.branch_name:
        diff_context += f"Branch: {ticket.branch_name}\n"

    # If no actual diff is available, note it in the review
    diff = diff_context or "No diff available. Review based on ticket description only."

    # Run AI review
    review_result = await review_code(
        diff=diff,
        ticket_description=ticket_desc,
        db=db,
        ticket_id=ticket_id,
    )

    # Determine decision based on findings
    critical_count = sum(1 for c in review_result.comments if c.severity == "critical")
    warning_count = sum(1 for c in review_result.comments if c.severity == "warning")

    if critical_count > 0 or warning_count > 3:
        decision = ReviewDecision.CHANGES_REQUESTED
    else:
        decision = ReviewDecision.APPROVED

    # Serialize inline comments
    inline_comments = [
        {
            "file": c.file,
            "line": c.line,
            "comment": c.comment,
            "severity": c.severity,
        }
        for c in review_result.comments
    ]

    # Persist AI review
    review = Review(
        ticket_id=ticket_id,
        reviewer_type=ReviewerType.AI_AGENT,
        agent_name="multi-agent",
        decision=decision,
        body=review_result.summary,
        inline_comments=inline_comments if inline_comments else None,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)

    result_json = review_result_to_json(review_result)

    logger.info(
        "AI review for ticket %s: decision=%s comments=%d cost=$%.4f",
        ticket_id,
        decision.value,
        len(review_result.comments),
        review_result.total_cost_usd,
    )

    return AiReviewTriggerResponse(
        review_id=review.id,
        summary=review_result.summary,
        comment_count=len(review_result.comments),
        total_cost_usd=review_result.total_cost_usd,
        agent_reviews=result_json["agent_reviews"],
    )
