"""Tests for AI Plan endpoints (list, get, approve, reject)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_plan import AiPlan, PlanStatus
from app.models.project import Project
from app.models.ticket import ColumnName, Ticket
from app.models.user import User
from app.services.auth_service import create_access_token, hash_password

pytestmark = pytest.mark.asyncio


async def _setup(
    db_session: AsyncSession,
    column: str = "plan_review",
) -> tuple[dict[str, str], str, str]:
    """Create user, project, ticket and return (headers, ticket_id, user_id)."""
    user = User(
        id=uuid.uuid4(),
        email=f"plans-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("strongpassword123"),
        full_name="Plan Tester",
        role="pm_lead",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(user.id, user.role)
    headers = {"Authorization": f"Bearer {token}"}

    project = Project(
        id=uuid.uuid4(),
        name="Plan Test Project",
        slug=f"plan-test-{uuid.uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.flush()

    ticket = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        ticket_number=1,
        title="Test Ticket for Plans",
        column_name=ColumnName(column),
    )
    db_session.add(ticket)
    await db_session.flush()

    return headers, str(ticket.id), str(user.id)


async def _create_plan(
    db_session: AsyncSession,
    ticket_id: str,
    version: int = 1,
    status: PlanStatus = PlanStatus.PENDING,
) -> AiPlan:
    """Insert a plan directly into the DB."""
    plan = AiPlan(
        id=uuid.uuid4(),
        ticket_id=uuid.UUID(ticket_id),
        version=version,
        agent_name="planner-agent",
        plan_markdown="## Plan\n\n- Step 1\n- Step 2",
        subtasks=[{"title": "Step 1", "description": "Do thing"}],
        file_list=["src/main.py"],
        status=status,
        prompt_tokens=100,
        completion_tokens=200,
        cost_usd=0.01,
        latency_ms=1500,
    )
    db_session.add(plan)
    await db_session.flush()
    await db_session.refresh(plan)
    return plan


# ── List plans ────────────────────────────────────────────────────────


async def test_list_plans_empty(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Listing plans for a ticket with none returns empty list."""
    headers, ticket_id, _ = await _setup(db_session)
    resp = await async_client.get(f"/api/v1/tickets/{ticket_id}/plans", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_plans_with_data(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Listing plans returns plans in descending version order."""
    headers, ticket_id, _ = await _setup(db_session)
    await _create_plan(db_session, ticket_id, version=1)
    await _create_plan(db_session, ticket_id, version=2)

    resp = await async_client.get(f"/api/v1/tickets/{ticket_id}/plans", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["version"] == 2
    assert data[1]["version"] == 1


async def test_list_plans_ticket_not_found(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Listing plans for a nonexistent ticket returns 404."""
    headers, _, _ = await _setup(db_session)
    fake_id = str(uuid.uuid4())
    resp = await async_client.get(f"/api/v1/tickets/{fake_id}/plans", headers=headers)
    assert resp.status_code == 404


# ── Get plan ──────────────────────────────────────────────────────────


async def test_get_plan(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Getting a plan by ID returns the plan."""
    headers, ticket_id, _ = await _setup(db_session)
    plan = await _create_plan(db_session, ticket_id)

    resp = await async_client.get(f"/api/v1/tickets/{ticket_id}/plans/{plan.id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(plan.id)
    assert data["plan_markdown"] == "## Plan\n\n- Step 1\n- Step 2"
    assert data["status"] == "pending"


async def test_get_plan_not_found(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Getting a nonexistent plan returns 404."""
    headers, ticket_id, _ = await _setup(db_session)
    fake_id = str(uuid.uuid4())
    resp = await async_client.get(f"/api/v1/tickets/{ticket_id}/plans/{fake_id}", headers=headers)
    assert resp.status_code == 404


# ── Approve plan ──────────────────────────────────────────────────────


async def test_approve_plan(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Approving a pending plan sets status to approved."""
    headers, ticket_id, user_id = await _setup(db_session, column="plan_review")
    plan = await _create_plan(db_session, ticket_id)

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/plans/{plan.id}/approve",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["reviewed_by"] == user_id


async def test_approve_plan_already_approved(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Approving an already-approved plan returns 409."""
    headers, ticket_id, _ = await _setup(db_session)
    plan = await _create_plan(db_session, ticket_id, status=PlanStatus.APPROVED)

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/plans/{plan.id}/approve",
        headers=headers,
    )
    assert resp.status_code == 409


async def test_approve_plan_moves_ticket(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Approving a plan when ticket is in plan_review moves it to ai_coding."""
    headers, ticket_id, _ = await _setup(db_session, column="plan_review")
    plan = await _create_plan(db_session, ticket_id)

    await async_client.post(
        f"/api/v1/tickets/{ticket_id}/plans/{plan.id}/approve",
        headers=headers,
    )

    # Verify ticket moved
    resp = await async_client.get(f"/api/v1/tickets/{ticket_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["column_name"] == "ai_coding"


# ── Reject plan ───────────────────────────────────────────────────────


async def test_reject_plan(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Rejecting a pending plan sets status to rejected with comment."""
    headers, ticket_id, user_id = await _setup(db_session, column="plan_review")
    plan = await _create_plan(db_session, ticket_id)

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/plans/{plan.id}/reject",
        json={"comment": "Needs more detail on error handling."},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["review_comment"] == "Needs more detail on error handling."
    assert data["reviewed_by"] == user_id


async def test_reject_plan_moves_ticket_back(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Rejecting a plan when ticket is in plan_review moves it back to ai_planning."""
    headers, ticket_id, _ = await _setup(db_session, column="plan_review")
    plan = await _create_plan(db_session, ticket_id)

    await async_client.post(
        f"/api/v1/tickets/{ticket_id}/plans/{plan.id}/reject",
        json={"comment": "Plan is too broad."},
        headers=headers,
    )

    resp = await async_client.get(f"/api/v1/tickets/{ticket_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["column_name"] == "ai_planning"


async def test_reject_plan_requires_comment(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Rejecting a plan without a comment returns 422."""
    headers, ticket_id, _ = await _setup(db_session)
    plan = await _create_plan(db_session, ticket_id)

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/plans/{plan.id}/reject",
        json={},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_reject_plan_already_rejected(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Rejecting an already-rejected plan returns 409."""
    headers, ticket_id, _ = await _setup(db_session)
    plan = await _create_plan(db_session, ticket_id, status=PlanStatus.REJECTED)

    resp = await async_client.post(
        f"/api/v1/tickets/{ticket_id}/plans/{plan.id}/reject",
        json={"comment": "Try again."},
        headers=headers,
    )
    assert resp.status_code == 409


# ── Auth ──────────────────────────────────────────────────────────────


async def test_plans_require_auth(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Plan endpoints require authentication."""
    fake_id = str(uuid.uuid4())
    resp = await async_client.get(f"/api/v1/tickets/{fake_id}/plans")
    assert resp.status_code in (401, 403)
