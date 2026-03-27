"""Pydantic schemas for AI Plan CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanRejectRequest(BaseModel):
    """Payload for rejecting a plan — comment is required."""

    comment: str = Field(min_length=1, max_length=10_000)


class PlanResponse(BaseModel):
    """Public representation of an AI plan."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    version: int
    agent_name: str
    plan_markdown: str
    subtasks: list[dict[str, Any]]
    file_list: list[str]
    status: str
    review_comment: str | None = None
    reviewed_by: uuid.UUID | None = None
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    created_at: datetime
