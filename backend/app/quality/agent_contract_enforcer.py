"""Agent Contract Enforcer.

Formal resource governance framework for AI agents:
- Contract definition (inputs, outputs, resource limits, success criteria)
- Conservation law enforcement for multi-agent delegation
- Dual enforcement: soft (budget-aware prompts) + hard (circuit breakers)
- Contract lifecycle management (proposed → active → completed/violated)
- Quality-resource tradeoff analysis

Based on:
- arXiv 2601.08815 "Agent Contracts" (COINE/AAMAS 2026)
- relari-ai/agent-contracts (GitHub 2026)
- CIO "How to get AI agent budgets right in 2026"
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)

# ── Enums ──────────────────────────────────────────────────────────────────


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class ContractStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    VIOLATED = "violated"


class ViolationType(StrEnum):
    TOKEN_LIMIT = "token_limit"
    API_CALL_LIMIT = "api_call_limit"
    TIME_LIMIT = "time_limit"
    COST_LIMIT = "cost_limit"
    CONSERVATION_LAW = "conservation_law"


# ── Dataclasses ────────────────────────────────────────────────────────────


@dataclass
class ResourceLimits:
    max_tokens: int = 100_000
    max_api_calls: int = 50
    max_wall_clock_seconds: float = 300.0
    max_cost_usd: float = 5.0


@dataclass
class ResourceUsage:
    tokens_used: int = 0
    api_calls_made: int = 0
    elapsed_seconds: float = 0.0
    cost_usd: float = 0.0


@dataclass
class Violation:
    violation_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    violation_type: ViolationType = ViolationType.TOKEN_LIMIT
    limit_value: float = 0.0
    actual_value: float = 0.0
    message: str = ""
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )


@dataclass
class Contract:
    contract_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    agent_id: str = ""
    parent_contract_id: str | None = None
    limits: ResourceLimits = field(default_factory=ResourceLimits)
    usage: ResourceUsage = field(default_factory=ResourceUsage)
    status: ContractStatus = ContractStatus.PROPOSED
    violations: list[Violation] = field(default_factory=list)
    success_criteria: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )


@dataclass
class DelegationResult:
    allowed: bool = True
    reason: str = ""
    child_contract_id: str = ""


@dataclass
class EnforcementCheck:
    within_limits: bool = True
    violations: list[Violation] = field(default_factory=list)
    utilisation: dict[str, float] = field(default_factory=dict)
    gate: GateDecision = GateDecision.PASS


@dataclass
class EnforcerConfig:
    soft_threshold: float = 0.80
    hard_threshold: float = 1.0
    enable_conservation_law: bool = True
    auto_suspend_on_violation: bool = True


@dataclass
class EnforcerReport:
    total_contracts: int = 0
    active: int = 0
    completed: int = 0
    violated: int = 0
    total_violations: int = 0
    avg_utilisation: float = 0.0
    gate: GateDecision = GateDecision.PASS


# ── Pure helpers ───────────────────────────────────────────────────────────


def _compute_utilisation(
    usage: ResourceUsage,
    limits: ResourceLimits,
) -> dict[str, float]:
    def _safe_div(a: float, b: float) -> float:
        return round(a / b, 4) if b > 0 else 0.0

    return {
        "tokens": _safe_div(usage.tokens_used, limits.max_tokens),
        "api_calls": _safe_div(usage.api_calls_made, limits.max_api_calls),
        "time": _safe_div(usage.elapsed_seconds, limits.max_wall_clock_seconds),
        "cost": _safe_div(usage.cost_usd, limits.max_cost_usd),
    }


def _check_violations(
    usage: ResourceUsage,
    limits: ResourceLimits,
) -> list[Violation]:
    violations: list[Violation] = []

    if usage.tokens_used > limits.max_tokens:
        violations.append(Violation(
            violation_type=ViolationType.TOKEN_LIMIT,
            limit_value=limits.max_tokens,
            actual_value=usage.tokens_used,
            message=f"Tokens {usage.tokens_used} > {limits.max_tokens}",
        ))

    if usage.api_calls_made > limits.max_api_calls:
        violations.append(Violation(
            violation_type=ViolationType.API_CALL_LIMIT,
            limit_value=limits.max_api_calls,
            actual_value=usage.api_calls_made,
            message=(
                f"API calls {usage.api_calls_made} > "
                f"{limits.max_api_calls}"
            ),
        ))

    if usage.elapsed_seconds > limits.max_wall_clock_seconds:
        violations.append(Violation(
            violation_type=ViolationType.TIME_LIMIT,
            limit_value=limits.max_wall_clock_seconds,
            actual_value=usage.elapsed_seconds,
            message=(
                f"Time {usage.elapsed_seconds}s > "
                f"{limits.max_wall_clock_seconds}s"
            ),
        ))

    if usage.cost_usd > limits.max_cost_usd:
        violations.append(Violation(
            violation_type=ViolationType.COST_LIMIT,
            limit_value=limits.max_cost_usd,
            actual_value=usage.cost_usd,
            message=(
                f"Cost ${usage.cost_usd} > ${limits.max_cost_usd}"
            ),
        ))

    return violations


def _check_conservation_law(
    parent_remaining: ResourceLimits,
    child_limits: ResourceLimits,
) -> tuple[bool, str]:
    if child_limits.max_tokens > parent_remaining.max_tokens:
        return False, (
            f"Child tokens {child_limits.max_tokens} exceeds "
            f"parent remaining {parent_remaining.max_tokens}"
        )
    if child_limits.max_api_calls > parent_remaining.max_api_calls:
        return False, (
            f"Child API calls {child_limits.max_api_calls} exceeds "
            f"parent remaining {parent_remaining.max_api_calls}"
        )
    if child_limits.max_cost_usd > parent_remaining.max_cost_usd:
        return False, (
            f"Child cost ${child_limits.max_cost_usd} exceeds "
            f"parent remaining ${parent_remaining.max_cost_usd}"
        )
    return True, "Conservation law satisfied"


def _remaining_limits(contract: Contract) -> ResourceLimits:
    return ResourceLimits(
        max_tokens=max(
            0, contract.limits.max_tokens - contract.usage.tokens_used,
        ),
        max_api_calls=max(
            0, contract.limits.max_api_calls - contract.usage.api_calls_made,
        ),
        max_wall_clock_seconds=max(
            0.0,
            contract.limits.max_wall_clock_seconds
            - contract.usage.elapsed_seconds,
        ),
        max_cost_usd=max(
            0.0, contract.limits.max_cost_usd - contract.usage.cost_usd,
        ),
    )


def _gate_from_utilisation(
    util: dict[str, float],
    soft: float,
    hard: float,
) -> GateDecision:
    max_util = max(util.values()) if util else 0.0
    if max_util >= hard:
        return GateDecision.BLOCK
    if max_util >= soft:
        return GateDecision.WARN
    return GateDecision.PASS


# ── Main class ─────────────────────────────────────────────────────────────


class AgentContractEnforcer:
    """Enforces resource contracts for AI agents."""

    def __init__(self, config: EnforcerConfig | None = None) -> None:
        self._config = config or EnforcerConfig()
        self._contracts: dict[str, Contract] = {}

    @property
    def config(self) -> EnforcerConfig:
        return self._config

    def create_contract(
        self,
        agent_id: str,
        limits: ResourceLimits | None = None,
        parent_contract_id: str | None = None,
        success_criteria: dict[str, float] | None = None,
    ) -> tuple[str, str]:
        contract = Contract(
            agent_id=agent_id,
            limits=limits or ResourceLimits(),
            parent_contract_id=parent_contract_id,
            success_criteria=success_criteria or {},
        )

        if (
            parent_contract_id
            and self._config.enable_conservation_law
        ):
            parent = self._contracts.get(parent_contract_id)
            if parent is None:
                return "", "Parent contract not found"
            remaining = _remaining_limits(parent)
            ok, reason = _check_conservation_law(
                remaining, contract.limits,
            )
            if not ok:
                return "", reason

        self._contracts[contract.contract_id] = contract
        logger.info(
            "Contract created: %s for agent %s",
            contract.contract_id, agent_id,
        )
        return contract.contract_id, "Contract created"

    def activate(self, contract_id: str) -> tuple[bool, str]:
        contract = self._contracts.get(contract_id)
        if contract is None:
            return False, "Contract not found"
        if contract.status != ContractStatus.PROPOSED:
            return False, f"Cannot activate from {contract.status}"
        contract.status = ContractStatus.ACTIVE
        return True, "Contract activated"

    def record_usage(
        self,
        contract_id: str,
        tokens: int = 0,
        api_calls: int = 0,
        seconds: float = 0.0,
        cost_usd: float = 0.0,
    ) -> EnforcementCheck:
        contract = self._contracts.get(contract_id)
        if contract is None:
            return EnforcementCheck(
                within_limits=False,
                gate=GateDecision.BLOCK,
                violations=[Violation(
                    message="Contract not found",
                )],
            )

        contract.usage.tokens_used += tokens
        contract.usage.api_calls_made += api_calls
        contract.usage.elapsed_seconds += seconds
        contract.usage.cost_usd += cost_usd

        violations = _check_violations(contract.usage, contract.limits)
        util = _compute_utilisation(contract.usage, contract.limits)
        gate = _gate_from_utilisation(
            util, self._config.soft_threshold, self._config.hard_threshold,
        )

        if violations:
            contract.violations.extend(violations)
            contract.status = (
                ContractStatus.SUSPENDED
                if self._config.auto_suspend_on_violation
                else contract.status
            )
            gate = GateDecision.BLOCK

        return EnforcementCheck(
            within_limits=len(violations) == 0,
            violations=violations,
            utilisation=util,
            gate=gate,
        )

    def complete(self, contract_id: str) -> tuple[bool, str]:
        contract = self._contracts.get(contract_id)
        if contract is None:
            return False, "Contract not found"
        if contract.status == ContractStatus.VIOLATED:
            return False, "Cannot complete a violated contract"
        contract.status = ContractStatus.COMPLETED
        return True, "Contract completed"

    def delegate(
        self,
        parent_contract_id: str,
        child_agent_id: str,
        child_limits: ResourceLimits,
    ) -> DelegationResult:
        parent = self._contracts.get(parent_contract_id)
        if parent is None:
            return DelegationResult(
                allowed=False, reason="Parent contract not found",
            )

        if self._config.enable_conservation_law:
            remaining = _remaining_limits(parent)
            ok, reason = _check_conservation_law(remaining, child_limits)
            if not ok:
                return DelegationResult(allowed=False, reason=reason)

        cid, msg = self.create_contract(
            agent_id=child_agent_id,
            limits=child_limits,
            parent_contract_id=parent_contract_id,
        )
        if not cid:
            return DelegationResult(allowed=False, reason=msg)

        self.activate(cid)
        return DelegationResult(
            allowed=True,
            reason="Delegation approved",
            child_contract_id=cid,
        )

    def get_contract(self, contract_id: str) -> Contract | None:
        return self._contracts.get(contract_id)

    def enforcer_report(self) -> EnforcerReport:
        contracts = list(self._contracts.values())
        total = len(contracts)
        active = sum(
            1 for c in contracts if c.status == ContractStatus.ACTIVE
        )
        completed = sum(
            1 for c in contracts if c.status == ContractStatus.COMPLETED
        )
        violated = sum(
            1 for c in contracts
            if c.status in (ContractStatus.VIOLATED, ContractStatus.SUSPENDED)
        )
        total_violations = sum(len(c.violations) for c in contracts)

        if total == 0:
            avg_util = 0.0
        else:
            utils = []
            for c in contracts:
                u = _compute_utilisation(c.usage, c.limits)
                utils.append(max(u.values()) if u else 0.0)
            avg_util = round(sum(utils) / len(utils), 4)

        if violated > 0:
            gate = GateDecision.BLOCK
        elif active > 0 and avg_util > self._config.soft_threshold:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        return EnforcerReport(
            total_contracts=total,
            active=active,
            completed=completed,
            violated=violated,
            total_violations=total_violations,
            avg_utilisation=avg_util,
            gate=gate,
        )
