"""Tests for Context Window Budget Manager."""

from __future__ import annotations

import pytest

from app.quality.context_window_budget_manager import (
    BudgetConfig,
    BudgetGrade,
    CompactionStrategy,
    ContextSection,
    ContextWindowBudgetManager,
    GateDecision,
    SectionBudget,
    _compute_utilisation,
    _find_hotspot,
    _grade_utilisation,
    _gate_from_grade,
    _section_priority,
    _simulate_compaction,
    SectionUsage,
)


# ── Helper factory ────────────────────────────────────────────────────────

def _make_manager(**overrides) -> ContextWindowBudgetManager:
    config = BudgetConfig(**overrides) if overrides else None
    return ContextWindowBudgetManager(config)


# ── Pure helper tests ─────────────────────────────────────────────────────

class TestComputeUtilisation:
    def test_zero_available(self):
        assert _compute_utilisation(100, 0) == 1.0

    def test_normal(self):
        assert _compute_utilisation(50, 100) == 0.5

    def test_over_budget(self):
        assert _compute_utilisation(150, 100) == 1.0

    def test_zero_used(self):
        assert _compute_utilisation(0, 100) == 0.0


class TestGradeUtilisation:
    def test_within_budget(self):
        cfg = BudgetConfig()
        assert _grade_utilisation(0.5, cfg) == BudgetGrade.WITHIN_BUDGET

    def test_warning(self):
        cfg = BudgetConfig()
        assert _grade_utilisation(0.75, cfg) == BudgetGrade.WARNING

    def test_over_budget(self):
        cfg = BudgetConfig()
        assert _grade_utilisation(0.90, cfg) == BudgetGrade.OVER_BUDGET

    def test_critical(self):
        cfg = BudgetConfig()
        assert _grade_utilisation(0.96, cfg) == BudgetGrade.CRITICAL


class TestGateFromGrade:
    def test_block_on_critical(self):
        assert _gate_from_grade(BudgetGrade.CRITICAL) == GateDecision.BLOCK

    def test_warn_on_over_budget(self):
        assert _gate_from_grade(BudgetGrade.OVER_BUDGET) == GateDecision.WARN

    def test_pass_on_within_budget(self):
        assert _gate_from_grade(BudgetGrade.WITHIN_BUDGET) == GateDecision.PASS

    def test_pass_on_warning(self):
        assert _gate_from_grade(BudgetGrade.WARNING) == GateDecision.PASS


class TestFindHotspot:
    def test_empty(self):
        assert _find_hotspot([]) == ""

    def test_finds_highest(self):
        usages = [
            SectionUsage(section=ContextSection.CODE, utilisation=0.5),
            SectionUsage(section=ContextSection.CONVERSATION, utilisation=0.9),
            SectionUsage(section=ContextSection.SYSTEM, utilisation=0.3),
        ]
        assert _find_hotspot(usages) == ContextSection.CONVERSATION


class TestSimulateCompaction:
    def test_truncate(self):
        result = _simulate_compaction(1000, CompactionStrategy.TRUNCATE_OLDEST)
        assert result == 500

    def test_summarise(self):
        result = _simulate_compaction(1000, CompactionStrategy.SUMMARISE)
        assert result == 300

    def test_priority_evict(self):
        result = _simulate_compaction(1000, CompactionStrategy.PRIORITY_EVICT)
        assert result == 400

    def test_sliding_window(self):
        result = _simulate_compaction(1000, CompactionStrategy.SLIDING_WINDOW)
        assert result == 600

    def test_zero_tokens(self):
        result = _simulate_compaction(0, CompactionStrategy.SUMMARISE)
        assert result == 0


class TestSectionPriority:
    def test_system_highest(self):
        assert _section_priority(ContextSection.SYSTEM) == 5

    def test_conversation_lowest(self):
        assert _section_priority(ContextSection.CONVERSATION) == 2


# ── Manager tests ─────────────────────────────────────────────────────────

class TestRegisterAgent:
    def test_default_budgets(self):
        mgr = _make_manager()
        budgets = mgr.register_agent("agent-1")
        assert len(budgets) == 5
        assert "system" in budgets
        assert "code" in budgets

    def test_custom_budgets(self):
        mgr = _make_manager()
        custom = {"system": 5000, "code": 50000}
        budgets = mgr.register_agent("agent-1", custom_budgets=custom)
        assert budgets["system"].max_tokens == 5000
        assert budgets["code"].max_tokens == 50000

    def test_invalid_section_ignored(self):
        mgr = _make_manager()
        custom = {"nonexistent": 1000, "code": 5000}
        budgets = mgr.register_agent("agent-1", custom_budgets=custom)
        assert "nonexistent" not in budgets
        assert "code" in budgets

    def test_system_not_compactable(self):
        mgr = _make_manager()
        budgets = mgr.register_agent("agent-1")
        assert budgets["system"].compactable is False
        assert budgets["code"].compactable is True


class TestRecordUsage:
    def test_basic_usage(self):
        mgr = _make_manager()
        mgr.register_agent("a1")
        usage = mgr.record_usage("a1", "code", 10000)
        assert usage.tokens_used == 10000

    def test_auto_register(self):
        mgr = _make_manager()
        usage = mgr.record_usage("new-agent", "code", 5000)
        assert usage.tokens_used == 5000

    def test_over_budget_flag(self):
        mgr = _make_manager()
        mgr.register_agent("a1", custom_budgets={"code": 100})
        usage = mgr.record_usage("a1", "code", 200)
        assert usage.is_over_budget is True


class TestGetSnapshot:
    def test_empty_agent(self):
        mgr = _make_manager()
        snap = mgr.get_snapshot("unknown")
        assert snap.grade == BudgetGrade.WITHIN_BUDGET

    def test_snapshot_with_usage(self):
        mgr = _make_manager(total_context_window=100000)
        mgr.register_agent("a1")
        mgr.record_usage("a1", "code", 30000)
        mgr.record_usage("a1", "conversation", 20000)
        snap = mgr.get_snapshot("a1")
        assert snap.total_tokens_used == 50000
        assert snap.overall_utilisation == 0.5
        assert snap.grade == BudgetGrade.WITHIN_BUDGET

    def test_critical_snapshot(self):
        mgr = _make_manager(total_context_window=10000)
        mgr.register_agent("a1")
        mgr.record_usage("a1", "code", 9800)
        snap = mgr.get_snapshot("a1")
        assert snap.grade == BudgetGrade.CRITICAL
        assert snap.gate == GateDecision.BLOCK

    def test_hotspot_detection(self):
        mgr = _make_manager(total_context_window=100000)
        mgr.register_agent("a1", custom_budgets={"code": 40000, "conversation": 30000})
        mgr.record_usage("a1", "code", 5000)
        mgr.record_usage("a1", "conversation", 25000)
        snap = mgr.get_snapshot("a1")
        assert snap.hotspot_section == ContextSection.CONVERSATION


class TestApplyCompaction:
    def test_compaction_reduces_tokens(self):
        mgr = _make_manager()
        mgr.register_agent("a1")
        mgr.record_usage("a1", "conversation", 10000)
        result = mgr.apply_compaction("a1", "conversation", CompactionStrategy.SUMMARISE)
        assert result.tokens_before == 10000
        assert result.tokens_after == 3000
        assert result.tokens_saved == 7000
        assert result.compaction_ratio == 0.3

    def test_compaction_updates_usage(self):
        mgr = _make_manager()
        mgr.register_agent("a1")
        mgr.record_usage("a1", "conversation", 10000)
        mgr.apply_compaction("a1", "conversation", CompactionStrategy.TRUNCATE_OLDEST)
        snap = mgr.get_snapshot("a1")
        conv = [u for u in snap.section_usages if u.section == ContextSection.CONVERSATION]
        assert conv[0].tokens_used == 5000


class TestAutoCompact:
    def test_compacts_over_budget_sections(self):
        mgr = _make_manager()
        mgr.register_agent("a1", custom_budgets={"code": 5000, "conversation": 3000})
        mgr.record_usage("a1", "code", 4000)  # under budget
        mgr.record_usage("a1", "conversation", 5000)  # over budget
        results = mgr.auto_compact("a1")
        assert len(results) == 1
        assert results[0].section == ContextSection.CONVERSATION

    def test_no_compaction_needed(self):
        mgr = _make_manager()
        mgr.register_agent("a1", custom_budgets={"code": 50000})
        mgr.record_usage("a1", "code", 1000)
        results = mgr.auto_compact("a1")
        assert len(results) == 0

    def test_system_not_compacted(self):
        mgr = _make_manager()
        mgr.register_agent("a1", custom_budgets={"system": 100, "code": 5000})
        mgr.record_usage("a1", "system", 200)  # over budget but not compactable
        mgr.record_usage("a1", "code", 1000)
        results = mgr.auto_compact("a1")
        assert all(r.section != ContextSection.SYSTEM for r in results)

    def test_unknown_agent(self):
        mgr = _make_manager()
        results = mgr.auto_compact("nonexistent")
        assert results == []


class TestEfficiencyReport:
    def test_empty_report(self):
        mgr = _make_manager()
        report = mgr.efficiency_report()
        assert report.avg_utilisation == 0.0

    def test_multi_agent_report(self):
        mgr = _make_manager(total_context_window=100000)
        mgr.register_agent("a1")
        mgr.register_agent("a2")
        mgr.record_usage("a1", "code", 30000)
        mgr.record_usage("a2", "code", 10000)
        report = mgr.efficiency_report()
        assert report.most_efficient_agent == "a2"
        assert report.least_efficient_agent == "a1"
        assert len(report.snapshots) == 2

    def test_report_includes_compactions(self):
        mgr = _make_manager()
        mgr.register_agent("a1")
        mgr.record_usage("a1", "conversation", 10000)
        mgr.apply_compaction("a1", "conversation", CompactionStrategy.SUMMARISE)
        report = mgr.efficiency_report()
        assert report.total_compactions == 1
        assert report.total_tokens_saved == 7000


class TestBudgetConfig:
    def test_default_values(self):
        cfg = BudgetConfig()
        assert cfg.total_context_window == 200_000
        assert cfg.safety_margin == 0.05
        assert sum(cfg.default_section_budgets.values()) == pytest.approx(1.0)

    def test_custom_values(self):
        cfg = BudgetConfig(total_context_window=100_000, safety_margin=0.10)
        assert cfg.total_context_window == 100_000


class TestEnumValues:
    def test_budget_grades(self):
        assert BudgetGrade.WITHIN_BUDGET == "within_budget"
        assert BudgetGrade.CRITICAL == "critical"

    def test_compaction_strategies(self):
        assert CompactionStrategy.SUMMARISE == "summarise"

    def test_context_sections(self):
        assert ContextSection.OUTPUT_RESERVE == "output_reserve"
