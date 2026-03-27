"""RBAC tests for kanban transitions, especially the production gate."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.models.ticket import ColumnName
from app.services.kanban_service import validate_transition


def _make_ticket(column: str, description: str = "Test description") -> MagicMock:
    """Create a mock ticket with the given column and description."""
    ticket = MagicMock()
    ticket.column_name = ColumnName(column)
    ticket.description = description
    return ticket


# ---------------------------------------------------------------------------
# Production gate: staging_verification -> production = pm_lead ONLY
# ---------------------------------------------------------------------------


def test_production_gate_pm_lead_allowed() -> None:
    ticket = _make_ticket("staging_verification")
    ok, reason = validate_transition(ticket, "production", "pm_lead")
    assert ok is True
    assert reason == ""


def test_production_gate_owner_forbidden() -> None:
    ticket = _make_ticket("staging_verification")
    ok, reason = validate_transition(ticket, "production", "owner")
    assert ok is False
    assert "owner" in reason


def test_production_gate_developer_forbidden() -> None:
    ticket = _make_ticket("staging_verification")
    ok, reason = validate_transition(ticket, "production", "developer")
    assert ok is False
    assert "developer" in reason


def test_production_gate_ai_agent_forbidden() -> None:
    ticket = _make_ticket("staging_verification")
    ok, reason = validate_transition(ticket, "production", "ai_agent")
    assert ok is False
    assert "ai_agent" in reason


# ---------------------------------------------------------------------------
# Other transitions
# ---------------------------------------------------------------------------


def test_backlog_to_ai_planning_owner_allowed() -> None:
    ticket = _make_ticket("backlog")
    ok, reason = validate_transition(ticket, "ai_planning", "owner")
    assert ok is True


def test_backlog_to_ai_planning_pm_lead_allowed() -> None:
    ticket = _make_ticket("backlog")
    ok, reason = validate_transition(ticket, "ai_planning", "pm_lead")
    assert ok is True


def test_backlog_to_ai_planning_developer_forbidden() -> None:
    ticket = _make_ticket("backlog")
    ok, reason = validate_transition(ticket, "ai_planning", "developer")
    assert ok is False


def test_ai_planning_to_plan_review_ai_agent_allowed() -> None:
    ticket = _make_ticket("ai_planning")
    ok, reason = validate_transition(ticket, "plan_review", "ai_agent")
    assert ok is True


def test_plan_review_to_ai_coding_pm_allowed() -> None:
    ticket = _make_ticket("plan_review")
    ok, reason = validate_transition(ticket, "ai_coding", "pm_lead")
    assert ok is True


def test_plan_review_to_ai_coding_developer_allowed() -> None:
    """Per TZ: developer can approve/reject plans (plan_review -> ai_coding)."""
    ticket = _make_ticket("plan_review")
    ok, reason = validate_transition(ticket, "ai_coding", "developer")
    assert ok is True


def test_code_review_to_staging_developer_allowed() -> None:
    ticket = _make_ticket("code_review")
    ok, reason = validate_transition(ticket, "staging", "developer")
    assert ok is True


def test_invalid_transition() -> None:
    ticket = _make_ticket("backlog")
    ok, reason = validate_transition(ticket, "production", "pm_lead")
    assert ok is False
    assert "not allowed" in reason


def test_prerequisite_check_description() -> None:
    """backlog -> ai_planning requires non-empty description."""
    ticket = _make_ticket("backlog", description="")
    ok, reason = validate_transition(ticket, "ai_planning", "owner")
    assert ok is False
    assert "description" in reason
