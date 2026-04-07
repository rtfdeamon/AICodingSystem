"""Review schemas — request/response models for code reviews."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.models.review import Review


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
