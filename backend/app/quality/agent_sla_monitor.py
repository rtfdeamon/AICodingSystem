"""Agent SLA Monitor — define and enforce service-level agreements for AI agents.

AI agents need SLAs just like infrastructure.  This module defines
per-agent SLA contracts (latency P95, quality floor, cost ceiling, error
budget) and continuously monitors compliance.  Breaches trigger alerts
and can gate deployments.

Based on:
- UptimeRobot "AI Agent Monitoring: Best Practices, Tools, and Metrics" (2026)
- Braintrust "AI Observability Tools: A Buyer's Guide" (2026)
- OpenTelemetry "AI Agent Observability — Evolving Standards" (2025)
- Galileo "6 Best AI Agent Monitoring Tools for Production" (2026)
- Andrii Furmanets "AI Agents 2026: Practical Architecture" (2026)

Key capabilities:
- Per-agent SLA contract definition (latency, quality, cost, error budget)
- Continuous monitoring with rolling window evaluation
- Error budget computation and burn-rate alerts
- SLA compliance percentage tracking
- Breach severity classification (minor / major / critical)
- Incident-style breach records for audit
- Quality gate: compliant / at_risk / breached
- Batch SLA status across all agents
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class SLAMetric(StrEnum):
    LATENCY_P95 = "latency_p95"
    QUALITY_FLOOR = "quality_floor"
    COST_CEILING = "cost_ceiling"
    ERROR_RATE = "error_rate"
    AVAILABILITY = "availability"


class BreachSeverity(StrEnum):
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class ComplianceStatus(StrEnum):
    COMPLIANT = "compliant"
    AT_RISK = "at_risk"
    BREACHED = "breached"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class SLATarget:
    """Single SLA target for a metric."""

    metric: SLAMetric
    target_value: float  # threshold
    warning_pct: float = 80.0  # % of target that triggers warning
    higher_is_better: bool = False  # True for quality, availability


@dataclass
class SLAContract:
    """Full SLA contract for an agent."""

    agent: str
    targets: list[SLATarget] = field(default_factory=list)
    window_minutes: int = 60  # evaluation window
    error_budget_pct: float = 0.5  # 0.5% allowed downtime / errors


@dataclass
class MetricObservation:
    """Single observation of a metric value."""

    agent: str
    metric: SLAMetric
    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class BreachRecord:
    """Record of an SLA breach."""

    breach_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent: str = ""
    metric: SLAMetric = SLAMetric.LATENCY_P95
    severity: BreachSeverity = BreachSeverity.MINOR
    observed_value: float = 0.0
    target_value: float = 0.0
    deviation_pct: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class MetricCompliance:
    """Compliance status for a single metric."""

    metric: SLAMetric
    target_value: float
    current_value: float
    compliance_pct: float  # % of observations within target
    status: ComplianceStatus
    breach_count: int


@dataclass
class AgentSLAReport:
    """SLA report for a single agent."""

    agent: str
    overall_status: ComplianceStatus
    gate: GateDecision
    metric_compliance: list[MetricCompliance]
    error_budget_remaining_pct: float
    breach_count: int
    observation_count: int


@dataclass
class BatchSLAReport:
    """Batch SLA report across all agents."""

    reports: list[AgentSLAReport]
    compliant_count: int
    at_risk_count: int
    breached_count: int
    total_breaches: int


# ── Pure helpers ─────────────────────────────────────────────────────────

def _classify_severity(deviation_pct: float) -> BreachSeverity:
    """Classify breach severity based on deviation from target."""
    if deviation_pct < 20:
        return BreachSeverity.MINOR
    if deviation_pct < 50:
        return BreachSeverity.MAJOR
    return BreachSeverity.CRITICAL


def _check_compliance(
    values: list[float],
    target: float,
    *,
    higher_is_better: bool,
) -> tuple[float, int]:
    """Compute compliance percentage and breach count."""
    if not values:
        return 100.0, 0

    breaches = 0
    for v in values:
        if higher_is_better:
            if v < target:
                breaches += 1
        elif v > target:
            breaches += 1

    compliance = ((len(values) - breaches) / len(values)) * 100
    return round(compliance, 2), breaches


def _compliance_status(compliance_pct: float, warning_pct: float) -> ComplianceStatus:
    """Determine compliance status from percentage."""
    if compliance_pct >= 99.0:
        return ComplianceStatus.COMPLIANT
    if compliance_pct >= warning_pct:
        return ComplianceStatus.AT_RISK
    return ComplianceStatus.BREACHED


def _compute_error_budget(
    total_observations: int,
    total_breaches: int,
    budget_pct: float,
) -> float:
    """Compute remaining error budget as percentage."""
    if total_observations == 0:
        return 100.0
    allowed = total_observations * (budget_pct / 100.0)
    if allowed == 0:
        return 0.0 if total_breaches > 0 else 100.0
    remaining = max(0, allowed - total_breaches) / allowed * 100
    return round(remaining, 2)


# ── Main class ───────────────────────────────────────────────────────────

class AgentSLAMonitor:
    """Monitors SLA compliance for AI agents."""

    def __init__(self) -> None:
        self._contracts: dict[str, SLAContract] = {}
        self._observations: list[MetricObservation] = []
        self._breaches: list[BreachRecord] = []

    # ── Contract management ──────────────────────────────────────────

    def register_contract(self, contract: SLAContract) -> None:
        """Register an SLA contract for an agent."""
        self._contracts[contract.agent] = contract
        logger.info("Registered SLA contract for agent %s", contract.agent)

    def create_default_contract(self, agent: str) -> SLAContract:
        """Create a contract with sensible defaults."""
        contract = SLAContract(
            agent=agent,
            targets=[
                SLATarget(metric=SLAMetric.LATENCY_P95, target_value=3000.0),
                SLATarget(metric=SLAMetric.QUALITY_FLOOR, target_value=0.7, higher_is_better=True),
                SLATarget(metric=SLAMetric.COST_CEILING, target_value=0.50),
                SLATarget(metric=SLAMetric.ERROR_RATE, target_value=0.05),
                SLATarget(metric=SLAMetric.AVAILABILITY, target_value=0.99, higher_is_better=True),
            ],
        )
        self._contracts[agent] = contract
        return contract

    # ── Observation recording ────────────────────────────────────────

    def observe(self, agent: str, metric: SLAMetric, value: float) -> MetricObservation | None:
        """Record a metric observation and check for breach."""
        obs = MetricObservation(agent=agent, metric=metric, value=value)
        self._observations.append(obs)

        # Check for immediate breach
        contract = self._contracts.get(agent)
        if contract:
            for target in contract.targets:
                if target.metric == metric:
                    breached = (
                        value < target.target_value
                        if target.higher_is_better
                        else value > target.target_value
                    )
                    if breached:
                        deviation = abs(value - target.target_value)
                        deviation_pct = (
                            (deviation / target.target_value * 100)
                            if target.target_value else 0
                        )
                        breach = BreachRecord(
                            agent=agent,
                            metric=metric,
                            severity=_classify_severity(deviation_pct),
                            observed_value=value,
                            target_value=target.target_value,
                            deviation_pct=round(deviation_pct, 2),
                        )
                        self._breaches.append(breach)
                        logger.warning(
                            "SLA breach for %s on %s: %.2f vs target %.2f (%s)",
                            agent, metric, value, target.target_value, breach.severity,
                        )
        return obs

    def observe_batch(
        self, agent: str, metrics: dict[SLAMetric, float],
    ) -> list[MetricObservation]:
        """Record multiple observations at once."""
        return [
            obs for m, v in metrics.items()
            if (obs := self.observe(agent, m, v)) is not None
        ]

    # ── Compliance evaluation ────────────────────────────────────────

    def evaluate_agent(self, agent: str) -> AgentSLAReport:
        """Evaluate SLA compliance for an agent."""
        contract = self._contracts.get(agent)
        targets = contract.targets if contract else []
        window = contract.window_minutes if contract else 60
        budget_pct = contract.error_budget_pct if contract else 0.5

        cutoff = datetime.now(UTC) - timedelta(minutes=window)
        agent_obs = [
            o for o in self._observations
            if o.agent == agent and o.timestamp >= cutoff
        ]

        metric_results: list[MetricCompliance] = []
        total_breaches = 0

        for target in targets:
            values = [o.value for o in agent_obs if o.metric == target.metric]
            compliance_pct, breaches = _check_compliance(
                values, target.target_value, higher_is_better=target.higher_is_better,
            )
            total_breaches += breaches
            status = _compliance_status(compliance_pct, target.warning_pct)
            current = values[-1] if values else 0.0

            metric_results.append(MetricCompliance(
                metric=target.metric,
                target_value=target.target_value,
                current_value=current,
                compliance_pct=compliance_pct,
                status=status,
                breach_count=breaches,
            ))

        error_budget_remaining = _compute_error_budget(
            len(agent_obs), total_breaches, budget_pct,
        )

        # Overall status
        statuses = [m.status for m in metric_results]
        if ComplianceStatus.BREACHED in statuses:
            overall = ComplianceStatus.BREACHED
            gate = GateDecision.BLOCK
        elif ComplianceStatus.AT_RISK in statuses:
            overall = ComplianceStatus.AT_RISK
            gate = GateDecision.WARN
        else:
            overall = ComplianceStatus.COMPLIANT
            gate = GateDecision.PASS

        return AgentSLAReport(
            agent=agent,
            overall_status=overall,
            gate=gate,
            metric_compliance=metric_results,
            error_budget_remaining_pct=error_budget_remaining,
            breach_count=total_breaches,
            observation_count=len(agent_obs),
        )

    def get_breaches(self, agent: str = "") -> list[BreachRecord]:
        """Get breach records, optionally filtered by agent."""
        if agent:
            return [b for b in self._breaches if b.agent == agent]
        return list(self._breaches)

    def batch_evaluate(self) -> BatchSLAReport:
        """Evaluate all registered agents."""
        reports = [self.evaluate_agent(a) for a in self._contracts]
        compliant = sum(
            1 for r in reports if r.overall_status == ComplianceStatus.COMPLIANT
        )
        at_risk = sum(
            1 for r in reports if r.overall_status == ComplianceStatus.AT_RISK
        )
        breached = sum(
            1 for r in reports if r.overall_status == ComplianceStatus.BREACHED
        )
        return BatchSLAReport(
            reports=reports,
            compliant_count=compliant,
            at_risk_count=at_risk,
            breached_count=breached,
            total_breaches=sum(r.breach_count for r in reports),
        )
