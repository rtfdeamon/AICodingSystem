"""AI log schemas — request/response models for AI activity logs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AILogEntry(BaseModel):
    id: str
    ticket_id: str | None = None
    agent: str
    model: str
    action: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    status: str = "success"
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AILogListResponse(BaseModel):
    items: list[AILogEntry]
    total: int
    page: int
    page_size: int


class AILogStats(BaseModel):
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    average_duration_ms: float = 0.0
    by_agent: dict[str, int] = {}
    by_model: dict[str, int] = {}
