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
from app.quality.feedback_tracker import FeedbackAction, record_feedback
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


class FindingFeedbackRequest(BaseModel):
    finding_index: int = Field(ge=0)
    action: str = Field(pattern=r"^(accepted|rejected|deferred)$")
    reason: str = ""


class FindingFeedbackResponse(BaseModel):
    review_id: uuid.UUID
    finding_index: int
    action: str
    reason: str


class AiReviewTriggerResponse(BaseModel):
    review_id: uuid.UUID
    summary: str
    comment_count: int
    total_cost_usd: float
    agent_reviews: list[dict[str, Any]]
    meta_review: dict[str, Any] | None = None


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
    from app.agents.meta_review_agent import meta_review_result_to_json, run_meta_review
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

    # Attempt to fetch real diff from GitHub
    if ticket.branch_name:
        try:
            from app.config import settings
            from app.git.github_client import GitHubClient

            token = settings.GITHUB_TOKEN
            gh = GitHubClient(access_token=token)
            real_diff = await gh.get_branch_diff(ticket.branch_name)
            if real_diff:
                diff = real_diff
        except Exception as exc:
            logger.warning("Could not fetch real diff for branch %s: %s", ticket.branch_name, exc)

    # Run AI review
    review_result = await review_code(
        diff=diff,
        ticket_description=ticket_desc,
        db=db,
        ticket_id=ticket_id,
    )

    # Layer 2: Meta-review (AI-on-AI review)
    meta_result = await run_meta_review(
        diff=diff,
        layer1_result=review_result,
        db=db,
        ticket_id=ticket_id,
    )

    # Use meta-review verdict for decision (Layer 2 overrides Layer 1 heuristics)
    verdict_map = {
        "approve": ReviewDecision.APPROVED,
        "request_changes": ReviewDecision.CHANGES_REQUESTED,
        "needs_discussion": ReviewDecision.CHANGES_REQUESTED,
    }
    decision = verdict_map.get(meta_result.verdict, ReviewDecision.CHANGES_REQUESTED)

    # Use consolidated comments from meta-review if available,
    # otherwise fall back to Layer 1 comments
    final_comments = meta_result.consolidated_comments or review_result.comments
    inline_comments = [
        {
            "file": c.file,
            "line": c.line,
            "comment": c.comment,
            "severity": c.severity,
        }
        for c in final_comments
    ]

    total_cost = review_result.total_cost_usd + meta_result.cost_usd

    # Build combined summary
    combined_summary = review_result.summary
    if meta_result.summary:
        combined_summary += f"\n\n[Meta-Review] {meta_result.summary}"
    if meta_result.missed_issues:
        combined_summary += "\n\n[Missed Issues] " + "; ".join(meta_result.missed_issues)

    # Persist AI review
    review = Review(
        ticket_id=ticket_id,
        reviewer_type=ReviewerType.AI_AGENT,
        agent_name="multi-agent-3layer",
        decision=decision,
        body=combined_summary,
        inline_comments=inline_comments if inline_comments else None,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)

    result_json = review_result_to_json(review_result)
    meta_json = meta_review_result_to_json(meta_result)

    logger.info(
        "AI review (3-layer) for ticket %s: verdict=%s confidence=%.2f "
        "comments=%d filtered=%d cost=$%.4f",
        ticket_id,
        meta_result.verdict,
        meta_result.confidence,
        len(final_comments),
        meta_result.filtered_count,
        total_cost,
    )

    return AiReviewTriggerResponse(
        review_id=review.id,
        summary=combined_summary,
        comment_count=len(final_comments),
        total_cost_usd=total_cost,
        agent_reviews=result_json["agent_reviews"],
        meta_review=meta_json,
    )


@router.post(
    "/reviews/{review_id}/feedback",
    response_model=FindingFeedbackResponse,
    status_code=201,
)
async def submit_finding_feedback(
    review_id: uuid.UUID,
    data: FindingFeedbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> FindingFeedbackResponse:
    """Submit developer feedback on an AI review finding.

    Tracks which AI findings developers accept/reject for prompt tuning.
    """
    # Verify review exists
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")

    feedback = record_feedback(
        review_id=review_id,
        finding_index=data.finding_index,
        action=FeedbackAction(data.action),
        reason=data.reason,
    )

    return FindingFeedbackResponse(
        review_id=feedback.review_id,
        finding_index=feedback.finding_index,
        action=feedback.action.value,
        reason=feedback.reason,
    )
