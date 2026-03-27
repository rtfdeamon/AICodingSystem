"""Tests for app.api.v1.ai_logs — log listing, stats, and single entry."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AiLog, AiLogStatus

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_ai_log(
    db_session: AsyncSession,
    *,
    agent_name: str = "claude",
    action_type: str = "planning",
    model_id: str = "claude-opus-4-6",
    ticket_id: uuid.UUID | None = None,
    prompt_tokens: int = 100,
    completion_tokens: int = 200,
    cost_usd: float = 0.01,
    latency_ms: int = 500,
    status: AiLogStatus = AiLogStatus.SUCCESS,
) -> AiLog:
    log = AiLog(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        agent_name=agent_name,
        action_type=action_type,
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        status=status,
    )
    db_session.add(log)
    await db_session.flush()
    await db_session.refresh(log)
    return log


# ---------------------------------------------------------------------------
# List AI logs
# ---------------------------------------------------------------------------


async def test_list_ai_logs_empty(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await async_client.get("/api/v1/ai-logs", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_ai_logs_with_data(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    await _create_ai_log(db_session)
    await _create_ai_log(db_session, agent_name="codex", action_type="coding")

    resp = await async_client.get("/api/v1/ai-logs", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


async def test_list_ai_logs_filter_by_agent(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    await _create_ai_log(db_session, agent_name="claude")
    await _create_ai_log(db_session, agent_name="codex")

    resp = await async_client.get("/api/v1/ai-logs?agent=claude", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["agent"] == "claude"


async def test_list_ai_logs_filter_by_status(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    await _create_ai_log(db_session, status=AiLogStatus.SUCCESS)
    await _create_ai_log(db_session, status=AiLogStatus.ERROR)

    resp = await async_client.get("/api/v1/ai-logs?status=error", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "error"


async def test_list_ai_logs_pagination(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    for i in range(5):
        await _create_ai_log(db_session, agent_name=f"agent-{i}")

    resp = await async_client.get("/api/v1/ai-logs?page=1&per_page=2", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


async def test_list_ai_logs_requires_auth(async_client: AsyncClient) -> None:
    resp = await async_client.get("/api/v1/ai-logs")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Get single AI log
# ---------------------------------------------------------------------------


async def test_get_ai_log(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    log = await _create_ai_log(db_session)
    resp = await async_client.get(f"/api/v1/ai-logs/{log.id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(log.id)
    assert body["agent"] == "claude"


async def test_get_ai_log_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake_id = uuid.uuid4()
    resp = await async_client.get(f"/api/v1/ai-logs/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AI log stats
# ---------------------------------------------------------------------------


async def test_ai_log_stats_empty(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await async_client.get("/api/v1/ai-logs/stats", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_requests"] == 0
    assert body["total_cost_usd"] == 0.0


async def test_ai_log_stats_with_data(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    await _create_ai_log(
        db_session,
        agent_name="claude",
        cost_usd=0.05,
        prompt_tokens=100,
        completion_tokens=200,
        latency_ms=500,
    )
    await _create_ai_log(
        db_session,
        agent_name="codex",
        cost_usd=0.03,
        prompt_tokens=50,
        completion_tokens=100,
        latency_ms=300,
    )

    resp = await async_client.get("/api/v1/ai-logs/stats", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_requests"] == 2
    assert body["total_cost_usd"] == pytest.approx(0.08)
    assert body["total_input_tokens"] == 150
    assert body["total_output_tokens"] == 300
    assert body["average_duration_ms"] == 400.0
    assert "claude" in body["by_agent"]
    assert "codex" in body["by_agent"]
