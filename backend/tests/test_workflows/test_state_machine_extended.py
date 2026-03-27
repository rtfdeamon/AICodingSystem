"""Comprehensive tests for state_machine — TicketStateMachine transitions and side effects."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import ColumnName, Priority, Ticket
from app.models.ticket_history import TicketHistory
from app.workflows.state_machine import TicketStateMachine

# NOTE: Only async test methods use @pytest.mark.asyncio (via asyncio_mode=auto).
# Do NOT use module-level pytestmark to avoid warnings on sync tests.

sm = TicketStateMachine()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticket(
    column: str,
    description: str | None = "some description",
    branch_name: str | None = None,
    retry_count: int = 0,
    title: str = "Test Ticket",
    acceptance_criteria: str | None = "AC here",
) -> Ticket:
    """Create a minimal Ticket for validation tests."""
    return Ticket(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        ticket_number=1,
        title=title,
        description=description,
        acceptance_criteria=acceptance_criteria,
        column_name=ColumnName(column),
        priority=Priority.P2,
        retry_count=retry_count,
        position=0,
        branch_name=branch_name,
    )


# ===================================================================
# can_transition — all 10 valid transition rules
# ===================================================================


class TestCanTransitionAllValid:
    """Verify all 10 defined transition rules are accepted."""

    def test_backlog_to_ai_planning(self) -> None:
        ticket = _make_ticket("backlog")
        ok, reason = sm.can_transition(ticket, "ai_planning", "owner")
        assert ok is True
        assert reason == ""

    def test_ai_planning_to_plan_review(self) -> None:
        ticket = _make_ticket("ai_planning")
        ok, _ = sm.can_transition(ticket, "plan_review", "ai_agent")
        assert ok is True

    def test_plan_review_to_ai_coding(self) -> None:
        ticket = _make_ticket("plan_review")
        ok, _ = sm.can_transition(ticket, "ai_coding", "developer")
        assert ok is True

    def test_plan_review_to_backlog(self) -> None:
        ticket = _make_ticket("plan_review")
        ok, _ = sm.can_transition(ticket, "backlog", "developer")
        assert ok is True

    def test_ai_coding_to_code_review(self) -> None:
        ticket = _make_ticket("ai_coding")
        ok, _ = sm.can_transition(ticket, "code_review", "ai_agent")
        assert ok is True

    def test_code_review_to_staging(self) -> None:
        ticket = _make_ticket("code_review")
        ok, _ = sm.can_transition(ticket, "staging", "developer")
        assert ok is True

    def test_code_review_to_ai_coding(self) -> None:
        ticket = _make_ticket("code_review")
        ok, _ = sm.can_transition(ticket, "ai_coding", "developer")
        assert ok is True

    def test_staging_to_staging_verification(self) -> None:
        ticket = _make_ticket("staging")
        ok, _ = sm.can_transition(ticket, "staging_verification", "ai_agent")
        assert ok is True

    def test_staging_verification_to_production(self) -> None:
        ticket = _make_ticket("staging_verification")
        ok, _ = sm.can_transition(ticket, "production", "pm_lead")
        assert ok is True

    def test_staging_verification_to_ai_coding(self) -> None:
        ticket = _make_ticket("staging_verification")
        ok, _ = sm.can_transition(ticket, "ai_coding", "developer")
        assert ok is True


# ===================================================================
# can_transition — invalid cases
# ===================================================================


class TestCanTransitionInvalid:
    """Invalid transition checks."""

    def test_invalid_transition_returns_false_with_reason(self) -> None:
        ticket = _make_ticket("backlog")
        ok, reason = sm.can_transition(ticket, "production", "owner")
        assert ok is False
        assert "not allowed" in reason

    def test_wrong_role_returns_false_with_reason(self) -> None:
        ticket = _make_ticket("backlog")
        ok, reason = sm.can_transition(ticket, "ai_planning", "developer")
        assert ok is False
        assert "developer" in reason
        assert "Role" in reason or "role" in reason.lower()

    def test_prerequisite_not_met_returns_false(self) -> None:
        ticket = _make_ticket("backlog", description=None)
        ok, reason = sm.can_transition(ticket, "ai_planning", "owner")
        assert ok is False
        assert "description" in reason

    def test_empty_description_prerequisite(self) -> None:
        ticket = _make_ticket("backlog", description="")
        ok, reason = sm.can_transition(ticket, "ai_planning", "pm_lead")
        assert ok is False
        assert "description" in reason

    def test_column_name_as_enum_works(self) -> None:
        """ColumnName enum should resolve correctly in can_transition."""
        ticket = _make_ticket("backlog")
        assert isinstance(ticket.column_name, ColumnName)
        ok, _ = sm.can_transition(ticket, "ai_planning", "owner")
        assert ok is True

    def test_column_name_as_string_works(self) -> None:
        """Raw string column_name should also resolve."""
        ticket = _make_ticket("backlog")
        object.__setattr__(ticket, "column_name", "backlog")
        ok, _ = sm.can_transition(ticket, "ai_planning", "owner")
        assert ok is True


# ===================================================================
# execute_transition — successful cases
# ===================================================================


class TestExecuteTransitionSuccess:
    """Successful transition execution."""

    async def test_updates_column_and_position(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="exec-ok@example.com", role="pm_lead")
        ticket = await create_test_ticket(column="backlog")

        with patch(
            "app.services.n8n_service.trigger_workflow",
            new_callable=AsyncMock,
        ):
            result = await sm.execute_transition(
                ticket=ticket,
                to_column="ai_planning",
                actor_id=user.id,
                actor_role="pm_lead",
                db=db_session,
            )

        assert result.column_name == ColumnName.AI_PLANNING
        assert result.position == 0

    async def test_invalid_transition_raises_value_error(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="exec-bad@example.com", role="developer")
        ticket = await create_test_ticket(column="backlog")

        with pytest.raises(ValueError, match="developer"):
            await sm.execute_transition(
                ticket=ticket,
                to_column="ai_planning",
                actor_id=user.id,
                actor_role="developer",
                db=db_session,
            )

    async def test_actor_type_system_for_ai_agent(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        """ai_agent role should create history with actor_type='system'."""
        user = await create_test_user(email="ai-actor@example.com", role="owner")
        ticket = await create_test_ticket(column="ai_planning")

        with patch(
            "app.services.n8n_service.trigger_workflow",
            new_callable=AsyncMock,
        ):
            await sm.execute_transition(
                ticket=ticket,
                to_column="plan_review",
                actor_id=user.id,
                actor_role="ai_agent",
                db=db_session,
            )

        result = await db_session.execute(
            select(TicketHistory).where(TicketHistory.ticket_id == ticket.id)
        )
        history = result.scalar_one()
        assert history.actor_type == "system"

    async def test_actor_type_user_for_human_roles(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        """Human roles should create history with actor_type='user'."""
        user = await create_test_user(email="human-actor@example.com", role="pm_lead")
        ticket = await create_test_ticket(column="backlog")

        with patch(
            "app.services.n8n_service.trigger_workflow",
            new_callable=AsyncMock,
        ):
            await sm.execute_transition(
                ticket=ticket,
                to_column="ai_planning",
                actor_id=user.id,
                actor_role="pm_lead",
                db=db_session,
            )

        result = await db_session.execute(
            select(TicketHistory).where(TicketHistory.ticket_id == ticket.id)
        )
        history = result.scalar_one()
        assert history.actor_type == "user"

    async def test_comment_saved_in_history_details(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="comment-hist@example.com", role="pm_lead")
        ticket = await create_test_ticket(column="backlog")

        with patch(
            "app.services.n8n_service.trigger_workflow",
            new_callable=AsyncMock,
        ):
            await sm.execute_transition(
                ticket=ticket,
                to_column="ai_planning",
                actor_id=user.id,
                actor_role="pm_lead",
                db=db_session,
                comment="Starting planning phase",
            )

        result = await db_session.execute(
            select(TicketHistory).where(TicketHistory.ticket_id == ticket.id)
        )
        history = result.scalar_one()
        assert history.details == {"comment": "Starting planning phase"}

    async def test_no_comment_details_is_none(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="no-comment@example.com", role="pm_lead")
        ticket = await create_test_ticket(column="backlog")

        with patch(
            "app.services.n8n_service.trigger_workflow",
            new_callable=AsyncMock,
        ):
            await sm.execute_transition(
                ticket=ticket,
                to_column="ai_planning",
                actor_id=user.id,
                actor_role="pm_lead",
                db=db_session,
            )

        result = await db_session.execute(
            select(TicketHistory).where(TicketHistory.ticket_id == ticket.id)
        )
        history = result.scalar_one()
        assert history.details is None


# ===================================================================
# execute_transition — retry count
# ===================================================================


class TestExecuteTransitionRetry:
    """Retry count tracking."""

    async def test_retry_incremented_from_code_review(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="retry-cr@example.com", role="developer")
        ticket = await create_test_ticket(column="code_review")
        initial = ticket.retry_count

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

        assert result.retry_count == initial + 1

    async def test_retry_incremented_from_staging_verification(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="retry-sv@example.com", role="developer")
        ticket = await create_test_ticket(column="staging_verification")
        initial = ticket.retry_count

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

        assert result.retry_count == initial + 1

    async def test_retry_not_incremented_from_plan_review(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        """First ai_coding entry (from plan_review) should NOT increment."""
        user = await create_test_user(email="first-ai@example.com", role="developer")
        ticket = await create_test_ticket(column="plan_review")
        initial = ticket.retry_count

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

        assert result.retry_count == initial


# ===================================================================
# _trigger_side_effects
# ===================================================================


class TestTriggerSideEffects:
    """Side-effect workflow triggers."""

    async def test_backlog_to_ai_planning_triggers_ai_planning(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="se-plan@example.com", role="pm_lead")
        ticket = await create_test_ticket(column="backlog")

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
        assert mock_trigger.call_args[0][0] == "ai_planning"
        payload = mock_trigger.call_args[0][1]
        assert "description" in payload
        assert "acceptance_criteria" in payload

    async def test_plan_review_to_ai_coding_triggers_ai_coding(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="se-code@example.com", role="developer")
        ticket = await create_test_ticket(column="plan_review")

        with patch(
            "app.services.n8n_service.trigger_workflow",
            new_callable=AsyncMock,
        ) as mock_trigger:
            await sm.execute_transition(
                ticket=ticket,
                to_column="ai_coding",
                actor_id=user.id,
                actor_role="developer",
                db=db_session,
            )

        mock_trigger.assert_awaited_once()
        assert mock_trigger.call_args[0][0] == "ai_coding"

    async def test_code_review_to_staging_triggers_build_test(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="se-build@example.com", role="developer")
        ticket = await create_test_ticket(column="code_review")

        with patch(
            "app.services.n8n_service.trigger_workflow",
            new_callable=AsyncMock,
        ) as mock_trigger:
            await sm.execute_transition(
                ticket=ticket,
                to_column="staging",
                actor_id=user.id,
                actor_role="developer",
                db=db_session,
            )

        mock_trigger.assert_awaited_once()
        assert mock_trigger.call_args[0][0] == "build_test"
        payload = mock_trigger.call_args[0][1]
        assert "branch_name" in payload

    async def test_staging_verification_to_production_triggers_deploy_canary(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="se-deploy@example.com", role="pm_lead")
        ticket = await create_test_ticket(column="staging_verification")

        with patch(
            "app.services.n8n_service.trigger_workflow",
            new_callable=AsyncMock,
        ) as mock_trigger:
            await sm.execute_transition(
                ticket=ticket,
                to_column="production",
                actor_id=user.id,
                actor_role="pm_lead",
                db=db_session,
            )

        mock_trigger.assert_awaited_once()
        assert mock_trigger.call_args[0][0] == "deploy_canary"
        payload = mock_trigger.call_args[0][1]
        assert payload["environment"] == "production"

    async def test_other_transitions_do_not_trigger_workflows(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        """ai_planning -> plan_review should NOT trigger any workflow."""
        user = await create_test_user(email="se-noop@example.com", role="ai_agent")
        ticket = await create_test_ticket(column="ai_planning")

        with patch(
            "app.services.n8n_service.trigger_workflow",
            new_callable=AsyncMock,
        ) as mock_trigger:
            await sm.execute_transition(
                ticket=ticket,
                to_column="plan_review",
                actor_id=user.id,
                actor_role="ai_agent",
                db=db_session,
            )

        mock_trigger.assert_not_awaited()

    async def test_exception_in_trigger_does_not_propagate(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="se-fail@example.com", role="pm_lead")
        ticket = await create_test_ticket(column="backlog")

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

        # Transition still succeeded
        assert result.column_name == ColumnName.AI_PLANNING
