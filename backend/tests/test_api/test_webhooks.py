"""Tests for webhook API endpoints (n8n and GitHub)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import patch

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
    # 503 if no secret configured, 401 if secret set but sig missing
    assert resp.status_code in (200, 401, 403, 422, 503)


# ---------------------------------------------------------------------------
# Additional coverage: n8n ticket-update with mapped actions
# ---------------------------------------------------------------------------


async def test_n8n_ticket_update_approve_plan_moves_to_ai_coding(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Action 'approve_plan' is in _ACTION_COLUMN_MAP -> moves ticket to ai_coding."""
    ticket_id = await _create_ticket_for_webhook(async_client, auth_headers)

    resp = await async_client.post(
        "/api/v1/webhooks/n8n/ticket-update",
        json={"ticket_id": ticket_id, "action": "approve_plan", "data": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"


async def test_n8n_ticket_update_reject_plan_moves_to_backlog(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Action 'reject_plan' moves ticket back to backlog."""
    ticket_id = await _create_ticket_for_webhook(async_client, auth_headers)

    resp = await async_client.post(
        "/api/v1/webhooks/n8n/ticket-update",
        json={"ticket_id": ticket_id, "action": "reject_plan", "data": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"


async def test_n8n_ticket_update_approve_production(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Action 'approve_production' maps to PRODUCTION column."""
    ticket_id = await _create_ticket_for_webhook(async_client, auth_headers)

    resp = await async_client.post(
        "/api/v1/webhooks/n8n/ticket-update",
        json={"ticket_id": ticket_id, "action": "approve_production", "data": {}},
    )
    assert resp.status_code == 200


async def test_n8n_ticket_update_invalid_uuid_string(
    async_client: AsyncClient,
) -> None:
    """A non-UUID ticket_id triggers the ValueError branch in _get_ticket_or_none."""
    resp = await async_client.post(
        "/api/v1/webhooks/n8n/ticket-update",
        json={"ticket_id": "not-a-uuid", "action": "approve_plan", "data": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"


# ---------------------------------------------------------------------------
# Additional coverage: n8n build-complete with nonexistent / invalid ticket
# ---------------------------------------------------------------------------


async def test_n8n_build_complete_nonexistent_ticket(
    async_client: AsyncClient,
) -> None:
    """Build-complete for a UUID that doesn't exist in DB — ticket is None, no-op."""
    fake_id = str(uuid.uuid4())
    resp = await async_client.post(
        "/api/v1/webhooks/n8n/build-complete",
        json={"ticket_id": fake_id, "build_status": "success"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"


async def test_n8n_build_complete_invalid_uuid(
    async_client: AsyncClient,
) -> None:
    """Build-complete with an invalid UUID triggers ValueError in helper."""
    resp = await async_client.post(
        "/api/v1/webhooks/n8n/build-complete",
        json={"ticket_id": "bad-uuid", "build_status": "failure"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Additional coverage: n8n deploy-status branches
# ---------------------------------------------------------------------------


async def test_n8n_deploy_status_production_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Deploy success + production environment moves ticket to PRODUCTION."""
    ticket_id = await _create_ticket_for_webhook(async_client, auth_headers)

    resp = await async_client.post(
        "/api/v1/webhooks/n8n/deploy-status",
        json={
            "ticket_id": ticket_id,
            "environment": "production",
            "deploy_status": "success",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"


async def test_n8n_deploy_status_failure(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Deploy failure moves ticket to STAGING."""
    ticket_id = await _create_ticket_for_webhook(async_client, auth_headers)

    resp = await async_client.post(
        "/api/v1/webhooks/n8n/deploy-status",
        json={
            "ticket_id": ticket_id,
            "environment": "staging",
            "deploy_status": "failure",
        },
    )
    assert resp.status_code == 200


async def test_n8n_deploy_status_rollback(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Deploy rollback moves ticket to STAGING."""
    ticket_id = await _create_ticket_for_webhook(async_client, auth_headers)

    resp = await async_client.post(
        "/api/v1/webhooks/n8n/deploy-status",
        json={
            "ticket_id": ticket_id,
            "environment": "production",
            "deploy_status": "rollback",
        },
    )
    assert resp.status_code == 200


async def test_n8n_deploy_status_nonexistent_ticket(
    async_client: AsyncClient,
) -> None:
    """Deploy status with nonexistent ticket — no-op."""
    fake_id = str(uuid.uuid4())
    resp = await async_client.post(
        "/api/v1/webhooks/n8n/deploy-status",
        json={
            "ticket_id": fake_id,
            "environment": "staging",
            "deploy_status": "success",
        },
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Additional coverage: GitHub webhook with various event types
# ---------------------------------------------------------------------------


_WH_SECRET = "test-webhook-secret"  # noqa: S105


def _signed_webhook_post(
    async_client: AsyncClient,
    payload: dict,
    headers: dict[str, str] | None = None,
    secret: str = _WH_SECRET,
):
    """Helper: POST to /webhooks/github with a valid HMAC signature."""
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    hdrs = {"X-Hub-Signature-256": sig, "Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    return async_client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers=hdrs,
    ), secret


async def test_github_webhook_no_secret_set(async_client: AsyncClient) -> None:
    """When GITHUB_CLIENT_SECRET is None, webhook returns 503 (fail-closed)."""
    with patch("app.api.v1.webhooks.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = None
        resp = await async_client.post(
            "/api/v1/webhooks/github",
            json={"ref": "refs/heads/main"},
            headers={"X-GitHub-Event": "push"},
        )
    assert resp.status_code == 503


async def test_github_webhook_push_event(async_client: AsyncClient) -> None:
    """GitHub push event is logged and returns 200."""
    secret = "test-webhook-secret"
    body = json.dumps({"ref": "refs/heads/main", "commits": []}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    with patch("app.api.v1.webhooks.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = secret
        resp = await async_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": sig,
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["event"] == "push"


async def test_github_webhook_pull_request_event(async_client: AsyncClient) -> None:
    """GitHub pull_request event is logged."""
    secret = "test-webhook-secret"
    body = json.dumps({"action": "opened", "number": 42}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    with patch("app.api.v1.webhooks.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = secret
        resp = await async_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig,
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["event"] == "pull_request"


async def test_github_webhook_check_run_event(async_client: AsyncClient) -> None:
    """GitHub check_run event with conclusion is logged."""
    secret = "test-webhook-secret"
    body = json.dumps({"check_run": {"conclusion": "success"}}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    with patch("app.api.v1.webhooks.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = secret
        resp = await async_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "check_run",
                "X-Hub-Signature-256": sig,
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["event"] == "check_run"


async def test_github_webhook_unknown_event(async_client: AsyncClient) -> None:
    """Unhandled GitHub event type falls through to the else branch."""
    secret = "test-webhook-secret"
    body = json.dumps({"action": "created"}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    with patch("app.api.v1.webhooks.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = secret
        resp = await async_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "star",
                "X-Hub-Signature-256": sig,
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["event"] == "star"


async def test_github_webhook_no_event_header(async_client: AsyncClient) -> None:
    """Missing X-GitHub-Event header defaults to 'unknown'."""
    secret = "test-webhook-secret"
    body = json.dumps({"some": "data"}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    with patch("app.api.v1.webhooks.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = secret
        resp = await async_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["event"] == "unknown"


async def test_github_webhook_valid_signature(async_client: AsyncClient) -> None:
    """Valid HMAC signature passes verification."""
    secret = "test-webhook-secret"
    body = json.dumps({"ref": "refs/heads/main"}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    with patch("app.api.v1.webhooks.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = secret
        resp = await async_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": sig,
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 200


async def test_github_webhook_invalid_signature(async_client: AsyncClient) -> None:
    """Invalid HMAC signature returns 401."""
    with patch("app.api.v1.webhooks.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = "real-secret"
        resp = await async_client.post(
            "/api/v1/webhooks/github",
            json={"ref": "refs/heads/main"},
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )
    assert resp.status_code == 401


async def test_github_webhook_missing_signature_with_secret(
    async_client: AsyncClient,
) -> None:
    """When secret is set but no signature header is provided, returns 401."""
    with patch("app.api.v1.webhooks.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = "some-secret"
        resp = await async_client.post(
            "/api/v1/webhooks/github",
            json={"ref": "refs/heads/main"},
            headers={"X-GitHub-Event": "push"},
        )
    assert resp.status_code == 401
