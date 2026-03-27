"""Tests for LLM Cost Tracker.

Covers: cost recording, budget management, alerts,
spend analytics, and tag-based attribution.
"""

from __future__ import annotations

from app.observability.cost_tracker import (
    BudgetAction,
    BudgetPeriod,
    CostAlertSeverity,
    CostEntry,
    CostTracker,
)

# ── CostEntry ────────────────────────────────────────────────────────────

class TestCostEntry:
    def test_default_values(self):
        e = CostEntry()
        assert e.id != ""
        assert e.total_cost == 0.0
        assert e.team == "default"
        assert e.feature == "general"


# ── Cost recording ───────────────────────────────────────────────────────

class TestCostRecording:
    def test_record_basic(self):
        tracker = CostTracker()
        entry = tracker.record(
            model_id="claude-sonnet-4",
            provider="anthropic",
            input_tokens=1000,
            output_tokens=500,
        )
        assert entry.total_cost > 0
        assert entry.input_cost > 0
        assert entry.output_cost > 0
        assert tracker.entry_count == 1

    def test_record_with_tags(self):
        tracker = CostTracker()
        entry = tracker.record(
            model_id="gpt-4o",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            team="backend",
            feature="code_review",
            ticket_id="T-123",
            tags={"agent": "review"},
        )
        assert entry.team == "backend"
        assert entry.feature == "code_review"
        assert entry.ticket_id == "T-123"

    def test_cached_discount(self):
        tracker = CostTracker()
        normal = tracker.record(
            model_id="claude-sonnet-4",
            provider="anthropic",
            input_tokens=1000,
            output_tokens=500,
        )
        cached = tracker.record(
            model_id="claude-sonnet-4",
            provider="anthropic",
            input_tokens=1000,
            output_tokens=500,
            cached=True,
        )
        assert cached.total_cost < normal.total_cost

    def test_unknown_model_default_pricing(self):
        tracker = CostTracker()
        entry = tracker.record(
            model_id="unknown-model",
            provider="unknown",
            input_tokens=1000,
            output_tokens=1000,
        )
        assert entry.total_cost > 0

    def test_multiple_records(self):
        tracker = CostTracker()
        for _ in range(5):
            tracker.record(
                model_id="gpt-4o-mini",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
            )
        assert tracker.entry_count == 5

    def test_latency_recorded(self):
        tracker = CostTracker()
        entry = tracker.record(
            model_id="claude-sonnet-4",
            provider="anthropic",
            input_tokens=100,
            output_tokens=50,
            latency_ms=1234.5,
        )
        assert entry.latency_ms == 1234.5


# ── Budget management ────────────────────────────────────────────────────

class TestBudgetManagement:
    def test_set_budget(self):
        tracker = CostTracker()
        config = tracker.set_budget(
            "backend", BudgetPeriod.DAILY, 10.0
        )
        assert config.team == "backend"
        assert config.limit_usd == 10.0

    def test_check_budget_under_limit(self):
        tracker = CostTracker()
        tracker.set_budget("backend", BudgetPeriod.DAILY, 100.0)
        tracker.record(
            model_id="gpt-4o-mini",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            team="backend",
        )
        statuses = tracker.check_budget("backend")
        assert len(statuses) == 1
        assert statuses[0].action == BudgetAction.ALLOW

    def test_budget_exceeded_warn(self):
        tracker = CostTracker()
        tracker.set_budget(
            "backend", BudgetPeriod.DAILY, 0.001,
            action_on_exceed=BudgetAction.WARN,
        )
        tracker.record(
            model_id="claude-opus-4",
            provider="anthropic",
            input_tokens=10000,
            output_tokens=5000,
            team="backend",
        )
        statuses = tracker.check_budget("backend")
        assert statuses[0].action == BudgetAction.WARN

    def test_budget_exceeded_block(self):
        tracker = CostTracker()
        tracker.set_budget(
            "backend", BudgetPeriod.DAILY, 0.001,
            action_on_exceed=BudgetAction.BLOCK,
        )
        tracker.record(
            model_id="claude-opus-4",
            provider="anthropic",
            input_tokens=10000,
            output_tokens=5000,
            team="backend",
        )
        allowed, reason = tracker.should_allow("backend")
        assert not allowed
        assert reason is not None

    def test_should_allow_under_budget(self):
        tracker = CostTracker()
        tracker.set_budget("dev", BudgetPeriod.DAILY, 1000.0)
        allowed, reason = tracker.should_allow("dev")
        assert allowed
        assert reason is None

    def test_no_budget_always_allows(self):
        tracker = CostTracker()
        allowed, reason = tracker.should_allow("any-team")
        assert allowed

    def test_budget_utilization(self):
        tracker = CostTracker()
        tracker.set_budget("team", BudgetPeriod.MONTHLY, 100.0)
        statuses = tracker.check_budget("team")
        assert statuses[0].utilization_pct == 0.0


# ── Alerts ───────────────────────────────────────────────────────────────

class TestAlerts:
    def test_critical_alert_on_exceed(self):
        tracker = CostTracker()
        tracker.set_budget("team", BudgetPeriod.DAILY, 0.001)
        tracker.record(
            model_id="claude-opus-4",
            provider="anthropic",
            input_tokens=10000,
            output_tokens=5000,
            team="team",
        )
        alerts = tracker.alerts
        assert len(alerts) >= 1
        assert any(
            a.severity == CostAlertSeverity.CRITICAL for a in alerts
        )

    def test_no_alert_under_budget(self):
        tracker = CostTracker()
        tracker.set_budget("team", BudgetPeriod.DAILY, 1000.0)
        tracker.record(
            model_id="gpt-4o-mini",
            provider="openai",
            input_tokens=10,
            output_tokens=5,
            team="team",
        )
        critical = [
            a for a in tracker.alerts
            if a.severity == CostAlertSeverity.CRITICAL
        ]
        assert len(critical) == 0


# ── Analytics ────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_summary_empty(self):
        tracker = CostTracker()
        s = tracker.summary()
        assert s.total_cost == 0.0
        assert s.total_requests == 0

    def test_summary_with_records(self):
        tracker = CostTracker()
        tracker.record(
            model_id="claude-sonnet-4", provider="anthropic",
            input_tokens=1000, output_tokens=500, team="a",
        )
        tracker.record(
            model_id="gpt-4o", provider="openai",
            input_tokens=500, output_tokens=200, team="b",
        )
        s = tracker.summary()
        assert s.total_requests == 2
        assert s.total_cost > 0
        assert "claude-sonnet-4" in s.cost_by_model
        assert "a" in s.cost_by_team

    def test_summary_by_team(self):
        tracker = CostTracker()
        tracker.record(
            model_id="gpt-4o", provider="openai",
            input_tokens=100, output_tokens=50, team="alpha",
        )
        tracker.record(
            model_id="gpt-4o", provider="openai",
            input_tokens=100, output_tokens=50, team="beta",
        )
        s = tracker.summary(team="alpha")
        assert s.total_requests == 1

    def test_summary_cache_savings(self):
        tracker = CostTracker()
        tracker.record(
            model_id="claude-sonnet-4", provider="anthropic",
            input_tokens=1000, output_tokens=500, cached=True,
        )
        s = tracker.summary()
        assert s.cache_savings > 0

    def test_top_spenders(self):
        tracker = CostTracker()
        for i in range(3):
            tracker.record(
                model_id="claude-opus-4", provider="anthropic",
                input_tokens=5000, output_tokens=2000, team=f"team-{i}",
            )
        top = tracker.top_spenders(n=2, by="team")
        assert len(top) == 2

    def test_top_spenders_by_model(self):
        tracker = CostTracker()
        tracker.record(
            model_id="claude-opus-4", provider="anthropic",
            input_tokens=10000, output_tokens=5000,
        )
        tracker.record(
            model_id="gpt-4o-mini", provider="openai",
            input_tokens=100, output_tokens=50,
        )
        top = tracker.top_spenders(by="model")
        assert top[0][0] == "claude-opus-4"

    def test_top_spenders_by_feature(self):
        tracker = CostTracker()
        tracker.record(
            model_id="gpt-4o", provider="openai",
            input_tokens=100, output_tokens=50,
            feature="code_review",
        )
        top = tracker.top_spenders(by="feature")
        assert top[0][0] == "code_review"

    def test_avg_cost_per_request(self):
        tracker = CostTracker()
        tracker.record(
            model_id="gpt-4o-mini", provider="openai",
            input_tokens=100, output_tokens=50,
        )
        s = tracker.summary()
        assert s.avg_cost_per_request > 0

    def test_summary_weekly(self):
        tracker = CostTracker()
        tracker.record(
            model_id="gpt-4o", provider="openai",
            input_tokens=100, output_tokens=50,
        )
        s = tracker.summary(period=BudgetPeriod.WEEKLY)
        assert s.total_requests == 1


# ── Clear ────────────────────────────────────────────────────────────────

class TestClear:
    def test_clear_all(self):
        tracker = CostTracker()
        tracker.record(
            model_id="gpt-4o", provider="openai",
            input_tokens=100, output_tokens=50,
        )
        tracker.clear()
        assert tracker.entry_count == 0
        assert len(tracker.alerts) == 0
