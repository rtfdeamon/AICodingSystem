"""Tests for the plan service module."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_plan import AiPlan, PlanStatus
from app.models.project import Project
from app.models.ticket import ColumnName, Priority, Ticket
from app.models.user import User
from app.services.auth_service import hash_password
from app.services.plan_service import approve_plan, get_plan, list_plans, reject_plan

pytestmark = pytest.mark.asyncio


async def _setup(db_session: AsyncSession, column: str = "plan_review") -> tuple[User, Ticket]:
    """Create user, project, and ticket."""
    user = User(
        id=uuid.uuid4(),
        email=f"plan-svc-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("password123"),
        full_name="Service Tester",
        role="pm_lead",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    project = Project(
        id=uuid.uuid4(),
        name="Plan Service Test",
        slug=f"plan-svc-{uuid.uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.flush()

    ticket = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        ticket_number=1,
        title="Test Ticket",
        column_name=ColumnName(column),
        priority=Priority.P2,
    )
    db_session.add(ticket)
    await db_session.flush()

    return user, ticket


async def _make_plan(
    db_session: AsyncSession,
    ticket_id: uuid.UUID,
    version: int = 1,
    status: PlanStatus = PlanStatus.PENDING,
) -> AiPlan:
    plan = AiPlan(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        version=version,
        agent_name="planner-agent",
        plan_markdown="# Plan",
        subtasks=[],
        file_list=[],
        status=status,
    )
    db_session.add(plan)
    await db_session.flush()
    await db_session.refresh(plan)
    return plan


async def test_list_plans_empty(db_session: AsyncSession) -> None:
    _, ticket = await _setup(db_session)
    plans = await list_plans(db_session, ticket.id)
    assert plans == []


async def test_list_plans_returns_ordered(db_session: AsyncSession) -> None:
    _, ticket = await _setup(db_session)
    await _make_plan(db_session, ticket.id, version=1)
    await _make_plan(db_session, ticket.id, version=2)
    plans = await list_plans(db_session, ticket.id)
    assert len(plans) == 2
    assert plans[0].version == 2


async def test_list_plans_ticket_not_found(db_session: AsyncSession) -> None:
    await _setup(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await list_plans(db_session, uuid.uuid4())
    assert exc_info.value.status_code == 404


async def test_get_plan_found(db_session: AsyncSession) -> None:
    _, ticket = await _setup(db_session)
    plan = await _make_plan(db_session, ticket.id)
    result = await get_plan(db_session, ticket.id, plan.id)
    assert result.id == plan.id


async def test_get_plan_not_found(db_session: AsyncSession) -> None:
    _, ticket = await _setup(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await get_plan(db_session, ticket.id, uuid.uuid4())
    assert exc_info.value.status_code == 404


async def test_approve_plan_success(db_session: AsyncSession) -> None:
    user, ticket = await _setup(db_session, column="plan_review")
    plan = await _make_plan(db_session, ticket.id)
    result = await approve_plan(db_session, ticket.id, plan.id, user.id)
    assert result.status == PlanStatus.APPROVED
    assert result.reviewed_by == user.id


async def test_approve_plan_moves_ticket(db_session: AsyncSession) -> None:
    user, ticket = await _setup(db_session, column="plan_review")
    plan = await _make_plan(db_session, ticket.id)
    await approve_plan(db_session, ticket.id, plan.id, user.id)
    await db_session.refresh(ticket)
    assert ticket.column_name == ColumnName.AI_CODING


async def test_approve_plan_already_approved(db_session: AsyncSession) -> None:
    user, ticket = await _setup(db_session)
    plan = await _make_plan(db_session, ticket.id, status=PlanStatus.APPROVED)
    with pytest.raises(HTTPException) as exc_info:
        await approve_plan(db_session, ticket.id, plan.id, user.id)
    assert exc_info.value.status_code == 409


async def test_reject_plan_success(db_session: AsyncSession) -> None:
    user, ticket = await _setup(db_session, column="plan_review")
    plan = await _make_plan(db_session, ticket.id)
    result = await reject_plan(db_session, ticket.id, plan.id, user.id, "Too broad")
    assert result.status == PlanStatus.REJECTED
    assert result.review_comment == "Too broad"


async def test_reject_plan_moves_ticket_back(db_session: AsyncSession) -> None:
    user, ticket = await _setup(db_session, column="plan_review")
    plan = await _make_plan(db_session, ticket.id)
    await reject_plan(db_session, ticket.id, plan.id, user.id, "Redo")
    await db_session.refresh(ticket)
    assert ticket.column_name == ColumnName.AI_PLANNING


async def test_reject_plan_already_rejected(db_session: AsyncSession) -> None:
    user, ticket = await _setup(db_session)
    plan = await _make_plan(db_session, ticket.id, status=PlanStatus.REJECTED)
    with pytest.raises(HTTPException) as exc_info:
        await reject_plan(db_session, ticket.id, plan.id, user.id, "Again")
    assert exc_info.value.status_code == 409
