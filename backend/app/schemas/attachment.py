"""Pydantic schemas for file attachments."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentResponse(BaseModel):
    """Public representation of a file attachment."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    uploader_id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    created_at: datetime


class AttachmentListResponse(BaseModel):
    """Paginated list of attachments."""

    items: list[AttachmentResponse]
    total: int
