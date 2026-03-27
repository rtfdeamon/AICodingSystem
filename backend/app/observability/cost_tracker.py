"""LLM Cost Tracker -- per-request cost attribution and budget governance.

Provides granular tracking of LLM API costs across models, teams, features,
and environments with tag-based attribution, budget alerts, and spend analytics.

Key features:
- Per-request cost recording with model/team/feature tags
- Daily and monthly budget caps with enforcement
- Cost-by-tag aggregation for chargebacks
- Spend velocity alerting (burn rate monitoring)
- Model-level cost comparison and optimization hints
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class CostAlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class BudgetPeriod(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class BudgetAction(StrEnum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class CostEntry:
    """A single LLM API cost event."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    model_id: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0
    latency_ms: float = 0.0
    team: str = "default"
    feature: str = "general"
    environment: str = "development"
    ticket_id: str | None = None
    tags: dict = field(default_factory=dict)
    cached: bool = False


@dataclass
class BudgetConfig:
    """Budget cap configuration."""

    team: str
    period: BudgetPeriod
    limit_usd: float
    action_on_exceed: BudgetAction = BudgetAction.WARN


@dataclass
class BudgetStatus:
    """Current status of a budget."""

    config: BudgetConfig
    spent_usd: float
    remaining_usd: float
    utilization_pct: float
    action: BudgetAction
    entries_count: int


@dataclass
class CostAlert:
    """A cost-related alert."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    severity: CostAlertSeverity = CostAlertSeverity.INFO
    message: str = ""
    team: str = ""
    spent_usd: float = 0.0
    limit_usd: float = 0.0


@dataclass
class SpendSummary:
    """Aggregated spend summary."""

    period_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    period_end: datetime = field(default_factory=lambda: datetime.now(UTC))
    total_cost: float = 0.0
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cost_by_model: dict = field(default_factory=dict)
    cost_by_team: dict = field(default_factory=dict)
    cost_by_feature: dict = field(default_factory=dict)
    avg_cost_per_request: float = 0.0
    cache_savings: float = 0.0


# ── Model pricing table ─────────────────────────────────────────────────

MODEL_PRICING: dict[str, tuple[float, float]] = {
    # (cost_per_1k_input, cost_per_1k_output)
    "claude-opus-4": (0.015, 0.075),
    "claude-sonnet-4": (0.003, 0.015),
    "claude-haiku-3.5": (0.0008, 0.004),
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.01, 0.03),
    "gemini-2.0-flash": (0.0001, 0.0004),
    "gemini-2.0-pro": (0.00125, 0.005),
    "o3-mini": (0.0011, 0.0044),
}


# ── Cost Tracker ─────────────────────────────────────────────────────────

class CostTracker:
    """Tracks LLM API costs with tag-based attribution and budget enforcement."""

    def __init__(self):
        self._entries: list[CostEntry] = []
        self._budgets: dict[str, BudgetConfig] = {}
        self._alerts: list[CostAlert] = []

    # ── Recording ───────────────────────────────────────────────────

    def record(
        self,
        model_id: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float = 0.0,
        team: str = "default",
        feature: str = "general",
        environment: str = "development",
        ticket_id: str | None = None,
        tags: dict | None = None,
        cached: bool = False,
    ) -> CostEntry:
        """Record a single LLM API call cost."""
        pricing = MODEL_PRICING.get(model_id, (0.01, 0.03))
        input_cost = (input_tokens / 1000) * pricing[0]
        output_cost = (output_tokens / 1000) * pricing[1]

        if cached:
            input_cost *= 0.1  # 90% discount for cached
            output_cost = 0.0

        entry = CostEntry(
            model_id=model_id,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost=round(input_cost, 6),
            output_cost=round(output_cost, 6),
            total_cost=round(input_cost + output_cost, 6),
            latency_ms=latency_ms,
            team=team,
            feature=feature,
            environment=environment,
            ticket_id=ticket_id,
            tags=tags or {},
            cached=cached,
        )
        self._entries.append(entry)

        # Check budgets
        self._check_budgets(team)

        logger.debug(
            "Cost recorded: %s %s — $%.4f (%d+%d tokens) team=%s",
            provider,
            model_id,
            entry.total_cost,
            input_tokens,
            output_tokens,
            team,
        )
        return entry

    # ── Budget management ───────────────────────────────────────────

    def set_budget(
        self,
        team: str,
        period: BudgetPeriod,
        limit_usd: float,
        action_on_exceed: BudgetAction = BudgetAction.WARN,
    ) -> BudgetConfig:
        """Set a budget cap for a team."""
        config = BudgetConfig(
            team=team,
            period=period,
            limit_usd=limit_usd,
            action_on_exceed=action_on_exceed,
        )
        key = f"{team}:{period}"
        self._budgets[key] = config
        return config

    def check_budget(self, team: str) -> list[BudgetStatus]:
        """Check all budget statuses for a team."""
        statuses = []
        for key, config in self._budgets.items():
            if not key.startswith(f"{team}:"):
                continue

            spent = self._spent_in_period(team, config.period)
            remaining = max(0.0, config.limit_usd - spent)
            util = (spent / config.limit_usd * 100) if config.limit_usd > 0 else 0

            if spent >= config.limit_usd:
                action = config.action_on_exceed
            elif util >= 80:
                action = BudgetAction.WARN
            else:
                action = BudgetAction.ALLOW

            statuses.append(BudgetStatus(
                config=config,
                spent_usd=round(spent, 4),
                remaining_usd=round(remaining, 4),
                utilization_pct=round(util, 1),
                action=action,
                entries_count=len([
                    e for e in self._entries
                    if e.team == team
                ]),
            ))
        return statuses

    def should_allow(self, team: str) -> tuple[bool, str | None]:
        """Check if a request from a team should be allowed."""
        statuses = self.check_budget(team)
        for status in statuses:
            if status.action == BudgetAction.BLOCK:
                return False, (
                    f"Budget exceeded for {team}: "
                    f"${status.spent_usd:.2f} / ${status.config.limit_usd:.2f} "
                    f"({status.config.period})"
                )
        return True, None

    def _spent_in_period(self, team: str, period: BudgetPeriod) -> float:
        """Calculate total spend in the given period."""
        now = datetime.now(UTC)
        if period == BudgetPeriod.DAILY:
            cutoff = now - timedelta(days=1)
        elif period == BudgetPeriod.WEEKLY:
            cutoff = now - timedelta(weeks=1)
        else:
            cutoff = now - timedelta(days=30)

        return sum(
            e.total_cost
            for e in self._entries
            if e.team == team and e.timestamp >= cutoff
        )

    def _check_budgets(self, team: str):
        """Check budgets and generate alerts if needed."""
        statuses = self.check_budget(team)
        for status in statuses:
            if status.utilization_pct >= 100:
                severity = CostAlertSeverity.CRITICAL
                msg = (
                    f"Budget EXCEEDED for {team}: "
                    f"${status.spent_usd:.2f} / ${status.config.limit_usd:.2f}"
                )
            elif status.utilization_pct >= 80:
                severity = CostAlertSeverity.WARNING
                msg = (
                    f"Budget at {status.utilization_pct:.0f}% for {team}: "
                    f"${status.spent_usd:.2f} / ${status.config.limit_usd:.2f}"
                )
            else:
                continue

            alert = CostAlert(
                severity=severity,
                message=msg,
                team=team,
                spent_usd=status.spent_usd,
                limit_usd=status.config.limit_usd,
            )
            self._alerts.append(alert)
            logger.warning("Cost alert: %s", msg)

    # ── Analytics ───────────────────────────────────────────────────

    def summary(
        self,
        period: BudgetPeriod = BudgetPeriod.DAILY,
        team: str | None = None,
    ) -> SpendSummary:
        """Generate a spend summary for the given period."""
        now = datetime.now(UTC)
        if period == BudgetPeriod.DAILY:
            start = now - timedelta(days=1)
        elif period == BudgetPeriod.WEEKLY:
            start = now - timedelta(weeks=1)
        else:
            start = now - timedelta(days=30)

        entries = [
            e for e in self._entries
            if e.timestamp >= start
            and (team is None or e.team == team)
        ]

        cost_by_model: dict[str, float] = {}
        cost_by_team: dict[str, float] = {}
        cost_by_feature: dict[str, float] = {}
        total_input = 0
        total_output = 0
        total_cost = 0.0
        cache_savings = 0.0

        for e in entries:
            cost_by_model[e.model_id] = (
                cost_by_model.get(e.model_id, 0) + e.total_cost
            )
            cost_by_team[e.team] = (
                cost_by_team.get(e.team, 0) + e.total_cost
            )
            cost_by_feature[e.feature] = (
                cost_by_feature.get(e.feature, 0) + e.total_cost
            )
            total_input += e.input_tokens
            total_output += e.output_tokens
            total_cost += e.total_cost
            if e.cached:
                # Estimate what full price would have been
                pricing = MODEL_PRICING.get(e.model_id, (0.01, 0.03))
                full_input = (e.input_tokens / 1000) * pricing[0]
                full_output = (e.output_tokens / 1000) * pricing[1]
                cache_savings += (full_input + full_output) - e.total_cost

        return SpendSummary(
            period_start=start,
            period_end=now,
            total_cost=round(total_cost, 4),
            total_requests=len(entries),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            cost_by_model={k: round(v, 4) for k, v in cost_by_model.items()},
            cost_by_team={k: round(v, 4) for k, v in cost_by_team.items()},
            cost_by_feature={
                k: round(v, 4) for k, v in cost_by_feature.items()
            },
            avg_cost_per_request=(
                round(total_cost / len(entries), 6) if entries else 0.0
            ),
            cache_savings=round(cache_savings, 4),
        )

    def top_spenders(
        self,
        n: int = 5,
        by: str = "model",
    ) -> list[tuple[str, float]]:
        """Return top N spenders by model, team, or feature."""
        s = self.summary()
        if by == "model":
            data = s.cost_by_model
        elif by == "team":
            data = s.cost_by_team
        elif by == "feature":
            data = s.cost_by_feature
        else:
            data = s.cost_by_model

        return sorted(data.items(), key=lambda x: x[1], reverse=True)[:n]

    @property
    def alerts(self) -> list[CostAlert]:
        return list(self._alerts)

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def clear(self):
        """Clear all tracked data."""
        self._entries.clear()
        self._alerts.clear()
