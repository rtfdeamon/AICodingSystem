"""Tests for app.api.v1.reviews — review CRUD and AI trigger."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_project_and_ticket(
    client: AsyncClient,
    headers: dict,
    column: str = "code_review",
) -> tuple[str, str]:
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Review Test Proj"},
        headers=headers,
    )
    project_id = proj_resp.json()["id"]

    ticket_resp = await client.post(
        f"/api/v1/projects/{project_id}/tickets",
        json={
            "title": "Review ticket",
            "description": "Needs review",
            "priority": "P1",
        },
        headers=headers,
    )
    return project_id, ticket_resp.json()["id"]


# ---------------------------------------------------------------------------
# List reviews
# ---------------------------------------------------------------------------


async def test_list_reviews_empty(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)
    resp = await async_client.get(
        f"/api/v1/tickets/{ticket_id}/reviews",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Submit human review
# ---------------------------------------------------------------------------


async def test_submit_review_approved(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)
    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/reviews",
        json={
            "decision": "approved",
            "body": "Looks good!",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "approved"
    assert data["body"] == "Looks good!"
    assert data["reviewer_type"] == "user"


async def test_submit_review_changes_requested(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)
    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/reviews",
        json={
            "decision": "changes_requested",
            "body": "Fix the bug",
            "inline_comments": [
                {
                    "file": "main.py",
                    "line": 10,
                    "comment": "This needs refactoring",
                    "severity": "warning",
                }
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["decision"] == "changes_requested"
    assert data["inline_comments"] is not None
    assert len(data["inline_comments"]) == 1


async def test_submit_review_rejected(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)
    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/reviews",
        json={"decision": "rejected", "body": "Not acceptable"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["decision"] == "rejected"


async def test_submit_review_ticket_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/tickets/{fake_id}/reviews",
        json={"decision": "approved"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_submit_review_requires_auth(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)
    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/reviews",
        json={"decision": "approved"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# AI review trigger
# ---------------------------------------------------------------------------


async def test_trigger_ai_review(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Trigger AI review with mocked review_code."""
    _, ticket_id = await _create_project_and_ticket(async_client, auth_headers)

    from dataclasses import dataclass, field

    @dataclass
    class FakeComment:
        file: str = "main.py"
        line: int = 1
        comment: str = "Looks fine"
        severity: str = "suggestion"

    @dataclass
    class FakeReviewResult:
        summary: str = "All good"
        comments: list = field(default_factory=lambda: [FakeComment()])
        total_cost_usd: float = 0.01
        agent_reviews: list = field(default_factory=list)

    fake_result = FakeReviewResult()

    @dataclass
    class FakeMetaResult:
        verdict: str = "approve"
        confidence: float = 0.9
        consolidated_comments: list = field(default_factory=list)
        filtered_count: int = 0
        missed_issues: list = field(default_factory=list)
        summary: str = ""
        cost_usd: float = 0.0
        latency_ms: int = 0

    fake_meta = FakeMetaResult()

    with (
        patch(
            "app.agents.review_agent.review_code",
            new_callable=AsyncMock,
            return_value=fake_result,
        ),
        patch(
            "app.agents.review_agent.review_result_to_json",
            return_value={"agent_reviews": [{"agent": "test", "summary": "ok"}]},
        ),
        patch(
            "app.agents.meta_review_agent.run_meta_review",
            new_callable=AsyncMock,
            return_value=fake_meta,
        ),
        patch(
            "app.agents.meta_review_agent.meta_review_result_to_json",
            return_value={"verdict": "approve", "confidence": 0.9},
        ),
    ):
        resp = await async_client.post(
            f"/api/v1/tickets/{ticket_id}/reviews/ai-trigger",
            headers=auth_headers,
        )

    assert resp.status_code == 201
    data = resp.json()
    assert "All good" in data["summary"]
    assert data["comment_count"] == 1
    assert data["total_cost_usd"] == 0.01


async def test_trigger_ai_review_ticket_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/tickets/{fake_id}/reviews/ai-trigger",
        headers=auth_headers,
    )
    assert resp.status_code == 404
