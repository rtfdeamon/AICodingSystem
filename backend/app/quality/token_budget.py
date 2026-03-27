"""Token Budget Enforcer -- per-context cost accounting.

Tracks and enforces token budgets per context type (code review,
full analysis, agent task, etc.) with team-level daily cost limits,
usage recording, and budget alerting.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class BudgetContext(StrEnum):
    CODE_REVIEW = "code_review"
    FULL_ANALYSIS = "full_analysis"
    AGENT_TASK = "agent_task"
    DOCSTRING = "docstring"
    TEST_GEN = "test_gen"
    PLANNING = "planning"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class BudgetConfig:
    """Per-context token budget configuration."""

    context: BudgetContext
    max_input_tokens: int
    max_output_tokens: int
    cost_per_1k_input: float
    cost_per_1k_output: float


@dataclass
class BudgetCheck:
    """Result of a budget check."""

    allowed: bool
    context: BudgetContext
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    budget_remaining: float
    warning: str | None = None


@dataclass
class CostRecord:
    """Recorded token usage event."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    context: BudgetContext = BudgetContext.CODE_REVIEW
    team: str = ""
    feature: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class BudgetAlert:
    """Alert when a team approaches its budget limit."""

    team: str
    context: BudgetContext
    used: float
    limit: float
    utilization_pct: float


# ── In-memory stores (production would use DB) ──────────────────────────

_budget_configs: dict[BudgetContext, BudgetConfig] = {}
_cost_records: list[CostRecord] = []
_team_budgets: dict[str, float] = {}  # team -> daily budget limit


# ── Default budgets ─────────────────────────────────────────────────────

_DEFAULT_BUDGETS: dict[BudgetContext, tuple[int, int]] = {
    BudgetContext.CODE_REVIEW: (2000, 1000),
    BudgetContext.FULL_ANALYSIS: (8000, 4000),
    BudgetContext.AGENT_TASK: (32000, 16000),
    BudgetContext.DOCSTRING: (1000, 500),
    BudgetContext.TEST_GEN: (4000, 4000),
    BudgetContext.PLANNING: (16000, 8000),
}

_DEFAULT_COST_INPUT = 0.01   # per 1k tokens
_DEFAULT_COST_OUTPUT = 0.03  # per 1k tokens


def _ensure_defaults() -> None:
    """Populate default budget configs if not already configured."""
    for ctx, (max_in, max_out) in _DEFAULT_BUDGETS.items():
        if ctx not in _budget_configs:
            _budget_configs[ctx] = BudgetConfig(
                context=ctx,
                max_input_tokens=max_in,
                max_output_tokens=max_out,
                cost_per_1k_input=_DEFAULT_COST_INPUT,
                cost_per_1k_output=_DEFAULT_COST_OUTPUT,
            )


# Initialise on import
_ensure_defaults()


# ── Public API ───────────────────────────────────────────────────────────

def configure_budget(
    context: BudgetContext,
    max_input: int,
    max_output: int,
    cost_input: float,
    cost_output: float,
) -> BudgetConfig:
    """Configure (or override) the budget for a specific context."""
    config = BudgetConfig(
        context=context,
        max_input_tokens=max_input,
        max_output_tokens=max_output,
        cost_per_1k_input=cost_input,
        cost_per_1k_output=cost_output,
    )
    _budget_configs[context] = config
    logger.info(
        "Budget configured: context=%s max_in=%d max_out=%d",
        context, max_input, max_output,
    )
    return config


def set_team_budget(team: str, daily_limit: float) -> None:
    """Set the daily budget limit for a team."""
    _team_budgets[team] = daily_limit
    logger.info("Team budget set: team=%s daily_limit=%.4f", team, daily_limit)


def check_budget(
    context: BudgetContext,
    input_tokens: int,
    output_tokens: int = 0,
    team: str | None = None,
) -> BudgetCheck:
    """Check whether a request fits within the configured budget.

    Validates token counts against context limits and, if *team* is
    provided, against the team's remaining daily budget.
    """
    config = _budget_configs.get(context)
    if config is None:
        return BudgetCheck(
            allowed=False,
            context=context,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=0.0,
            budget_remaining=0.0,
            warning="No budget configured for context",
        )

    estimated_cost = (
        (input_tokens / 1000) * config.cost_per_1k_input
        + (output_tokens / 1000) * config.cost_per_1k_output
    )

    # Token-level check
    input_over = input_tokens > config.max_input_tokens
    output_over = output_tokens > config.max_output_tokens

    warning: str | None = None
    allowed = True

    if input_over or output_over:
        parts: list[str] = []
        if input_over:
            parts.append(
                f"input_tokens ({input_tokens}) exceeds max"
                f" ({config.max_input_tokens})",
            )
        if output_over:
            parts.append(
                f"output_tokens ({output_tokens}) exceeds max"
                f" ({config.max_output_tokens})",
            )
        warning = "; ".join(parts)
        allowed = False

    # Team budget check
    budget_remaining = 0.0
    if team is not None and team in _team_budgets:
        team_used = get_team_usage(team)
        budget_remaining = _team_budgets[team] - team_used
        if estimated_cost > budget_remaining:
            team_warning = (
                f"team '{team}' budget exceeded"
                f" (remaining={budget_remaining:.4f},"
                f" cost={estimated_cost:.4f})"
            )
            warning = f"{warning}; {team_warning}" if warning else team_warning
            allowed = False
    elif team is not None:
        # No team budget configured -- allow but note it
        budget_remaining = 0.0

    return BudgetCheck(
        allowed=allowed,
        context=context,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=round(estimated_cost, 6),
        budget_remaining=round(budget_remaining, 6),
        warning=warning,
    )


def record_usage(
    context: BudgetContext,
    team: str,
    feature: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
) -> CostRecord:
    """Record a token usage event."""
    record = CostRecord(
        context=context,
        team=team,
        feature=feature,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
    )
    _cost_records.append(record)
    logger.info(
        "Usage recorded: context=%s team=%s feature=%s cost=%.6f",
        context, team, feature, cost,
    )
    return record


def get_team_usage(team: str, hours: int = 24) -> float:
    """Get total cost for a team within the last *hours*."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    return sum(
        r.cost for r in _cost_records
        if r.team == team and r.timestamp >= cutoff
    )


def get_feature_usage(feature: str, hours: int = 24) -> float:
    """Get total cost for a feature within the last *hours*."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    return sum(
        r.cost for r in _cost_records
        if r.feature == feature and r.timestamp >= cutoff
    )


def estimate_tokens(text: str) -> int:
    """Rough token estimate: len(text) / 4."""
    return len(text) // 4


def compress_context(text: str, max_tokens: int) -> str:
    """Truncate *text* so its estimated token count fits within *max_tokens*."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def get_budget_alerts(threshold: float = 0.8) -> list[BudgetAlert]:
    """Return alerts for teams whose usage exceeds *threshold* of their daily limit."""
    alerts: list[BudgetAlert] = []
    for team, limit in _team_budgets.items():
        if limit <= 0:
            continue
        used = get_team_usage(team)
        utilization = used / limit
        if utilization >= threshold:
            # Find the dominant context for this team
            context_costs: dict[BudgetContext, float] = {}
            cutoff = datetime.now(UTC) - timedelta(hours=24)
            for r in _cost_records:
                if r.team == team and r.timestamp >= cutoff:
                    context_costs[r.context] = context_costs.get(r.context, 0.0) + r.cost
            dominant_ctx = (
                max(context_costs, key=context_costs.get)  # type: ignore[arg-type]
                if context_costs
                else BudgetContext.CODE_REVIEW
            )
            alerts.append(
                BudgetAlert(
                    team=team,
                    context=dominant_ctx,
                    used=round(used, 6),
                    limit=limit,
                    utilization_pct=round(utilization * 100, 1),
                )
            )
    return alerts


def get_cost_summary() -> dict:
    """Return a summary of costs: total, by context, and by team."""
    total_cost = sum(r.cost for r in _cost_records)

    by_context: dict[str, float] = {}
    for r in _cost_records:
        by_context[r.context] = by_context.get(r.context, 0.0) + r.cost

    by_team: dict[str, float] = {}
    for r in _cost_records:
        by_team[r.team] = by_team.get(r.team, 0.0) + r.cost

    return {
        "total_cost": round(total_cost, 6),
        "by_context": {k: round(v, 6) for k, v in by_context.items()},
        "by_team": {k: round(v, 6) for k, v in by_team.items()},
        "record_count": len(_cost_records),
    }


def clear_budget_data() -> None:
    """Clear all stored budget data (for testing)."""
    _budget_configs.clear()
    _cost_records.clear()
    _team_budgets.clear()
    _ensure_defaults()


def budget_check_to_json(bc: BudgetCheck) -> dict:
    """Serialise a BudgetCheck to a JSON-compatible dict."""
    return {
        "allowed": bc.allowed,
        "context": bc.context.value,
        "input_tokens": bc.input_tokens,
        "output_tokens": bc.output_tokens,
        "estimated_cost": bc.estimated_cost,
        "budget_remaining": bc.budget_remaining,
        "warning": bc.warning,
    }
