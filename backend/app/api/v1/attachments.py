"""File attachment endpoints for tickets."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.attachment import Attachment
from app.models.user import User
from app.schemas.attachment import AttachmentListResponse, AttachmentResponse

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

UPLOADS_DIR = Path("uploads")


@router.post(
    "/tickets/{ticket_id}/attachments",
    response_model=AttachmentResponse,
    status_code=201,
)
async def upload_attachment(
    ticket_id: uuid.UUID,
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AttachmentResponse:
    """Upload a file attachment to a ticket (max 10 MB)."""
    # Read file content and enforce size limit
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    raw_filename = file.filename or "unnamed"
    # Sanitize filename to prevent path traversal attacks
    filename = Path(raw_filename).name.replace("\x00", "")
    if not filename or filename in (".", ".."):
        filename = "unnamed"
    file_id = uuid.uuid4()
    safe_filename = f"{file_id}_{filename}"

    # Ensure upload directory exists
    ticket_dir = UPLOADS_DIR / str(ticket_id)
    ticket_dir.mkdir(parents=True, exist_ok=True)

    storage_path = ticket_dir / safe_filename

    # Write file to disk
    storage_path.write_bytes(content)

    attachment = Attachment(
        id=file_id,
        ticket_id=ticket_id,
        uploader_id=current_user.id,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        file_size=len(content),
        storage_path=str(storage_path),
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    logger.info(
        "Attachment %s uploaded for ticket %s by user %s",
        file_id,
        ticket_id,
        current_user.id,
    )
    return AttachmentResponse.model_validate(attachment)


@router.get(
    "/tickets/{ticket_id}/attachments",
    response_model=AttachmentListResponse,
)
async def list_attachments(
    ticket_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> AttachmentListResponse:
    """List all attachments for a ticket."""
    count_result = await db.execute(select(func.count()).where(Attachment.ticket_id == ticket_id))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Attachment)
        .where(Attachment.ticket_id == ticket_id)
        .order_by(Attachment.created_at.desc())
    )
    attachments = result.scalars().all()

    return AttachmentListResponse(
        items=[AttachmentResponse.model_validate(a) for a in attachments],
        total=total,
    )


@router.get(
    "/attachments/{attachment_id}/download",
)
async def download_attachment(
    attachment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    """Download an attachment file."""
    result = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found.",
        )

    if not os.path.exists(attachment.storage_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk.",
        )

    return FileResponse(
        path=attachment.storage_path,
        filename=attachment.filename,
        media_type=attachment.content_type,
    )


@router.delete(
    "/attachments/{attachment_id}",
    status_code=204,
)
async def delete_attachment(
    attachment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Delete an attachment. Only the uploader or a project owner may delete."""
    result = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found.",
        )

    # Only uploader or owner role can delete
    if attachment.uploader_id != current_user.id and current_user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the uploader or an owner can delete this attachment.",
        )

    # Remove file from disk
    try:
        os.remove(attachment.storage_path)
    except OSError:
        logger.warning("Could not remove file at %s", attachment.storage_path)

    await db.delete(attachment)
    await db.commit()
    logger.info("Attachment %s deleted by user %s", attachment_id, current_user.id)
