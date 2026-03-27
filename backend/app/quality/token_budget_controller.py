"""Token Budget Controller — per-task and per-agent token budget
management with cost tracking and enforcement.

Unconstrained LLM agents can consume 5-8 USD per task through retry
loops, long context windows, and over-qualified model selection.
Token budget management enforces spending limits at the task, agent,
and session level, preventing runaway costs while maintaining quality.

Based on:
- Moltbook-AI "AI Agent Cost Optimization Guide 2026"
- Redis "LLM Token Optimization: Cut Costs & Latency in 2026"
- Stevens Online "Hidden Economics of AI Agents" (2026)
- Medium "Reduced LLM Token Costs by 90%" (Mar 2026)

Key capabilities:
- Per-task and per-agent token budgets with enforcement
- Model-aware cost estimation (input vs output tokens)
- Budget pools: daily, hourly, per-session limits
- Overspend alerting with configurable severity levels
- Usage analytics: cost breakdown by model, agent, task type
- Automatic model downgrade suggestions when budget is tight
- Quality gate: budget utilization health check
- Batch budget analysis across multiple sessions
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class BudgetStatus(StrEnum):
    UNDER_BUDGET = "under_budget"
    WARNING = "warning"
    OVER_BUDGET = "over_budget"
    EXHAUSTED = "exhausted"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class ModelTier(StrEnum):
    PREMIUM = "premium"
    STANDARD = "standard"
    ECONOMY = "economy"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class TokenUsage:
    """Token usage for a single LLM call."""

    id: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    task_id: str = ""
    agent_id: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BudgetAlert:
    """Alert when budget thresholds are crossed."""

    severity: AlertSeverity
    message: str
    budget_name: str
    used_usd: float
    limit_usd: float
    utilization: float
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class Budget:
    """A token/cost budget for a scope (task, agent, session)."""

    name: str
    limit_usd: float
    used_usd: float = 0.0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    call_count: int = 0
    status: BudgetStatus = BudgetStatus.UNDER_BUDGET
    warning_threshold: float = 0.75
    block_threshold: float = 0.95


@dataclass
class ModelDowngradeSuggestion:
    """Suggestion to use a cheaper model to stay in budget."""

    current_model: str
    suggested_model: str
    current_tier: ModelTier
    suggested_tier: ModelTier
    estimated_savings_pct: float
    reason: str


@dataclass
class UsageReport:
    """Aggregate usage report."""

    total_cost_usd: float
    total_tokens: int
    total_input_tokens: int
    total_output_tokens: int
    call_count: int
    cost_by_model: dict[str, float]
    cost_by_agent: dict[str, float]
    cost_by_task: dict[str, float]
    alerts: list[BudgetAlert]
    downgrade_suggestions: list[ModelDowngradeSuggestion]
    gate_decision: GateDecision
    computed_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchBudgetReport:
    """Report across multiple budget scopes."""

    budgets: list[Budget]
    total_used_usd: float
    total_limit_usd: float
    overall_utilization: float
    alerts: list[BudgetAlert]
    gate_decision: GateDecision


# ── Pricing ──────────────────────────────────────────────────────────────

# Per-million-token prices (2026 Q1 averages)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_M, output_per_M)
    "claude-opus": (15.0, 75.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (0.25, 1.25),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-pro": (1.25, 5.0),
    "gemini-flash": (0.075, 0.30),
}

_MODEL_TIERS: dict[str, ModelTier] = {
    "claude-opus": ModelTier.PREMIUM,
    "claude-sonnet": ModelTier.STANDARD,
    "claude-haiku": ModelTier.ECONOMY,
    "gpt-4o": ModelTier.STANDARD,
    "gpt-4o-mini": ModelTier.ECONOMY,
    "gemini-pro": ModelTier.STANDARD,
    "gemini-flash": ModelTier.ECONOMY,
}

_DOWNGRADE_MAP: dict[str, str] = {
    "claude-opus": "claude-sonnet",
    "claude-sonnet": "claude-haiku",
    "gpt-4o": "gpt-4o-mini",
    "gemini-pro": "gemini-flash",
}


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a call."""
    in_price, out_price = _MODEL_PRICING.get(model, (3.0, 15.0))
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


# ── Main class ───────────────────────────────────────────────────────────

class TokenBudgetController:
    """Manage token budgets for tasks, agents, and sessions.

    Enforces spending limits and provides cost analytics to
    prevent runaway LLM costs in production pipelines.
    """

    def __init__(
        self,
        default_task_budget_usd: float = 1.0,
        default_agent_budget_usd: float = 5.0,
        session_budget_usd: float = 20.0,
        warning_threshold: float = 0.75,
        block_threshold: float = 0.95,
    ) -> None:
        self.default_task_budget_usd = default_task_budget_usd
        self.default_agent_budget_usd = default_agent_budget_usd
        self.session_budget_usd = session_budget_usd
        self.warning_threshold = warning_threshold
        self.block_threshold = block_threshold

        # Budgets
        self._budgets: dict[str, Budget] = {}
        self._session_budget = Budget(
            name="session",
            limit_usd=session_budget_usd,
            warning_threshold=warning_threshold,
            block_threshold=block_threshold,
        )
        self._budgets["session"] = self._session_budget

        # Usage history
        self._usages: list[TokenUsage] = []
        self._alerts: list[BudgetAlert] = []

    # ── Budget management ────────────────────────────────────────────

    def create_budget(
        self,
        name: str,
        limit_usd: float | None = None,
    ) -> Budget:
        """Create or reset a named budget."""
        budget = Budget(
            name=name,
            limit_usd=limit_usd or self.default_task_budget_usd,
            warning_threshold=self.warning_threshold,
            block_threshold=self.block_threshold,
        )
        self._budgets[name] = budget
        return budget

    def get_budget(self, name: str) -> Budget | None:
        """Get a budget by name."""
        return self._budgets.get(name)

    # ── Usage tracking ───────────────────────────────────────────────

    def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_id: str = "",
        agent_id: str = "",
    ) -> TokenUsage:
        """Record a token usage event and update budgets."""
        cost = _compute_cost(model, input_tokens, output_tokens)
        total = input_tokens + output_tokens

        usage = TokenUsage(
            id=uuid.uuid4().hex[:12],
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            cost_usd=cost,
            task_id=task_id,
            agent_id=agent_id,
        )
        self._usages.append(usage)

        # Update session budget
        self._update_budget(self._session_budget, usage)

        # Update task budget
        if task_id and task_id in self._budgets:
            self._update_budget(self._budgets[task_id], usage)

        # Update agent budget
        if agent_id and agent_id in self._budgets:
            self._update_budget(self._budgets[agent_id], usage)

        return usage

    def _update_budget(self, budget: Budget, usage: TokenUsage) -> None:
        """Update budget counters and check thresholds."""
        budget.used_usd += usage.cost_usd
        budget.total_tokens += usage.total_tokens
        budget.input_tokens += usage.input_tokens
        budget.output_tokens += usage.output_tokens
        budget.call_count += 1

        utilization = budget.used_usd / max(budget.limit_usd, 0.001)

        if utilization >= 1.0:
            budget.status = BudgetStatus.EXHAUSTED
            self._emit_alert(AlertSeverity.CRITICAL, budget, utilization)
        elif utilization >= budget.block_threshold:
            budget.status = BudgetStatus.OVER_BUDGET
            self._emit_alert(AlertSeverity.CRITICAL, budget, utilization)
        elif utilization >= budget.warning_threshold:
            budget.status = BudgetStatus.WARNING
            self._emit_alert(AlertSeverity.WARNING, budget, utilization)
        else:
            budget.status = BudgetStatus.UNDER_BUDGET

    def _emit_alert(
        self,
        severity: AlertSeverity,
        budget: Budget,
        utilization: float,
    ) -> None:
        """Create a budget alert."""
        alert = BudgetAlert(
            severity=severity,
            message=(
                f"Budget '{budget.name}' at {utilization:.0%} "
                f"(${budget.used_usd:.4f} / ${budget.limit_usd:.2f})"
            ),
            budget_name=budget.name,
            used_usd=budget.used_usd,
            limit_usd=budget.limit_usd,
            utilization=utilization,
        )
        self._alerts.append(alert)
        logger.warning("Budget alert: %s", alert.message)

    # ── Checks ───────────────────────────────────────────────────────

    def check_budget(self, budget_name: str = "session") -> GateDecision:
        """Check if a budget allows further spending."""
        budget = self._budgets.get(budget_name)
        if not budget:
            return GateDecision.PASS

        utilization = budget.used_usd / max(budget.limit_usd, 0.001)
        if utilization >= budget.block_threshold:
            return GateDecision.BLOCK
        if utilization >= budget.warning_threshold:
            return GateDecision.WARN
        return GateDecision.PASS

    def suggest_downgrade(self, model: str) -> ModelDowngradeSuggestion | None:
        """Suggest a cheaper model if budget is tight."""
        session_util = (
            self._session_budget.used_usd
            / max(self._session_budget.limit_usd, 0.001)
        )
        if session_util < self.warning_threshold:
            return None

        suggested = _DOWNGRADE_MAP.get(model)
        if not suggested:
            return None

        current_tier = _MODEL_TIERS.get(model, ModelTier.STANDARD)
        suggested_tier = _MODEL_TIERS.get(suggested, ModelTier.ECONOMY)

        in_curr, out_curr = _MODEL_PRICING.get(model, (3.0, 15.0))
        in_sugg, out_sugg = _MODEL_PRICING.get(suggested, (0.25, 1.25))
        savings = 1.0 - (in_sugg + out_sugg) / max(in_curr + out_curr, 0.001)

        return ModelDowngradeSuggestion(
            current_model=model,
            suggested_model=suggested,
            current_tier=current_tier,
            suggested_tier=suggested_tier,
            estimated_savings_pct=savings,
            reason=(
                f"Session budget at {session_util:.0%}. "
                f"Switching to {suggested} saves ~{savings:.0%}."
            ),
        )

    # ── Reporting ────────────────────────────────────────────────────

    def report(self) -> UsageReport:
        """Generate an aggregate usage report."""
        cost_by_model: dict[str, float] = {}
        cost_by_agent: dict[str, float] = {}
        cost_by_task: dict[str, float] = {}

        total_in = 0
        total_out = 0

        for u in self._usages:
            cost_by_model[u.model] = cost_by_model.get(u.model, 0) + u.cost_usd
            if u.agent_id:
                cost_by_agent[u.agent_id] = (
                    cost_by_agent.get(u.agent_id, 0) + u.cost_usd
                )
            if u.task_id:
                cost_by_task[u.task_id] = (
                    cost_by_task.get(u.task_id, 0) + u.cost_usd
                )
            total_in += u.input_tokens
            total_out += u.output_tokens

        # Downgrade suggestions for active expensive models
        suggestions: list[ModelDowngradeSuggestion] = []
        for model in cost_by_model:
            sugg = self.suggest_downgrade(model)
            if sugg:
                suggestions.append(sugg)

        gate = self.check_budget("session")

        return UsageReport(
            total_cost_usd=self._session_budget.used_usd,
            total_tokens=self._session_budget.total_tokens,
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            call_count=self._session_budget.call_count,
            cost_by_model=cost_by_model,
            cost_by_agent=cost_by_agent,
            cost_by_task=cost_by_task,
            alerts=list(self._alerts),
            downgrade_suggestions=suggestions,
            gate_decision=gate,
        )

    def batch_report(self) -> BatchBudgetReport:
        """Generate a report across all active budgets."""
        budgets = list(self._budgets.values())
        total_used = sum(b.used_usd for b in budgets)
        total_limit = sum(b.limit_usd for b in budgets)
        utilization = total_used / max(total_limit, 0.001)

        if utilization >= self.block_threshold:
            gate = GateDecision.BLOCK
        elif utilization >= self.warning_threshold:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        return BatchBudgetReport(
            budgets=budgets,
            total_used_usd=total_used,
            total_limit_usd=total_limit,
            overall_utilization=utilization,
            alerts=list(self._alerts),
            gate_decision=gate,
        )
