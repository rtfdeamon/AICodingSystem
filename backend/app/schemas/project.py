"""Pydantic schemas for Project CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    """Payload for creating a new project."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    repo_url: str | None = Field(default=None, max_length=2048)
    default_branch: str = Field(default="main", max_length=128)


class ProjectUpdate(BaseModel):
    """Payload for updating a project (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    repo_url: str | None = Field(default=None, max_length=2048)
    default_branch: str | None = Field(default=None, max_length=128)


class ProjectResponse(BaseModel):
    """Full project representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    repo_url: str | None = None
    default_branch: str
    creator_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""

    items: list[ProjectResponse]
    total: int
    page: int
    page_size: int
    pages: int
