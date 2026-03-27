"""Pydantic schemas for User CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Payload for registering a new user."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)


class UserUpdate(BaseModel):
    """Payload for updating an existing user (all fields optional)."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=2048)
    role: str | None = Field(
        default=None,
        pattern=r"^(owner|developer|pm_lead|ai_agent)$",
    )


class UserResponse(BaseModel):
    """Public representation of a user."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    avatar_url: str | None = None
    is_active: bool
    created_at: datetime


class UserInDB(UserResponse):
    """Internal representation that includes the hashed password."""

    hashed_password: str | None = None
