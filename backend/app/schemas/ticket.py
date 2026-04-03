"""Pydantic schemas for Ticket CRUD and board operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TicketCreate(BaseModel):
    """Payload for creating a new ticket."""

    title: str = Field(min_length=1, max_length=512)
    description: str | None = None
    acceptance_criteria: str | None = None
    business_task: str | None = None
    decomposed_task: str | None = None
    coding_task: str | None = None
    ai_prompt: str | None = None
    priority: str = Field(default="P2", pattern=r"^P[0-3]$")
    labels: list[str] | None = None


class TicketUpdate(BaseModel):
    """Payload for updating a ticket (all fields optional)."""

    title: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = None
    acceptance_criteria: str | None = None
    business_task: str | None = None
    decomposed_task: str | None = None
    coding_task: str | None = None
    ai_prompt: str | None = None
    priority: str | None = Field(default=None, pattern=r"^P[0-3]$")
    assignee_id: uuid.UUID | None = None
    labels: list[str] | None = None
    story_points: int | None = Field(default=None, ge=0, le=100)


class TicketMoveRequest(BaseModel):
    """Request to move a ticket to another Kanban column."""

    to_column: str = Field(
        ...,
        pattern=(
            r"^(backlog|ai_planning|plan_review|ai_coding|"
            r"code_review|staging|staging_verification|production)$"
        ),
    )
    comment: str | None = None


class TicketResponse(BaseModel):
    """Full ticket representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    ticket_number: int
    title: str
    description: str | None = None
    acceptance_criteria: str | None = None
    business_task: str | None = None
    decomposed_task: str | None = None
    coding_task: str | None = None
    ai_prompt: str | None = None
    priority: str
    column_name: str
    assignee_id: uuid.UUID | None = None
    reporter_id: uuid.UUID | None = None
    story_points: int | None = None
    labels: list[str] | None = None
    branch_name: str | None = None
    pr_url: str | None = None
    retry_count: int = 0
    position: int = 0
    created_at: datetime
    updated_at: datetime


class TicketListResponse(BaseModel):
    """Paginated list of tickets."""

    items: list[TicketResponse]
    total: int
    page: int
    page_size: int
    pages: int
