"""Unit tests for the kanban_service module: transition validation and RBAC."""

from __future__ import annotations

import uuid

from app.models.ticket import ColumnName, Priority, Ticket
from app.services.kanban_service import validate_transition

# No pytestmark - all tests in this module are synchronous


def _make_ticket(column: str, description: str | None = "some description") -> Ticket:
    """Create a minimal Ticket instance for testing validation logic."""
    return Ticket(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        ticket_number=1,
        title="Test",
        description=description,
        column_name=ColumnName(column),
        priority=Priority.P2,
        retry_count=0,
        position=0,
    )


class TestValidateTransitionValid:
    """Tests for valid transitions."""

    def test_backlog_to_ai_planning_owner(self) -> None:
        ticket = _make_ticket("backlog")
        ok, reason = validate_transition(ticket, "ai_planning", "owner")
        assert ok is True
        assert reason == ""

    def test_backlog_to_ai_planning_pm_lead(self) -> None:
        ticket = _make_ticket("backlog")
        ok, reason = validate_transition(ticket, "ai_planning", "pm_lead")
        assert ok is True

    def test_ai_planning_to_plan_review_ai_agent(self) -> None:
        ticket = _make_ticket("ai_planning")
        ok, reason = validate_transition(ticket, "plan_review", "ai_agent")
        assert ok is True

    def test_plan_review_to_ai_coding_owner(self) -> None:
        ticket = _make_ticket("plan_review")
        ok, reason = validate_transition(ticket, "ai_coding", "owner")
        assert ok is True

    def test_code_review_to_staging_developer(self) -> None:
        ticket = _make_ticket("code_review")
        ok, reason = validate_transition(ticket, "staging", "developer")
        assert ok is True

    def test_staging_verification_to_production_pm_lead(self) -> None:
        """Per TZ: only pm_lead can deploy to production."""
        ticket = _make_ticket("staging_verification")
        ok, reason = validate_transition(ticket, "production", "pm_lead")
        assert ok is True


class TestValidateTransitionInvalid:
    """Tests for invalid transitions."""

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

    def test_backlog_to_ai_planning_missing_description(self) -> None:
        """The backlog -> ai_planning transition requires description."""
        ticket = _make_ticket("backlog", description=None)
        ok, reason = validate_transition(ticket, "ai_planning", "owner")
        assert ok is False
        assert "description" in reason.lower()


class TestValidateTransitionWrongRole:
    """Tests for RBAC enforcement on transitions."""

    def test_developer_cannot_move_backlog_to_ai_planning(self) -> None:
        ticket = _make_ticket("backlog")
        ok, reason = validate_transition(ticket, "ai_planning", "developer")
        assert ok is False
        assert "role" in reason.lower()

    def test_developer_cannot_move_to_production(self) -> None:
        ticket = _make_ticket("staging_verification")
        ok, reason = validate_transition(ticket, "production", "developer")
        assert ok is False
        assert "role" in reason.lower()

    def test_ai_agent_cannot_move_to_staging(self) -> None:
        ticket = _make_ticket("code_review")
        ok, reason = validate_transition(ticket, "staging", "ai_agent")
        assert ok is False
        assert "role" in reason.lower()


class TestDeveloperReviewPermissions:
    """Per TZ: developer can approve/reject on plan_review and code_review."""

    def test_developer_can_approve_plan(self) -> None:
        ticket = _make_ticket("plan_review")
        ok, reason = validate_transition(ticket, "ai_coding", "developer")
        assert ok is True, f"Developer should approve plans: {reason}"

    def test_developer_can_reject_plan(self) -> None:
        ticket = _make_ticket("plan_review")
        ok, reason = validate_transition(ticket, "backlog", "developer")
        assert ok is True, f"Developer should reject plans: {reason}"

    def test_developer_can_approve_code(self) -> None:
        ticket = _make_ticket("code_review")
        ok, reason = validate_transition(ticket, "staging", "developer")
        assert ok is True, f"Developer should approve code: {reason}"

    def test_developer_can_reject_code(self) -> None:
        ticket = _make_ticket("code_review")
        ok, reason = validate_transition(ticket, "ai_coding", "developer")
        assert ok is True, f"Developer should reject code: {reason}"

    def test_owner_cannot_deploy_to_production(self) -> None:
        """Per TZ: only pm_lead can deploy to production."""
        ticket = _make_ticket("staging_verification")
        ok, reason = validate_transition(ticket, "production", "owner")
        assert ok is False
        assert "role" in reason.lower()
