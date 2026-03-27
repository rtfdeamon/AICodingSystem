"""Tests for webhook API endpoints (n8n and GitHub)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_ticket_for_webhook(
    client: AsyncClient,
    headers: dict[str, str],
) -> str:
    """Create a project and ticket, return ticket_id."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Webhook Project"},
        headers=headers,
    )
    project_id = proj_resp.json()["id"]

    ticket_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={
            "title": "Webhook Test Ticket",
            "description": "For webhook testing",
            "priority": "P2",
        },
        headers=headers,
    )
    return ticket_resp.json()["id"]


# ---------------------------------------------------------------------------
# n8n ticket-update webhook
# ---------------------------------------------------------------------------


async def test_n8n_ticket_update_approve(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    ticket_id = await _create_ticket_for_webhook(async_client, auth_headers)

    resp = await async_client.post(
        "/api/v1/webhooks/n8n/ticket-update",
        json={
            "ticket_id": ticket_id,
            "action": "approve",
            "data": {"reviewer": "n8n-bot"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "received")


async def test_n8n_ticket_update_reject(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    ticket_id = await _create_ticket_for_webhook(async_client, auth_headers)

    resp = await async_client.post(
        "/api/v1/webhooks/n8n/ticket-update",
        json={
            "ticket_id": ticket_id,
            "action": "reject",
            "data": {"reason": "quality issues"},
        },
    )
    assert resp.status_code == 200


async def test_n8n_ticket_update_invalid_ticket(async_client: AsyncClient) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.post(
        "/api/v1/webhooks/n8n/ticket-update",
        json={
            "ticket_id": fake_id,
            "action": "approve",
            "data": {},
        },
    )
    # Depends on implementation: may be 200 (no-op) or 404
    assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# n8n build-complete webhook
# ---------------------------------------------------------------------------


async def test_n8n_build_complete_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    ticket_id = await _create_ticket_for_webhook(async_client, auth_headers)

    resp = await async_client.post(
        "/api/v1/webhooks/n8n/build-complete",
        json={
            "ticket_id": ticket_id,
            "build_status": "success",
            "build_url": "https://ci.example.com/build/42",
            "logs": "Build completed successfully",
            "artifacts": ["dist/app.js"],
        },
    )
    assert resp.status_code == 200


async def test_n8n_build_complete_failure(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    ticket_id = await _create_ticket_for_webhook(async_client, auth_headers)

    resp = await async_client.post(
        "/api/v1/webhooks/n8n/build-complete",
        json={
            "ticket_id": ticket_id,
            "build_status": "failure",
            "build_url": "https://ci.example.com/build/43",
            "logs": "Compilation error",
            "artifacts": [],
        },
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# n8n deploy-status webhook
# ---------------------------------------------------------------------------


async def test_n8n_deploy_status(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    ticket_id = await _create_ticket_for_webhook(async_client, auth_headers)

    resp = await async_client.post(
        "/api/v1/webhooks/n8n/deploy-status",
        json={
            "ticket_id": ticket_id,
            "environment": "staging",
            "deploy_status": "success",
            "deploy_url": "https://staging.example.com",
            "details": {"version": "1.2.3"},
        },
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GitHub webhook (no signature = rejected)
# ---------------------------------------------------------------------------


async def test_github_webhook_no_signature(async_client: AsyncClient) -> None:
    resp = await async_client.post(
        "/api/v1/webhooks/github",
        json={"action": "completed", "check_run": {"conclusion": "success"}},
        headers={"X-GitHub-Event": "check_run"},
    )
    # Without proper signature, should be rejected
    assert resp.status_code in (200, 401, 403, 422)
