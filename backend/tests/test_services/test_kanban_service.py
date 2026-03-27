"""Comprehensive tests for kanban_service — transitions, moves, board, reorder."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import ColumnName, Priority, Ticket
from app.models.ticket_history import TicketHistory
from app.services.kanban_service import (
    get_board,
    move_ticket,
    reorder_ticket,
    validate_transition,
)

# NOTE: Only async test methods use @pytest.mark.asyncio (via asyncio_mode=auto in pyproject.toml).
# Do NOT use module-level pytestmark to avoid warnings on sync tests.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticket(
    column: str,
    description: str | None = "some description",
    branch_name: str | None = None,
    retry_count: int = 0,
    title: str = "Test Ticket",
) -> Ticket:
    """Create a minimal Ticket for synchronous validation tests."""
    return Ticket(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        ticket_number=1,
        title=title,
        description=description,
        column_name=ColumnName(column),
        priority=Priority.P2,
        retry_count=retry_count,
        position=0,
        branch_name=branch_name,
    )


# ===================================================================
# validate_transition
# ===================================================================


class TestValidateTransitionValid:
    """All valid transitions should return (True, '')."""

    def test_backlog_to_ai_planning_owner(self) -> None:
        ticket = _make_ticket("backlog")
        ok, reason = validate_transition(ticket, "ai_planning", "owner")
        assert ok is True
        assert reason == ""

    def test_backlog_to_ai_planning_pm_lead(self) -> None:
        ticket = _make_ticket("backlog")
        ok, reason = validate_transition(ticket, "ai_planning", "pm_lead")
        assert ok is True
        assert reason == ""

    def test_ai_planning_to_plan_review_ai_agent(self) -> None:
        ticket = _make_ticket("ai_planning")
        ok, reason = validate_transition(ticket, "plan_review", "ai_agent")
        assert ok is True

    def test_ai_planning_to_plan_review_pm_lead(self) -> None:
        ticket = _make_ticket("ai_planning")
        ok, reason = validate_transition(ticket, "plan_review", "pm_lead")
        assert ok is True

    def test_ai_planning_to_plan_review_owner(self) -> None:
        ticket = _make_ticket("ai_planning")
        ok, reason = validate_transition(ticket, "plan_review", "owner")
        assert ok is True

    def test_plan_review_to_ai_coding_developer(self) -> None:
        ticket = _make_ticket("plan_review")
        ok, reason = validate_transition(ticket, "ai_coding", "developer")
        assert ok is True

    def test_plan_review_to_ai_coding_owner(self) -> None:
        ticket = _make_ticket("plan_review")
        ok, reason = validate_transition(ticket, "ai_coding", "owner")
        assert ok is True

    def test_plan_review_to_backlog_developer(self) -> None:
        ticket = _make_ticket("plan_review")
        ok, reason = validate_transition(ticket, "backlog", "developer")
        assert ok is True

    def test_ai_coding_to_code_review_ai_agent(self) -> None:
        ticket = _make_ticket("ai_coding")
        ok, reason = validate_transition(ticket, "code_review", "ai_agent")
        assert ok is True

    def test_code_review_to_staging_developer(self) -> None:
        ticket = _make_ticket("code_review")
        ok, reason = validate_transition(ticket, "staging", "developer")
        assert ok is True

    def test_code_review_to_ai_coding_developer(self) -> None:
        """code_review -> ai_coding is valid for developer (request changes)."""
        ticket = _make_ticket("code_review")
        ok, reason = validate_transition(ticket, "ai_coding", "developer")
        assert ok is True

    def test_staging_to_staging_verification(self) -> None:
        ticket = _make_ticket("staging")
        ok, reason = validate_transition(ticket, "staging_verification", "ai_agent")
        assert ok is True

    def test_staging_verification_to_production_pm_lead(self) -> None:
        """Only pm_lead can deploy to production."""
        ticket = _make_ticket("staging_verification")
        ok, reason = validate_transition(ticket, "production", "pm_lead")
        assert ok is True

    def test_staging_verification_to_ai_coding_developer(self) -> None:
        """Verification failed, rework by developer."""
        ticket = _make_ticket("staging_verification")
        ok, reason = validate_transition(ticket, "ai_coding", "developer")
        assert ok is True


class TestValidateTransitionInvalid:
    """Invalid transitions should return (False, reason)."""

    def test_backlog_to_production_rejected(self) -> None:
        ticket = _make_ticket("backlog")
        ok, reason = validate_transition(ticket, "production", "owner")
        assert ok is False
        assert "not allowed" in reason.lower()

    def test_ai_coding_to_backlog_rejected(self) -> None:
        ticket = _make_ticket("ai_coding")
        ok, reason = validate_transition(ticket, "backlog", "owner")
        assert ok is False

    def test_production_to_backlog_rejected(self) -> None:
        ticket = _make_ticket("production")
        ok, reason = validate_transition(ticket, "backlog", "owner")
        assert ok is False

    def test_staging_to_production_rejected(self) -> None:
        """Cannot skip staging_verification."""
        ticket = _make_ticket("staging")
        ok, reason = validate_transition(ticket, "production", "pm_lead")
        assert ok is False


class TestValidateTransitionWrongRole:
    """RBAC enforcement tests."""

    def test_developer_cannot_backlog_to_ai_planning(self) -> None:
        ticket = _make_ticket("backlog")
        ok, reason = validate_transition(ticket, "ai_planning", "developer")
        assert ok is False
        assert "role" in reason.lower()
        assert "developer" in reason.lower()

    def test_owner_cannot_deploy_to_production(self) -> None:
        """Only pm_lead can deploy to production."""
        ticket = _make_ticket("staging_verification")
        ok, reason = validate_transition(ticket, "production", "owner")
        assert ok is False
        assert "role" in reason.lower()

    def test_ai_agent_cannot_approve_code(self) -> None:
        ticket = _make_ticket("code_review")
        ok, reason = validate_transition(ticket, "staging", "ai_agent")
        assert ok is False


class TestValidateTransitionPrerequisites:
    """Prerequisite checks."""

    def test_missing_description_for_backlog_to_ai_planning(self) -> None:
        ticket = _make_ticket("backlog", description=None)
        ok, reason = validate_transition(ticket, "ai_planning", "owner")
        assert ok is False
        assert "description" in reason.lower()

    def test_empty_description_for_backlog_to_ai_planning(self) -> None:
        ticket = _make_ticket("backlog", description="")
        ok, reason = validate_transition(ticket, "ai_planning", "owner")
        assert ok is False
        assert "description" in reason.lower()


class TestValidateTransitionColumnNameEnum:
    """Test with ColumnName enum value vs string."""

    def test_ticket_with_enum_column_name(self) -> None:
        """column_name stored as ColumnName enum works correctly."""
        ticket = _make_ticket("backlog")
        assert isinstance(ticket.column_name, ColumnName)
        ok, _ = validate_transition(ticket, "ai_planning", "owner")
        assert ok is True

    def test_ticket_with_string_column_name(self) -> None:
        """column_name stored as raw string should still work."""
        ticket = _make_ticket("backlog")
        # Force column_name to be a raw string (bypass enum)
        object.__setattr__(ticket, "column_name", "backlog")
        ok, _ = validate_transition(ticket, "ai_planning", "owner")
        assert ok is True


# ===================================================================
# move_ticket
# ===================================================================


class TestMoveTicketSuccess:
    """Successful ticket moves."""

    async def test_successful_move(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="move-ok@example.com", role="owner")
        ticket = await create_test_ticket(column="backlog")

        with patch("app.services.websocket_manager.ws_manager") as mock_ws:
            mock_ws.broadcast_to_project = AsyncMock()
            result = await move_ticket(
                db=db_session,
                ticket_id=ticket.id,
                to_column="ai_planning",
                actor_id=user.id,
                actor_role="owner",
            )

        assert result.column_name == ColumnName.AI_PLANNING
        assert result.position == 0

    async def test_history_record_created(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="history@example.com", role="owner")
        ticket = await create_test_ticket(column="backlog")

        with patch("app.services.websocket_manager.ws_manager") as mock_ws:
            mock_ws.broadcast_to_project = AsyncMock()
            await move_ticket(
                db=db_session,
                ticket_id=ticket.id,
                to_column="ai_planning",
                actor_id=user.id,
                actor_role="owner",
                comment="Let's go",
            )

        result = await db_session.execute(
            select(TicketHistory).where(TicketHistory.ticket_id == ticket.id)
        )
        history = result.scalar_one()
        assert history.action == "moved"
        assert history.from_column == "backlog"
        assert history.to_column == "ai_planning"
        assert history.actor_id == user.id
        assert history.details == {"comment": "Let's go"}

    async def test_history_without_comment(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="nocomment@example.com", role="owner")
        ticket = await create_test_ticket(column="backlog")

        with patch("app.services.websocket_manager.ws_manager") as mock_ws:
            mock_ws.broadcast_to_project = AsyncMock()
            await move_ticket(
                db=db_session,
                ticket_id=ticket.id,
                to_column="ai_planning",
                actor_id=user.id,
                actor_role="owner",
            )

        result = await db_session.execute(
            select(TicketHistory).where(TicketHistory.ticket_id == ticket.id)
        )
        history = result.scalar_one()
        assert history.details is None


class TestMoveTicketErrors:
    """Error cases for move_ticket."""

    async def test_ticket_not_found_raises_404(
        self,
        db_session: AsyncSession,
        create_test_user,
    ) -> None:
        user = await create_test_user(email="404@example.com")
        fake_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            await move_ticket(
                db=db_session,
                ticket_id=fake_id,
                to_column="ai_planning",
                actor_id=user.id,
                actor_role="owner",
            )
        assert exc_info.value.status_code == 404

    async def test_invalid_transition_raises_422(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="422@example.com", role="owner")
        ticket = await create_test_ticket(column="backlog")

        with pytest.raises(HTTPException) as exc_info:
            await move_ticket(
                db=db_session,
                ticket_id=ticket.id,
                to_column="production",
                actor_id=user.id,
                actor_role="owner",
            )
        assert exc_info.value.status_code == 422


class TestMoveTicketBranchName:
    """Branch name auto-generation logic."""

    async def test_auto_generates_branch_name_first_ai_coding(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="branch@example.com", role="developer")
        ticket = await create_test_ticket(column="plan_review", title="Add user login page")
        assert ticket.branch_name is None

        with patch("app.services.websocket_manager.ws_manager") as mock_ws:
            mock_ws.broadcast_to_project = AsyncMock()
            result = await move_ticket(
                db=db_session,
                ticket_id=ticket.id,
                to_column="ai_coding",
                actor_id=user.id,
                actor_role="developer",
            )

        assert result.branch_name is not None
        assert result.branch_name.startswith("feature/ticket-")
        assert "add" in result.branch_name.lower()

    async def test_does_not_overwrite_existing_branch_name(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="keep-branch@example.com", role="developer")
        ticket = await create_test_ticket(column="plan_review")
        ticket.branch_name = "feature/existing-branch"
        await db_session.flush()

        with patch("app.services.websocket_manager.ws_manager") as mock_ws:
            mock_ws.broadcast_to_project = AsyncMock()
            result = await move_ticket(
                db=db_session,
                ticket_id=ticket.id,
                to_column="ai_coding",
                actor_id=user.id,
                actor_role="developer",
            )

        assert result.branch_name == "feature/existing-branch"


class TestMoveTicketRetryCount:
    """Retry count increment logic."""

    async def test_increments_retry_from_code_review(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="retry-cr@example.com", role="developer")
        ticket = await create_test_ticket(column="code_review")
        ticket.branch_name = "feature/existing"
        initial = ticket.retry_count

        with patch("app.services.websocket_manager.ws_manager") as mock_ws:
            mock_ws.broadcast_to_project = AsyncMock()
            result = await move_ticket(
                db=db_session,
                ticket_id=ticket.id,
                to_column="ai_coding",
                actor_id=user.id,
                actor_role="developer",
            )

        assert result.retry_count == initial + 1

    async def test_increments_retry_from_staging_verification(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="retry-sv@example.com", role="developer")
        ticket = await create_test_ticket(column="staging_verification")
        ticket.branch_name = "feature/existing"
        initial = ticket.retry_count

        with patch("app.services.websocket_manager.ws_manager") as mock_ws:
            mock_ws.broadcast_to_project = AsyncMock()
            result = await move_ticket(
                db=db_session,
                ticket_id=ticket.id,
                to_column="ai_coding",
                actor_id=user.id,
                actor_role="developer",
            )

        assert result.retry_count == initial + 1

    async def test_no_retry_increment_from_plan_review(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        """First entry into ai_coding (from plan_review) should NOT increment retry."""
        user = await create_test_user(email="no-retry@example.com", role="developer")
        ticket = await create_test_ticket(column="plan_review")
        initial = ticket.retry_count

        with patch("app.services.websocket_manager.ws_manager") as mock_ws:
            mock_ws.broadcast_to_project = AsyncMock()
            result = await move_ticket(
                db=db_session,
                ticket_id=ticket.id,
                to_column="ai_coding",
                actor_id=user.id,
                actor_role="developer",
            )

        assert result.retry_count == initial


class TestMoveTicketWebSocket:
    """WebSocket event publishing on move."""

    async def test_publishes_ws_event(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="ws-ok@example.com", role="owner")
        ticket = await create_test_ticket(column="backlog")

        with patch("app.services.websocket_manager.ws_manager") as mock_ws:
            mock_ws.broadcast_to_project = AsyncMock()
            await move_ticket(
                db=db_session,
                ticket_id=ticket.id,
                to_column="ai_planning",
                actor_id=user.id,
                actor_role="owner",
            )

        mock_ws.broadcast_to_project.assert_awaited_once()
        call_args = mock_ws.broadcast_to_project.call_args
        event_data = call_args[0][1]
        assert event_data["data"]["from_column"] == "backlog"
        assert event_data["data"]["to_column"] == "ai_planning"

    async def test_ws_failure_does_not_block_move(
        self,
        db_session: AsyncSession,
        create_test_user,
        create_test_ticket,
    ) -> None:
        user = await create_test_user(email="ws-fail@example.com", role="owner")
        ticket = await create_test_ticket(column="backlog")

        with patch("app.services.websocket_manager.ws_manager") as mock_ws:
            mock_ws.broadcast_to_project = AsyncMock(
                side_effect=RuntimeError("WS down")
            )
            result = await move_ticket(
                db=db_session,
                ticket_id=ticket.id,
                to_column="ai_planning",
                actor_id=user.id,
                actor_role="owner",
            )

        # Move still went through
        assert result.column_name == ColumnName.AI_PLANNING


# ===================================================================
# get_board
# ===================================================================


class TestGetBoard:
    """Board retrieval tests."""

    async def test_empty_board_has_all_column_keys(
        self,
        db_session: AsyncSession,
    ) -> None:
        project_id = uuid.uuid4()
        board = await get_board(db_session, project_id)

        for col in ColumnName:
            assert col.value in board
            assert board[col.value] == []

    async def test_tickets_grouped_by_column(
        self,
        db_session: AsyncSession,
        create_test_project,
        create_test_ticket,
    ) -> None:
        project = await create_test_project(
            name="Board Project",
            slug="board-project",
        )
        await create_test_ticket(project=project, column="backlog", title="T1")
        await create_test_ticket(project=project, column="ai_planning", title="T2")

        board = await get_board(db_session, project.id)

        assert len(board["backlog"]) == 1
        assert len(board["ai_planning"]) == 1
        assert board["backlog"][0].title == "T1"
        assert board["ai_planning"][0].title == "T2"

    async def test_multiple_tickets_in_same_column(
        self,
        db_session: AsyncSession,
        create_test_project,
    ) -> None:
        project = await create_test_project(
            name="Multi Project",
            slug="multi-project",
        )
        for i in range(3):
            t = Ticket(
                id=uuid.uuid4(),
                project_id=project.id,
                ticket_number=i + 1,
                title=f"Ticket {i}",
                description="desc",
                column_name=ColumnName.BACKLOG,
                priority=Priority.P2,
                position=i,
            )
            db_session.add(t)
        await db_session.flush()

        board = await get_board(db_session, project.id)
        assert len(board["backlog"]) == 3


# ===================================================================
# reorder_ticket
# ===================================================================


class TestReorderTicket:
    """Ticket reorder tests."""

    async def test_reorder_to_new_position(
        self,
        db_session: AsyncSession,
        create_test_ticket,
    ) -> None:
        ticket = await create_test_ticket()
        result = await reorder_ticket(db_session, ticket.id, 5)
        assert result.position == 5

    async def test_reorder_ticket_not_found_raises_404(
        self,
        db_session: AsyncSession,
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await reorder_ticket(db_session, uuid.uuid4(), 3)
        assert exc_info.value.status_code == 404

    async def test_negative_position_clamped_to_zero(
        self,
        db_session: AsyncSession,
        create_test_ticket,
    ) -> None:
        ticket = await create_test_ticket()
        result = await reorder_ticket(db_session, ticket.id, -5)
        assert result.position == 0
