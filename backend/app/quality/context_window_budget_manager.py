"""Context Window Budget Manager — intelligent context allocation & compaction.

Production AI coding agents must manage their context window as a scarce
resource. This module tracks token usage per context section, enforces
budgets, applies compaction strategies, and alerts when approaching limits.
Inspired by the shift toward context engineering as a core discipline.

Based on:
- Martin Fowler "Context Engineering for Coding Agents" (2026)
- Augment Code "11 Prompting Techniques for Better AI Agents" (2026)
- Faros AI "Best AI Coding Agents 2026" — context window management
- UCStrategies "Prompt Engineering Best Practices 2026"
- DasRoot "Prompt Versioning: The Missing DevOps Layer" (2026)

Key capabilities:
- Per-section token budget allocation (system, rules, code, conversation, output)
- Real-time token usage tracking with budget enforcement
- Compaction strategies: truncation, summarisation, priority-based eviction
- Budget utilisation analytics with hotspot detection
- Context overflow prevention with configurable safety margin
- Quality gate: within_budget / warning / over_budget / critical
- Batch context efficiency report across agents
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class BudgetGrade(StrEnum):
    WITHIN_BUDGET = "within_budget"  # <= 70%
    WARNING = "warning"             # <= 85%
    OVER_BUDGET = "over_budget"     # <= 95%
    CRITICAL = "critical"           # > 95%


class CompactionStrategy(StrEnum):
    TRUNCATE_OLDEST = "truncate_oldest"
    SUMMARISE = "summarise"
    PRIORITY_EVICT = "priority_evict"
    SLIDING_WINDOW = "sliding_window"


class ContextSection(StrEnum):
    SYSTEM = "system"
    RULES = "rules"
    CODE = "code"
    CONVERSATION = "conversation"
    OUTPUT_RESERVE = "output_reserve"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class SectionBudget:
    """Budget allocation for a single context section."""

    section: ContextSection
    max_tokens: int
    priority: int = 1  # higher = more important, kept during compaction
    compactable: bool = True  # can this section be compacted?


@dataclass
class SectionUsage:
    """Current token usage for a section."""

    section: ContextSection
    tokens_used: int = 0
    max_tokens: int = 0
    utilisation: float = 0.0
    is_over_budget: bool = False


@dataclass
class BudgetConfig:
    """Configuration for context window budget management."""

    total_context_window: int = 200_000  # total tokens available
    safety_margin: float = 0.05  # 5% reserved for safety
    warning_threshold: float = 0.70
    over_budget_threshold: float = 0.85
    critical_threshold: float = 0.95
    default_section_budgets: dict[str, float] = field(default_factory=lambda: {
        "system": 0.05,
        "rules": 0.10,
        "code": 0.40,
        "conversation": 0.30,
        "output_reserve": 0.15,
    })


@dataclass
class CompactionResult:
    """Result of a context compaction operation."""

    strategy: CompactionStrategy
    section: ContextSection
    tokens_before: int
    tokens_after: int
    tokens_saved: int
    compaction_ratio: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ContextSnapshot:
    """Point-in-time snapshot of context window usage."""

    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent: str = ""
    total_tokens_used: int = 0
    total_tokens_available: int = 0
    overall_utilisation: float = 0.0
    section_usages: list[SectionUsage] = field(default_factory=list)
    grade: BudgetGrade = BudgetGrade.WITHIN_BUDGET
    gate: GateDecision = GateDecision.PASS
    hotspot_section: str = ""
    compactions_applied: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ContextEfficiencyReport:
    """Batch efficiency report across agents."""

    snapshots: list[ContextSnapshot] = field(default_factory=list)
    avg_utilisation: float = 0.0
    most_efficient_agent: str = ""
    least_efficient_agent: str = ""
    total_compactions: int = 0
    total_tokens_saved: int = 0
    overall_grade: BudgetGrade = BudgetGrade.WITHIN_BUDGET


# ── Pure helpers ─────────────────────────────────────────────────────────

def _compute_utilisation(used: int, available: int) -> float:
    """Compute utilisation ratio, clamped to [0, 1]."""
    if available <= 0:
        return 1.0
    return min(1.0, max(0.0, used / available))


def _grade_utilisation(utilisation: float, config: BudgetConfig) -> BudgetGrade:
    """Assign a grade based on utilisation."""
    if utilisation > config.critical_threshold:
        return BudgetGrade.CRITICAL
    if utilisation > config.over_budget_threshold:
        return BudgetGrade.OVER_BUDGET
    if utilisation > config.warning_threshold:
        return BudgetGrade.WARNING
    return BudgetGrade.WITHIN_BUDGET


def _gate_from_grade(grade: BudgetGrade) -> GateDecision:
    """Map grade to gate decision."""
    if grade == BudgetGrade.CRITICAL:
        return GateDecision.BLOCK
    if grade == BudgetGrade.OVER_BUDGET:
        return GateDecision.WARN
    return GateDecision.PASS


def _find_hotspot(usages: list[SectionUsage]) -> str:
    """Find the section with highest utilisation."""
    if not usages:
        return ""
    return max(usages, key=lambda u: u.utilisation).section


def _simulate_compaction(
    tokens_used: int,
    strategy: CompactionStrategy,
) -> int:
    """Estimate tokens after compaction (heuristic)."""
    ratios = {
        CompactionStrategy.TRUNCATE_OLDEST: 0.50,
        CompactionStrategy.SUMMARISE: 0.30,
        CompactionStrategy.PRIORITY_EVICT: 0.40,
        CompactionStrategy.SLIDING_WINDOW: 0.60,
    }
    ratio = ratios.get(strategy, 0.50)
    return max(0, int(tokens_used * ratio))


# ── Main class ───────────────────────────────────────────────────────────

class ContextWindowBudgetManager:
    """Manages context window budgets across agents and sections."""

    def __init__(self, config: BudgetConfig | None = None) -> None:
        self._config = config or BudgetConfig()
        self._section_budgets: dict[str, dict[str, SectionBudget]] = {}
        self._section_tokens: dict[str, dict[str, int]] = {}
        self._compaction_history: list[CompactionResult] = []
        self._snapshots: list[ContextSnapshot] = []

    @property
    def config(self) -> BudgetConfig:
        return self._config

    def register_agent(
        self,
        agent: str,
        custom_budgets: dict[str, int] | None = None,
    ) -> dict[str, SectionBudget]:
        """Register an agent with default or custom section budgets."""
        usable_tokens = int(
            self._config.total_context_window * (1 - self._config.safety_margin)
        )

        budgets: dict[str, SectionBudget] = {}
        if custom_budgets:
            for section_name, tokens in custom_budgets.items():
                try:
                    sec = ContextSection(section_name)
                except ValueError:
                    continue
                budgets[section_name] = SectionBudget(
                    section=sec,
                    max_tokens=tokens,
                    priority=_section_priority(sec),
                    compactable=sec != ContextSection.SYSTEM,
                )
        else:
            for section_name, fraction in self._config.default_section_budgets.items():
                try:
                    sec = ContextSection(section_name)
                except ValueError:
                    continue
                budgets[section_name] = SectionBudget(
                    section=sec,
                    max_tokens=int(usable_tokens * fraction),
                    priority=_section_priority(sec),
                    compactable=sec != ContextSection.SYSTEM,
                )

        self._section_budgets[agent] = budgets
        self._section_tokens[agent] = {s: 0 for s in budgets}
        logger.info("Registered agent %s with %d section budgets", agent, len(budgets))
        return budgets

    def record_usage(
        self,
        agent: str,
        section: str,
        tokens: int,
    ) -> SectionUsage:
        """Record token usage for a section, returning current usage state."""
        if agent not in self._section_tokens:
            self.register_agent(agent)

        self._section_tokens[agent][section] = tokens
        budget = self._section_budgets.get(agent, {}).get(section)
        max_tokens = budget.max_tokens if budget else 0
        utilisation = _compute_utilisation(tokens, max_tokens) if max_tokens > 0 else 0.0

        return SectionUsage(
            section=(
                ContextSection(section)
                if section in ContextSection.__members__.values()
                else ContextSection.CODE
            ),
            tokens_used=tokens,
            max_tokens=max_tokens,
            utilisation=round(utilisation, 4),
            is_over_budget=tokens > max_tokens,
        )

    def get_snapshot(self, agent: str) -> ContextSnapshot:
        """Take a point-in-time snapshot of an agent's context usage."""
        if agent not in self._section_tokens:
            return ContextSnapshot(agent=agent, grade=BudgetGrade.WITHIN_BUDGET)

        usages: list[SectionUsage] = []
        total_used = 0
        for section_name, tokens in self._section_tokens[agent].items():
            budget = self._section_budgets.get(agent, {}).get(section_name)
            max_t = budget.max_tokens if budget else 0
            util = _compute_utilisation(tokens, max_t) if max_t > 0 else 0.0
            usages.append(SectionUsage(
                section=ContextSection(section_name),
                tokens_used=tokens,
                max_tokens=max_t,
                utilisation=round(util, 4),
                is_over_budget=tokens > max_t,
            ))
            total_used += tokens

        total_available = self._config.total_context_window
        overall_util = _compute_utilisation(total_used, total_available)
        grade = _grade_utilisation(overall_util, self._config)
        gate = _gate_from_grade(grade)
        hotspot = _find_hotspot(usages)

        compactions = sum(
            1 for c in self._compaction_history
            if c.section.value in self._section_tokens.get(agent, {})
        )

        snapshot = ContextSnapshot(
            agent=agent,
            total_tokens_used=total_used,
            total_tokens_available=total_available,
            overall_utilisation=round(overall_util, 4),
            section_usages=usages,
            grade=grade,
            gate=gate,
            hotspot_section=hotspot,
            compactions_applied=compactions,
        )
        self._snapshots.append(snapshot)
        return snapshot

    def apply_compaction(
        self,
        agent: str,
        section: str,
        strategy: CompactionStrategy,
    ) -> CompactionResult:
        """Apply compaction to a section, reducing token usage."""
        current_tokens = self._section_tokens.get(agent, {}).get(section, 0)
        after_tokens = _simulate_compaction(current_tokens, strategy)
        saved = current_tokens - after_tokens

        # Update usage
        if agent in self._section_tokens and section in self._section_tokens[agent]:
            self._section_tokens[agent][section] = after_tokens

        try:
            sec_enum = ContextSection(section)
        except ValueError:
            sec_enum = ContextSection.CODE

        result = CompactionResult(
            strategy=strategy,
            section=sec_enum,
            tokens_before=current_tokens,
            tokens_after=after_tokens,
            tokens_saved=saved,
            compaction_ratio=round(after_tokens / current_tokens, 4) if current_tokens > 0 else 0.0,
        )
        self._compaction_history.append(result)
        logger.info(
            "Compacted %s/%s: %d → %d tokens (saved %d, strategy=%s)",
            agent, section, current_tokens, after_tokens, saved, strategy,
        )
        return result

    def auto_compact(self, agent: str) -> list[CompactionResult]:
        """Automatically compact sections that are over budget, lowest priority first."""
        if agent not in self._section_budgets:
            return []

        results: list[CompactionResult] = []
        # Sort sections by priority (compact lowest priority first)
        sections = sorted(
            self._section_budgets[agent].items(),
            key=lambda x: x[1].priority,
        )

        for section_name, budget in sections:
            if not budget.compactable:
                continue
            tokens = self._section_tokens.get(agent, {}).get(section_name, 0)
            if tokens > budget.max_tokens:
                result = self.apply_compaction(
                    agent, section_name, CompactionStrategy.PRIORITY_EVICT,
                )
                results.append(result)

        return results

    def efficiency_report(self) -> ContextEfficiencyReport:
        """Generate an efficiency report across all registered agents."""
        snapshots: list[ContextSnapshot] = []
        for agent in self._section_tokens:
            snapshots.append(self.get_snapshot(agent))

        if not snapshots:
            return ContextEfficiencyReport()

        avg_util = sum(s.overall_utilisation for s in snapshots) / len(snapshots)
        most_efficient = min(snapshots, key=lambda s: s.overall_utilisation)
        least_efficient = max(snapshots, key=lambda s: s.overall_utilisation)

        total_saved = sum(c.tokens_saved for c in self._compaction_history)
        worst_grade = max(snapshots, key=lambda s: s.overall_utilisation).grade

        return ContextEfficiencyReport(
            snapshots=snapshots,
            avg_utilisation=round(avg_util, 4),
            most_efficient_agent=most_efficient.agent,
            least_efficient_agent=least_efficient.agent,
            total_compactions=len(self._compaction_history),
            total_tokens_saved=total_saved,
            overall_grade=worst_grade,
        )


# ── Module-level helpers ─────────────────────────────────────────────────

def _section_priority(section: ContextSection) -> int:
    """Default priority for a section (higher = more important)."""
    priorities = {
        ContextSection.SYSTEM: 5,
        ContextSection.RULES: 4,
        ContextSection.OUTPUT_RESERVE: 4,
        ContextSection.CODE: 3,
        ContextSection.CONVERSATION: 2,
    }
    return priorities.get(section, 1)
