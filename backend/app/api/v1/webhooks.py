"""Webhook receiver endpoints for n8n and GitHub integrations."""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.ticket import ColumnName, Ticket

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared schemas for webhook payloads
# ---------------------------------------------------------------------------


class N8NTicketUpdatePayload(BaseModel):
    """Payload received from n8n when a ticket is updated externally."""

    ticket_id: str
    action: str
    data: dict[str, Any] = {}


class N8NBuildCompletePayload(BaseModel):
    """Payload received from n8n when a build completes."""

    ticket_id: str
    build_status: str  # success, failure
    build_url: str | None = None
    logs: str | None = None
    artifacts: list[str] = []


class N8NDeployStatusPayload(BaseModel):
    """Payload received from n8n with deployment status."""

    ticket_id: str
    environment: str  # staging, production
    deploy_status: str  # success, failure, rollback
    deploy_url: str | None = None
    details: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# n8n webhook receivers
# ---------------------------------------------------------------------------


@router.post("/webhooks/n8n/ticket-update")
async def n8n_ticket_update(
    payload: N8NTicketUpdatePayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Receive ticket update events from n8n workflows.

    Processes the update and triggers board state changes based on action.
    """
    logger.info(
        "n8n ticket-update webhook: ticket=%s action=%s",
        payload.ticket_id,
        payload.action,
    )

    ticket = await _get_ticket_or_none(db, payload.ticket_id)
    if ticket and payload.action in _ACTION_COLUMN_MAP:
        ticket.column_name = _ACTION_COLUMN_MAP[payload.action]
        await db.commit()
        logger.info(
            "Ticket %s moved to %s via webhook action=%s",
            payload.ticket_id,
            ticket.column_name.value,
            payload.action,
        )

    return {"status": "received", "ticket_id": payload.ticket_id}


@router.post("/webhooks/n8n/build-complete")
async def n8n_build_complete(
    payload: N8NBuildCompletePayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Receive build completion events from the CI/CD pipeline via n8n."""
    logger.info(
        "n8n build-complete webhook: ticket=%s status=%s",
        payload.ticket_id,
        payload.build_status,
    )

    ticket = await _get_ticket_or_none(db, payload.ticket_id)
    if ticket:
        if payload.build_status == "success":
            ticket.column_name = ColumnName.STAGING
        elif payload.build_status == "failure":
            ticket.column_name = ColumnName.AI_CODING
            ticket.retry_count = (ticket.retry_count or 0) + 1
        await db.commit()
        logger.info(
            "Ticket %s moved to %s after build %s",
            payload.ticket_id,
            ticket.column_name.value,
            payload.build_status,
        )

    return {"status": "received", "ticket_id": payload.ticket_id}


@router.post("/webhooks/n8n/deploy-status")
async def n8n_deploy_status(
    payload: N8NDeployStatusPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Receive deployment status updates from n8n."""
    logger.info(
        "n8n deploy-status webhook: ticket=%s env=%s status=%s",
        payload.ticket_id,
        payload.environment,
        payload.deploy_status,
    )

    ticket = await _get_ticket_or_none(db, payload.ticket_id)
    if ticket:
        if payload.deploy_status == "success":
            if payload.environment == "production":
                ticket.column_name = ColumnName.PRODUCTION
            else:
                ticket.column_name = ColumnName.STAGING_VERIFICATION
        elif payload.deploy_status in ("failure", "rollback"):
            ticket.column_name = ColumnName.STAGING
        await db.commit()
        logger.info(
            "Ticket %s moved to %s after deploy %s (%s)",
            payload.ticket_id,
            ticket.column_name.value,
            payload.deploy_status,
            payload.environment,
        )

    return {"status": "received", "ticket_id": payload.ticket_id}


# ---------------------------------------------------------------------------
# GitHub webhook receiver
# ---------------------------------------------------------------------------


async def _verify_github_signature(request: Request, signature: str | None) -> None:
    """Verify the ``X-Hub-Signature-256`` header from GitHub."""
    secret = settings.GITHUB_CLIENT_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook signature verification unavailable: secret not configured.",
        )
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header.",
        )

    body = await request.body()
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub webhook signature.",
        )


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Receive and process GitHub webhook events.

    Supports ``push``, ``pull_request``, and ``check_run`` events.
    """
    await _verify_github_signature(request, x_hub_signature_256)

    body = await request.json()
    event_type = x_github_event or "unknown"

    logger.info("GitHub webhook received: event=%s", event_type)

    if event_type == "push":
        ref = body.get("ref", "")
        logger.info("GitHub push to %s", ref)
    elif event_type == "pull_request":
        action = body.get("action", "")
        pr_number = body.get("number", "?")
        logger.info("GitHub PR #%s action=%s", pr_number, action)
    elif event_type == "check_run":
        conclusion = body.get("check_run", {}).get("conclusion", "")
        logger.info("GitHub check_run conclusion=%s", conclusion)
    else:
        logger.debug("Unhandled GitHub event type: %s", event_type)

    return {"status": "received", "event": event_type}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Map n8n ticket-update actions to target kanban columns
_ACTION_COLUMN_MAP: dict[str, ColumnName] = {
    "approve_plan": ColumnName.AI_CODING,
    "reject_plan": ColumnName.BACKLOG,
    "approve_code": ColumnName.STAGING,
    "reject_code": ColumnName.AI_CODING,
    "approve_staging": ColumnName.STAGING_VERIFICATION,
    "approve_production": ColumnName.PRODUCTION,
}


async def _get_ticket_or_none(
    db: AsyncSession,
    ticket_id_str: str,
) -> Ticket | None:
    """Resolve a ticket by its string ID, returning None on failure."""
    try:
        tid = uuid.UUID(ticket_id_str)
    except ValueError:
        logger.warning("Invalid ticket_id in webhook: %s", ticket_id_str)
        return None
    result = await db.execute(select(Ticket).where(Ticket.id == tid))
    return result.scalar_one_or_none()
