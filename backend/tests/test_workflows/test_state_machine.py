"""Tests for state_machine — formal ticket state transitions."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import ColumnName
from app.workflows.state_machine import TicketStateMachine

sm = TicketStateMachine()


# ---------------------------------------------------------------------------
# can_transition — valid transitions
# ---------------------------------------------------------------------------


async def test_can_transition_valid(create_test_ticket):
    """backlog -> ai_planning is allowed for pm_lead with description set."""
    ticket = await create_test_ticket(column="backlog")
    ok, reason = sm.can_transition(ticket, "ai_planning", "pm_lead")
    assert ok is True
    assert reason == ""


async def test_can_transition_valid_owner(create_test_ticket):
    """backlog -> ai_planning is allowed for owner."""
    ticket = await create_test_ticket(column="backlog")
    ok, reason = sm.can_transition(ticket, "ai_planning", "owner")
    assert ok is True


# ---------------------------------------------------------------------------
# can_transition — invalid transitions
# ---------------------------------------------------------------------------


async def test_can_transition_invalid_path(create_test_ticket):
    """backlog -> production is not a valid transition path."""
    ticket = await create_test_ticket(column="backlog")
    ok, reason = sm.can_transition(ticket, "production", "pm_lead")
    assert ok is False
    assert "not allowed" in reason


async def test_can_transition_wrong_role(create_test_ticket):
    """developer cannot move tickets from backlog to ai_planning."""
    ticket = await create_test_ticket(column="backlog")
    ok, reason = sm.can_transition(ticket, "ai_planning", "developer")
    assert ok is False
    assert "developer" in reason


async def test_can_transition_production_pm_only(create_test_ticket):
    """Only pm_lead can move to production."""
    ticket = await create_test_ticket(column="staging_verification")
    ok, reason = sm.can_transition(ticket, "production", "pm_lead")
    assert ok is True

    ok, reason = sm.can_transition(ticket, "production", "owner")
    assert ok is False
    assert "owner" in reason


async def test_can_transition_prerequisite_missing(create_test_ticket):
    """backlog -> ai_planning requires description to be set."""
    ticket = await create_test_ticket(column="backlog", description="")
    ok, reason = sm.can_transition(ticket, "ai_planning", "pm_lead")
    # description is empty string, which is falsy — prerequisite not met
    assert ok is False
    assert "description" in reason


# ---------------------------------------------------------------------------
# execute_transition — valid transition
# ---------------------------------------------------------------------------


async def test_execute_transition_success(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Executes a valid transition and records history."""
    user = await create_test_user(email="pm@example.com", role="pm_lead")
    ticket = await create_test_ticket(column="backlog")

    from unittest.mock import AsyncMock, patch

    with patch(
        "app.services.n8n_service.trigger_workflow",
        new_callable=AsyncMock,
    ) as mock_trigger:
        mock_trigger.return_value = {"status": "ok"}

        result = await sm.execute_transition(
            ticket=ticket,
            to_column="ai_planning",
            actor_id=user.id,
            actor_role="pm_lead",
            db=db_session,
            comment="Starting AI planning",
        )

    assert result.column_name == ColumnName.AI_PLANNING


async def test_execute_transition_invalid_raises(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Raises ValueError for an invalid transition."""
    user = await create_test_user(email="dev@example.com", role="developer")
    ticket = await create_test_ticket(column="backlog")

    with pytest.raises(ValueError, match="developer"):
        await sm.execute_transition(
            ticket=ticket,
            to_column="ai_planning",
            actor_id=user.id,
            actor_role="developer",
            db=db_session,
        )


# ---------------------------------------------------------------------------
# execute_transition — retry count
# ---------------------------------------------------------------------------


async def test_execute_transition_increments_retry(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Retry count increments when returning to ai_coding from code_review."""
    user = await create_test_user(email="dev-retry@example.com", role="developer")
    ticket = await create_test_ticket(column="code_review")
    initial_retry = ticket.retry_count

    from unittest.mock import AsyncMock, patch

    with patch(
        "app.services.n8n_service.trigger_workflow",
        new_callable=AsyncMock,
    ):
        result = await sm.execute_transition(
            ticket=ticket,
            to_column="ai_coding",
            actor_id=user.id,
            actor_role="developer",
            db=db_session,
        )

    assert result.retry_count == initial_retry + 1


# ---------------------------------------------------------------------------
# _trigger_side_effects — coverage via execute_transition
# ---------------------------------------------------------------------------


async def test_side_effects_planning_triggered(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Triggers ai_planning workflow on backlog -> ai_planning."""
    user = await create_test_user(email="pm-side@example.com", role="pm_lead")
    ticket = await create_test_ticket(column="backlog")

    from unittest.mock import AsyncMock, patch

    with patch(
        "app.services.n8n_service.trigger_workflow",
        new_callable=AsyncMock,
    ) as mock_trigger:
        mock_trigger.return_value = {"status": "ok"}

        await sm.execute_transition(
            ticket=ticket,
            to_column="ai_planning",
            actor_id=user.id,
            actor_role="pm_lead",
            db=db_session,
        )

    mock_trigger.assert_awaited_once()
    call_args = mock_trigger.call_args
    assert call_args[0][0] == "ai_planning"


async def test_side_effects_failure_does_not_block(
    db_session: AsyncSession,
    create_test_user,
    create_test_ticket,
):
    """Side-effect failures don't block the transition."""
    user = await create_test_user(email="pm-fail@example.com", role="pm_lead")
    ticket = await create_test_ticket(column="backlog")

    from unittest.mock import AsyncMock, patch

    with patch(
        "app.services.n8n_service.trigger_workflow",
        new_callable=AsyncMock,
    ) as mock_trigger:
        mock_trigger.side_effect = Exception("n8n is down")

        result = await sm.execute_transition(
            ticket=ticket,
            to_column="ai_planning",
            actor_id=user.id,
            actor_role="pm_lead",
            db=db_session,
        )

    # Transition still went through despite side-effect failure
    assert result.column_name == ColumnName.AI_PLANNING
