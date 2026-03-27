"""Tests for Token Budget Controller."""

from __future__ import annotations

import pytest

from app.quality.token_budget_controller import (
    AlertSeverity,
    BatchBudgetReport,
    Budget,
    BudgetAlert,
    BudgetStatus,
    GateDecision,
    ModelDowngradeSuggestion,
    ModelTier,
    TokenBudgetController,
    TokenUsage,
    UsageReport,
    _compute_cost,
)


# ── Cost computation ─────────────────────────────────────────────────────

class TestComputeCost:
    def test_known_model(self):
        cost = _compute_cost("claude-sonnet", 1_000_000, 0)
        assert cost == pytest.approx(3.0)

    def test_output_more_expensive(self):
        cost_in = _compute_cost("claude-sonnet", 1000, 0)
        cost_out = _compute_cost("claude-sonnet", 0, 1000)
        assert cost_out > cost_in

    def test_unknown_model_uses_default(self):
        cost = _compute_cost("unknown-model", 1_000_000, 0)
        assert cost > 0

    def test_zero_tokens(self):
        assert _compute_cost("claude-sonnet", 0, 0) == 0.0

    def test_haiku_cheapest(self):
        haiku = _compute_cost("claude-haiku", 1000, 1000)
        sonnet = _compute_cost("claude-sonnet", 1000, 1000)
        assert haiku < sonnet

    def test_opus_most_expensive(self):
        opus = _compute_cost("claude-opus", 1000, 1000)
        sonnet = _compute_cost("claude-sonnet", 1000, 1000)
        assert opus > sonnet


# ── Budget management ────────────────────────────────────────────────────

class TestBudgetManagement:
    def setup_method(self):
        self.ctrl = TokenBudgetController(
            default_task_budget_usd=1.0,
            session_budget_usd=10.0,
        )

    def test_create_budget(self):
        b = self.ctrl.create_budget("task-1", limit_usd=2.0)
        assert isinstance(b, Budget)
        assert b.limit_usd == 2.0
        assert b.name == "task-1"

    def test_get_budget(self):
        self.ctrl.create_budget("task-1")
        b = self.ctrl.get_budget("task-1")
        assert b is not None
        assert b.name == "task-1"

    def test_get_nonexistent(self):
        assert self.ctrl.get_budget("nope") is None

    def test_session_budget_exists(self):
        b = self.ctrl.get_budget("session")
        assert b is not None
        assert b.limit_usd == 10.0


# ── Usage tracking ───────────────────────────────────────────────────────

class TestUsageTracking:
    def setup_method(self):
        self.ctrl = TokenBudgetController(session_budget_usd=10.0)

    def test_record_usage(self):
        usage = self.ctrl.record_usage("claude-sonnet", 1000, 500)
        assert isinstance(usage, TokenUsage)
        assert usage.total_tokens == 1500
        assert usage.cost_usd > 0

    def test_session_budget_updated(self):
        self.ctrl.record_usage("claude-sonnet", 1000, 500)
        b = self.ctrl.get_budget("session")
        assert b is not None
        assert b.used_usd > 0
        assert b.call_count == 1

    def test_task_budget_updated(self):
        self.ctrl.create_budget("task-1")
        self.ctrl.record_usage("claude-sonnet", 1000, 500, task_id="task-1")
        b = self.ctrl.get_budget("task-1")
        assert b is not None
        assert b.used_usd > 0

    def test_agent_budget_updated(self):
        self.ctrl.create_budget("agent-1")
        self.ctrl.record_usage("claude-sonnet", 1000, 500, agent_id="agent-1")
        b = self.ctrl.get_budget("agent-1")
        assert b is not None
        assert b.used_usd > 0

    def test_multiple_usages_accumulate(self):
        self.ctrl.record_usage("claude-sonnet", 1000, 500)
        self.ctrl.record_usage("claude-sonnet", 2000, 1000)
        b = self.ctrl.get_budget("session")
        assert b is not None
        assert b.call_count == 2
        assert b.total_tokens == 4500


# ── Budget status ────────────────────────────────────────────────────────

class TestBudgetStatus:
    def test_under_budget(self):
        ctrl = TokenBudgetController(session_budget_usd=100.0)
        ctrl.record_usage("claude-haiku", 100, 50)
        b = ctrl.get_budget("session")
        assert b is not None
        assert b.status == BudgetStatus.UNDER_BUDGET

    def test_warning_status(self):
        ctrl = TokenBudgetController(
            session_budget_usd=0.001,
            warning_threshold=0.5,
        )
        # This should push over the warning threshold
        ctrl.record_usage("claude-opus", 10000, 5000)
        b = ctrl.get_budget("session")
        assert b is not None
        assert b.status in (
            BudgetStatus.WARNING,
            BudgetStatus.OVER_BUDGET,
            BudgetStatus.EXHAUSTED,
        )

    def test_exhausted_status(self):
        ctrl = TokenBudgetController(session_budget_usd=0.0001)
        ctrl.record_usage("claude-opus", 100000, 50000)
        b = ctrl.get_budget("session")
        assert b is not None
        assert b.status == BudgetStatus.EXHAUSTED


# ── Alerts ───────────────────────────────────────────────────────────────

class TestAlerts:
    def test_no_alerts_under_budget(self):
        ctrl = TokenBudgetController(session_budget_usd=100.0)
        ctrl.record_usage("claude-haiku", 100, 50)
        assert len(ctrl._alerts) == 0

    def test_alert_on_overspend(self):
        ctrl = TokenBudgetController(session_budget_usd=0.0001)
        ctrl.record_usage("claude-opus", 100000, 50000)
        assert len(ctrl._alerts) > 0
        assert ctrl._alerts[0].severity == AlertSeverity.CRITICAL

    def test_alert_contains_budget_name(self):
        ctrl = TokenBudgetController(session_budget_usd=0.0001)
        ctrl.record_usage("claude-opus", 100000, 50000)
        assert "session" in ctrl._alerts[0].budget_name


# ── Gate checks ──────────────────────────────────────────────────────────

class TestGateChecks:
    def test_pass(self):
        ctrl = TokenBudgetController(session_budget_usd=100.0)
        assert ctrl.check_budget("session") == GateDecision.PASS

    def test_block_on_exhausted(self):
        ctrl = TokenBudgetController(session_budget_usd=0.0001)
        ctrl.record_usage("claude-opus", 100000, 50000)
        assert ctrl.check_budget("session") == GateDecision.BLOCK

    def test_unknown_budget_passes(self):
        ctrl = TokenBudgetController()
        assert ctrl.check_budget("nonexistent") == GateDecision.PASS


# ── Downgrade suggestions ───────────────────────────────────────────────

class TestDowngradeSuggestions:
    def test_no_suggestion_under_budget(self):
        ctrl = TokenBudgetController(session_budget_usd=100.0)
        assert ctrl.suggest_downgrade("claude-opus") is None

    def test_suggestion_when_tight(self):
        ctrl = TokenBudgetController(session_budget_usd=0.001)
        ctrl.record_usage("claude-opus", 100000, 50000)
        sugg = ctrl.suggest_downgrade("claude-opus")
        assert sugg is not None
        assert isinstance(sugg, ModelDowngradeSuggestion)
        assert sugg.suggested_model == "claude-sonnet"
        assert sugg.estimated_savings_pct > 0

    def test_no_downgrade_for_cheapest(self):
        ctrl = TokenBudgetController(session_budget_usd=0.001)
        ctrl.record_usage("claude-haiku", 100000, 50000)
        assert ctrl.suggest_downgrade("claude-haiku") is None

    def test_savings_percentage_positive(self):
        ctrl = TokenBudgetController(session_budget_usd=0.001)
        ctrl.record_usage("gpt-4o", 100000, 50000)
        sugg = ctrl.suggest_downgrade("gpt-4o")
        assert sugg is not None
        assert 0 < sugg.estimated_savings_pct < 1.0


# ── Reporting ────────────────────────────────────────────────────────────

class TestUsageReport:
    def setup_method(self):
        self.ctrl = TokenBudgetController(session_budget_usd=10.0)

    def test_empty_report(self):
        report = self.ctrl.report()
        assert isinstance(report, UsageReport)
        assert report.total_cost_usd == 0.0
        assert report.call_count == 0

    def test_report_with_data(self):
        self.ctrl.record_usage("claude-sonnet", 1000, 500, task_id="t1", agent_id="a1")
        self.ctrl.record_usage("gpt-4o", 2000, 1000, task_id="t2", agent_id="a1")
        report = self.ctrl.report()
        assert report.call_count == 2
        assert "claude-sonnet" in report.cost_by_model
        assert "gpt-4o" in report.cost_by_model
        assert "a1" in report.cost_by_agent
        assert "t1" in report.cost_by_task

    def test_report_gate_decision(self):
        report = self.ctrl.report()
        assert report.gate_decision == GateDecision.PASS


class TestBatchBudgetReport:
    def test_batch_report(self):
        ctrl = TokenBudgetController(session_budget_usd=10.0)
        ctrl.create_budget("task-1", 2.0)
        ctrl.create_budget("task-2", 3.0)
        report = ctrl.batch_report()
        assert isinstance(report, BatchBudgetReport)
        # session + task-1 + task-2
        assert len(report.budgets) == 3
        assert report.total_limit_usd == 15.0

    def test_batch_utilization(self):
        ctrl = TokenBudgetController(session_budget_usd=10.0)
        report = ctrl.batch_report()
        assert report.overall_utilization == 0.0
        assert report.gate_decision == GateDecision.PASS
