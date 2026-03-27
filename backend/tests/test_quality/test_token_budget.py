"""Tests for Token Budget Enforcer module."""

from __future__ import annotations

import pytest

from app.quality.token_budget import (
    BudgetAlert,
    BudgetConfig,
    BudgetContext,
    CostRecord,
    budget_check_to_json,
    check_budget,
    clear_budget_data,
    compress_context,
    configure_budget,
    estimate_tokens,
    get_budget_alerts,
    get_cost_summary,
    get_feature_usage,
    get_team_usage,
    record_usage,
    set_team_budget,
)


@pytest.fixture(autouse=True)
def _clean_budget() -> None:
    """Clear budget data before each test."""
    clear_budget_data()


# ── Budget configuration ────────────────────────────────────────────────


class TestConfigureBudget:
    def test_configure_new_budget(self) -> None:
        cfg = configure_budget(BudgetContext.CODE_REVIEW, 5000, 2000, 0.02, 0.06)
        assert isinstance(cfg, BudgetConfig)
        assert cfg.context == BudgetContext.CODE_REVIEW
        assert cfg.max_input_tokens == 5000
        assert cfg.max_output_tokens == 2000
        assert cfg.cost_per_1k_input == 0.02
        assert cfg.cost_per_1k_output == 0.06

    def test_override_existing_budget(self) -> None:
        configure_budget(BudgetContext.DOCSTRING, 500, 200, 0.01, 0.03)
        cfg = configure_budget(BudgetContext.DOCSTRING, 2000, 1000, 0.05, 0.10)
        assert cfg.max_input_tokens == 2000
        assert cfg.max_output_tokens == 1000

    def test_defaults_are_loaded(self) -> None:
        """Default budgets should be present after clear_budget_data."""
        result = check_budget(BudgetContext.CODE_REVIEW, 100)
        assert result.allowed is True


# ── Budget check pass / fail ────────────────────────────────────────────


class TestCheckBudget:
    def test_allowed_within_limits(self) -> None:
        result = check_budget(BudgetContext.CODE_REVIEW, 1000, 500)
        assert result.allowed is True
        assert result.warning is None
        assert result.estimated_cost > 0

    def test_denied_input_over_limit(self) -> None:
        result = check_budget(BudgetContext.CODE_REVIEW, 5000, 0)
        assert result.allowed is False
        assert result.warning is not None
        assert "input_tokens" in result.warning

    def test_denied_output_over_limit(self) -> None:
        result = check_budget(BudgetContext.CODE_REVIEW, 100, 5000)
        assert result.allowed is False
        assert "output_tokens" in (result.warning or "")

    def test_denied_both_over_limit(self) -> None:
        result = check_budget(BudgetContext.DOCSTRING, 5000, 5000)
        assert result.allowed is False
        assert "input_tokens" in (result.warning or "")
        assert "output_tokens" in (result.warning or "")

    def test_exact_limit_is_allowed(self) -> None:
        result = check_budget(BudgetContext.CODE_REVIEW, 2000, 1000)
        assert result.allowed is True

    def test_estimated_cost_calculation(self) -> None:
        configure_budget(BudgetContext.CODE_REVIEW, 10000, 10000, 0.01, 0.03)
        result = check_budget(BudgetContext.CODE_REVIEW, 1000, 1000)
        expected = (1000 / 1000) * 0.01 + (1000 / 1000) * 0.03
        assert abs(result.estimated_cost - expected) < 1e-6

    def test_zero_tokens(self) -> None:
        result = check_budget(BudgetContext.CODE_REVIEW, 0, 0)
        assert result.allowed is True
        assert result.estimated_cost == 0.0


# ── Team budget limits ──────────────────────────────────────────────────


class TestTeamBudget:
    def test_set_team_budget(self) -> None:
        set_team_budget("backend", 10.0)
        # Recording within limit should be fine
        result = check_budget(BudgetContext.CODE_REVIEW, 100, 0, team="backend")
        assert result.allowed is True

    def test_team_budget_exceeded(self) -> None:
        set_team_budget("backend", 0.05)
        record_usage(BudgetContext.CODE_REVIEW, "backend", "pr-review", 1000, 500, 0.05)
        result = check_budget(BudgetContext.CODE_REVIEW, 1000, 500, team="backend")
        assert result.allowed is False
        assert "budget exceeded" in (result.warning or "")

    def test_team_without_budget_is_allowed(self) -> None:
        result = check_budget(BudgetContext.CODE_REVIEW, 100, 0, team="no-budget-team")
        assert result.allowed is True


# ── Usage recording ─────────────────────────────────────────────────────


class TestRecordUsage:
    def test_record_creates_cost_record(self) -> None:
        rec = record_usage(BudgetContext.AGENT_TASK, "infra", "deploy", 8000, 4000, 0.20)
        assert isinstance(rec, CostRecord)
        assert rec.context == BudgetContext.AGENT_TASK
        assert rec.team == "infra"
        assert rec.feature == "deploy"
        assert rec.cost == 0.20

    def test_record_has_uuid(self) -> None:
        rec = record_usage(BudgetContext.CODE_REVIEW, "team-a", "lint", 100, 50, 0.001)
        assert len(rec.id) == 36  # UUID string length

    def test_record_has_timestamp(self) -> None:
        rec = record_usage(BudgetContext.CODE_REVIEW, "team-a", "lint", 100, 50, 0.001)
        assert rec.timestamp is not None


# ── Team usage aggregation ──────────────────────────────────────────────


class TestGetTeamUsage:
    def test_team_usage_sums_costs(self) -> None:
        record_usage(BudgetContext.CODE_REVIEW, "backend", "feat-a", 100, 50, 0.01)
        record_usage(BudgetContext.FULL_ANALYSIS, "backend", "feat-b", 200, 100, 0.02)
        assert abs(get_team_usage("backend") - 0.03) < 1e-6

    def test_team_usage_filters_by_team(self) -> None:
        record_usage(BudgetContext.CODE_REVIEW, "backend", "feat-a", 100, 50, 0.01)
        record_usage(BudgetContext.CODE_REVIEW, "frontend", "feat-b", 100, 50, 0.02)
        assert abs(get_team_usage("backend") - 0.01) < 1e-6

    def test_team_usage_empty(self) -> None:
        assert get_team_usage("nonexistent") == 0.0


# ── Feature usage tracking ──────────────────────────────────────────────


class TestGetFeatureUsage:
    def test_feature_usage_sums_costs(self) -> None:
        record_usage(BudgetContext.CODE_REVIEW, "team-a", "pr-review", 100, 50, 0.01)
        record_usage(BudgetContext.CODE_REVIEW, "team-b", "pr-review", 200, 100, 0.02)
        assert abs(get_feature_usage("pr-review") - 0.03) < 1e-6

    def test_feature_usage_empty(self) -> None:
        assert get_feature_usage("unknown-feature") == 0.0


# ── Token estimation ────────────────────────────────────────────────────


class TestEstimateTokens:
    def test_basic_estimation(self) -> None:
        assert estimate_tokens("abcd") == 1

    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_longer_text(self) -> None:
        text = "a" * 400
        assert estimate_tokens(text) == 100


# ── Context compression ─────────────────────────────────────────────────


class TestCompressContext:
    def test_no_truncation_needed(self) -> None:
        text = "short"
        assert compress_context(text, 100) == text

    def test_truncation(self) -> None:
        text = "a" * 100
        result = compress_context(text, 10)
        assert len(result) == 40  # 10 tokens * 4 chars

    def test_zero_max_tokens(self) -> None:
        assert compress_context("anything", 0) == ""


# ── Budget alerts ────────────────────────────────────────────────────────


class TestGetBudgetAlerts:
    def test_no_alerts_below_threshold(self) -> None:
        set_team_budget("backend", 1.0)
        record_usage(BudgetContext.CODE_REVIEW, "backend", "feat", 100, 50, 0.1)
        alerts = get_budget_alerts(threshold=0.8)
        assert len(alerts) == 0

    def test_alert_at_threshold(self) -> None:
        set_team_budget("backend", 1.0)
        record_usage(BudgetContext.CODE_REVIEW, "backend", "feat", 100, 50, 0.85)
        alerts = get_budget_alerts(threshold=0.8)
        assert len(alerts) == 1
        alert = alerts[0]
        assert isinstance(alert, BudgetAlert)
        assert alert.team == "backend"
        assert alert.utilization_pct == 85.0

    def test_no_alerts_when_no_teams(self) -> None:
        assert get_budget_alerts() == []


# ── Cost summary ─────────────────────────────────────────────────────────


class TestGetCostSummary:
    def test_empty_summary(self) -> None:
        summary = get_cost_summary()
        assert summary["total_cost"] == 0.0
        assert summary["record_count"] == 0

    def test_summary_aggregates(self) -> None:
        record_usage(BudgetContext.CODE_REVIEW, "backend", "feat-a", 100, 50, 0.01)
        record_usage(BudgetContext.FULL_ANALYSIS, "frontend", "feat-b", 200, 100, 0.02)
        summary = get_cost_summary()
        assert abs(summary["total_cost"] - 0.03) < 1e-6
        assert summary["record_count"] == 2
        assert BudgetContext.CODE_REVIEW in summary["by_context"]
        assert "backend" in summary["by_team"]
        assert "frontend" in summary["by_team"]


# ── JSON serialization ──────────────────────────────────────────────────


class TestBudgetCheckToJson:
    def test_serializes_allowed_check(self) -> None:
        bc = check_budget(BudgetContext.CODE_REVIEW, 100, 50)
        data = budget_check_to_json(bc)
        assert data["allowed"] is True
        assert data["context"] == "code_review"
        assert data["input_tokens"] == 100
        assert data["output_tokens"] == 50
        assert isinstance(data["estimated_cost"], float)
        assert data["warning"] is None

    def test_serializes_denied_check(self) -> None:
        bc = check_budget(BudgetContext.DOCSTRING, 9999, 9999)
        data = budget_check_to_json(bc)
        assert data["allowed"] is False
        assert isinstance(data["warning"], str)


# ── Edge cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_clear_budget_data_resets(self) -> None:
        record_usage(BudgetContext.CODE_REVIEW, "t", "f", 100, 50, 1.0)
        set_team_budget("t", 5.0)
        clear_budget_data()
        assert get_cost_summary()["record_count"] == 0
        assert get_team_usage("t") == 0.0
        # Defaults should be re-loaded
        result = check_budget(BudgetContext.CODE_REVIEW, 100)
        assert result.allowed is True

    def test_budget_context_enum_values(self) -> None:
        assert BudgetContext.CODE_REVIEW.value == "code_review"
        assert BudgetContext.AGENT_TASK.value == "agent_task"
        assert len(BudgetContext) == 6
