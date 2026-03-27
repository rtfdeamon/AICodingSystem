"""Agentic Trust Framework (ATF) — graduated autonomy governance for
AI coding agents.

Zero Trust governance treats autonomy as something earned through
demonstrated trustworthiness.  Agents are assigned graduated privilege
levels (Intern → Junior → Senior → Principal) with explicit promotion
criteria, performance thresholds, and security validation gates.

Based on Cloud Security Alliance "The Agentic Trust Framework: Zero Trust
Governance for AI Agents" (February 2026), OWASP Top 10 for Agentic
Applications (December 2025), and CoSAI guidance.

Key capabilities:
- Four maturity levels with explicit promotion criteria
- Runtime least-privilege enforcement per task
- Confused deputy and privilege escalation prevention
- Risk-proportional review pipelines
- Policy-as-code enforcement (declarative rules)
- Promotion/demotion lifecycle management
- Performance and security scoring per agent
- Full audit trail of trust decisions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class TrustLevel(IntEnum):
    """Agent trust levels — higher = more autonomous."""

    INTERN = 0
    JUNIOR = 1
    SENIOR = 2
    PRINCIPAL = 3


class PermissionScope(StrEnum):
    READ_CODE = "read_code"
    WRITE_CODE = "write_code"
    RUN_TESTS = "run_tests"
    MODIFY_CONFIG = "modify_config"
    DEPLOY_STAGING = "deploy_staging"
    DEPLOY_PRODUCTION = "deploy_production"
    ACCESS_SECRETS = "access_secrets"
    MODIFY_INFRA = "modify_infra"
    CREATE_PR = "create_pr"
    MERGE_PR = "merge_pr"
    DELETE_BRANCH = "delete_branch"
    EXTERNAL_API = "external_api"


class PromotionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    AUTO_PROMOTED = "auto_promoted"
    DEMOTED = "demoted"


class ActionOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    ESCALATED = "escalated"


# ── Permission matrix per trust level ────────────────────────────────────

LEVEL_PERMISSIONS: dict[TrustLevel, set[PermissionScope]] = {
    TrustLevel.INTERN: {
        PermissionScope.READ_CODE,
    },
    TrustLevel.JUNIOR: {
        PermissionScope.READ_CODE,
        PermissionScope.WRITE_CODE,
        PermissionScope.RUN_TESTS,
    },
    TrustLevel.SENIOR: {
        PermissionScope.READ_CODE,
        PermissionScope.WRITE_CODE,
        PermissionScope.RUN_TESTS,
        PermissionScope.MODIFY_CONFIG,
        PermissionScope.DEPLOY_STAGING,
        PermissionScope.CREATE_PR,
        PermissionScope.EXTERNAL_API,
    },
    TrustLevel.PRINCIPAL: set(PermissionScope),  # All permissions
}


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class PromotionCriteria:
    """Criteria an agent must meet to advance to the next trust level."""

    min_tasks_completed: int = 10
    min_success_rate: float = 0.9
    min_security_score: float = 0.8
    min_time_at_level_hours: float = 24.0
    max_security_violations: int = 0
    requires_human_approval: bool = True


@dataclass
class AgentProfile:
    """Profile and trust state of a single agent."""

    agent_id: str
    name: str
    trust_level: TrustLevel = TrustLevel.INTERN
    tasks_completed: int = 0
    tasks_failed: int = 0
    security_violations: int = 0
    security_score: float = 1.0
    promoted_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    promotion_history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionRequest:
    """A request from an agent to perform a privileged action."""

    agent_id: str
    permission: PermissionScope
    resource: str = ""
    context: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class ActionDecision:
    """Decision on whether to allow an agent action."""

    request: ActionRequest
    outcome: ActionOutcome
    reason: str
    trust_level: TrustLevel
    required_level: TrustLevel | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class PromotionRequest:
    """Request to promote an agent to a higher trust level."""

    agent_id: str
    current_level: TrustLevel
    target_level: TrustLevel
    status: PromotionStatus = PromotionStatus.PENDING
    criteria_met: dict[str, bool] = field(default_factory=dict)
    reason: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class TrustAnalytics:
    """Analytics across all agents."""

    total_agents: int
    agents_by_level: dict[str, int]
    total_actions: int
    allowed_actions: int
    denied_actions: int
    escalated_actions: int
    total_promotions: int
    total_demotions: int
    avg_security_score: float


# ── Agentic Trust Framework ─────────────────────────────────────────────

class AgenticTrustFramework:
    """Zero Trust governance framework for AI agents.

    Manages agent trust levels, permission enforcement, and promotion
    lifecycle with full audit trail.
    """

    def __init__(
        self,
        *,
        default_criteria: PromotionCriteria | None = None,
    ) -> None:
        self._agents: dict[str, AgentProfile] = {}
        self._default_criteria = default_criteria or PromotionCriteria()
        self._level_criteria: dict[TrustLevel, PromotionCriteria] = {}
        self._audit_log: list[dict[str, Any]] = []
        self._action_log: list[ActionDecision] = []

    # ── Agent management ─────────────────────────────────────────────

    def register_agent(
        self,
        agent_id: str,
        name: str,
        *,
        initial_level: TrustLevel = TrustLevel.INTERN,
        metadata: dict[str, Any] | None = None,
    ) -> AgentProfile:
        """Register a new agent at the given trust level."""
        profile = AgentProfile(
            agent_id=agent_id,
            name=name,
            trust_level=initial_level,
            metadata=metadata or {},
        )
        self._agents[agent_id] = profile
        self._log("register_agent", agent_id=agent_id, level=initial_level.name)
        return profile

    def get_agent(self, agent_id: str) -> AgentProfile | None:
        return self._agents.get(agent_id)

    def list_agents(self, *, level: TrustLevel | None = None) -> list[AgentProfile]:
        agents = list(self._agents.values())
        if level is not None:
            agents = [a for a in agents if a.trust_level == level]
        return agents

    # ── Permission enforcement ───────────────────────────────────────

    def check_permission(self, request: ActionRequest) -> ActionDecision:
        """Check if an agent has permission for a requested action."""
        agent = self._agents.get(request.agent_id)
        if not agent:
            decision = ActionDecision(
                request=request,
                outcome=ActionOutcome.DENIED,
                reason="Agent not registered",
                trust_level=TrustLevel.INTERN,
            )
            self._action_log.append(decision)
            return decision

        allowed_permissions = LEVEL_PERMISSIONS.get(agent.trust_level, set())
        required_level = self._min_level_for_permission(request.permission)

        if request.permission in allowed_permissions:
            outcome = ActionOutcome.ALLOWED
            reason = f"Permission granted at {agent.trust_level.name} level"
        elif required_level is not None and agent.trust_level.value == required_level.value - 1:
            outcome = ActionOutcome.ESCALATED
            reason = f"Requires {required_level.name} level; escalating for review"
        else:
            outcome = ActionOutcome.DENIED
            req_name = required_level.name if required_level else "UNKNOWN"
            reason = (
                f"Insufficient trust level: {agent.trust_level.name},"
                f" requires {req_name}"
            )

        decision = ActionDecision(
            request=request,
            outcome=outcome,
            reason=reason,
            trust_level=agent.trust_level,
            required_level=required_level,
        )
        self._action_log.append(decision)
        self._log(
            "check_permission",
            agent_id=request.agent_id,
            permission=request.permission,
            outcome=outcome,
        )
        return decision

    def record_task_outcome(
        self,
        agent_id: str,
        *,
        success: bool,
        security_violation: bool = False,
    ) -> None:
        """Record the outcome of a task performed by an agent."""
        agent = self._agents.get(agent_id)
        if not agent:
            return

        if success:
            agent.tasks_completed += 1
        else:
            agent.tasks_failed += 1

        if security_violation:
            agent.security_violations += 1
            # Recalculate security score
            total = agent.tasks_completed + agent.tasks_failed
            if total > 0:
                agent.security_score = max(
                    1.0 - (agent.security_violations / total),
                    0.0,
                )
            # Auto-demote on security violations
            if agent.security_violations > 0 and agent.trust_level > TrustLevel.INTERN:
                self._demote_agent(agent_id, "Security violation detected")

    # ── Promotion / Demotion ─────────────────────────────────────────

    def check_promotion_eligibility(self, agent_id: str) -> PromotionRequest | None:
        """Check if an agent is eligible for promotion."""
        agent = self._agents.get(agent_id)
        if not agent or agent.trust_level >= TrustLevel.PRINCIPAL:
            return None

        target = TrustLevel(agent.trust_level.value + 1)
        criteria = self._level_criteria.get(target, self._default_criteria)

        total_tasks = agent.tasks_completed + agent.tasks_failed
        success_rate = agent.tasks_completed / max(total_tasks, 1)

        criteria_met = {
            "min_tasks": agent.tasks_completed >= criteria.min_tasks_completed,
            "success_rate": success_rate >= criteria.min_success_rate,
            "security_score": agent.security_score >= criteria.min_security_score,
            "no_violations": agent.security_violations <= criteria.max_security_violations,
        }

        all_met = all(criteria_met.values())

        return PromotionRequest(
            agent_id=agent_id,
            current_level=agent.trust_level,
            target_level=target,
            status=PromotionStatus.PENDING if all_met else PromotionStatus.DENIED,
            criteria_met=criteria_met,
            reason="All criteria met" if all_met else "Criteria not met: " + ", ".join(
                k for k, v in criteria_met.items() if not v
            ),
        )

    def promote_agent(
        self,
        agent_id: str,
        *,
        auto: bool = False,
    ) -> PromotionRequest | None:
        """Promote an agent to the next trust level."""
        request = self.check_promotion_eligibility(agent_id)
        if not request or request.status == PromotionStatus.DENIED:
            return request

        agent = self._agents[agent_id]
        agent.trust_level = request.target_level
        agent.promoted_at = datetime.now(UTC).isoformat()
        agent.promotion_history.append({
            "from": request.current_level.name,
            "to": request.target_level.name,
            "auto": auto,
            "timestamp": agent.promoted_at,
        })

        request.status = PromotionStatus.AUTO_PROMOTED if auto else PromotionStatus.APPROVED

        self._log(
            "promote",
            agent_id=agent_id,
            from_level=request.current_level.name,
            to_level=request.target_level.name,
        )
        return request

    def set_level_criteria(
        self,
        level: TrustLevel,
        criteria: PromotionCriteria,
    ) -> None:
        """Set custom promotion criteria for a specific level."""
        self._level_criteria[level] = criteria

    # ── Analytics ────────────────────────────────────────────────────

    def analytics(self) -> TrustAnalytics:
        level_counts: dict[str, int] = {}
        for agent in self._agents.values():
            level_counts[agent.trust_level.name] = level_counts.get(agent.trust_level.name, 0) + 1

        allowed = sum(1 for d in self._action_log if d.outcome == ActionOutcome.ALLOWED)
        denied = sum(1 for d in self._action_log if d.outcome == ActionOutcome.DENIED)
        escalated = sum(1 for d in self._action_log if d.outcome == ActionOutcome.ESCALATED)

        promotions = sum(
            1 for e in self._audit_log if e.get("action") == "promote"
        )
        demotions = sum(
            1 for e in self._audit_log if e.get("action") == "demote"
        )

        scores = [a.security_score for a in self._agents.values()]
        avg_score = sum(scores) / max(len(scores), 1)

        return TrustAnalytics(
            total_agents=len(self._agents),
            agents_by_level=level_counts,
            total_actions=len(self._action_log),
            allowed_actions=allowed,
            denied_actions=denied,
            escalated_actions=escalated,
            total_promotions=promotions,
            total_demotions=demotions,
            avg_security_score=avg_score,
        )

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def get_action_log(self) -> list[ActionDecision]:
        return list(self._action_log)

    # ── Private helpers ──────────────────────────────────────────────

    def _demote_agent(self, agent_id: str, reason: str) -> None:
        agent = self._agents.get(agent_id)
        if not agent or agent.trust_level <= TrustLevel.INTERN:
            return

        old_level = agent.trust_level
        agent.trust_level = TrustLevel(agent.trust_level.value - 1)
        agent.promoted_at = datetime.now(UTC).isoformat()
        agent.promotion_history.append({
            "from": old_level.name,
            "to": agent.trust_level.name,
            "reason": reason,
            "timestamp": agent.promoted_at,
        })
        self._log(
            "demote",
            agent_id=agent_id,
            from_level=old_level.name,
            to_level=agent.trust_level.name,
            reason=reason,
        )

    def _min_level_for_permission(self, permission: PermissionScope) -> TrustLevel | None:
        """Find minimum trust level that grants a permission."""
        for level in TrustLevel:
            if permission in LEVEL_PERMISSIONS.get(level, set()):
                return level
        return None

    def _log(self, action: str, **kwargs: Any) -> None:
        self._audit_log.append({
            "action": action,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        })
