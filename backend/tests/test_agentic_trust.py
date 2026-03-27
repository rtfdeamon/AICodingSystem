"""Tests for Agentic Trust Framework (ATF) — graduated autonomy governance."""

from __future__ import annotations

import pytest

from app.quality.agentic_trust import (
    LEVEL_PERMISSIONS,
    ActionOutcome,
    ActionRequest,
    AgenticTrustFramework,
    AgentProfile,
    PermissionScope,
    PromotionCriteria,
    PromotionStatus,
    TrustAnalytics,
    TrustLevel,
)


@pytest.fixture
def framework() -> AgenticTrustFramework:
    return AgenticTrustFramework()


@pytest.fixture
def framework_with_agents(framework: AgenticTrustFramework) -> AgenticTrustFramework:
    framework.register_agent("agent-intern", "Intern Bot")
    framework.register_agent("agent-junior", "Junior Bot", initial_level=TrustLevel.JUNIOR)
    framework.register_agent("agent-senior", "Senior Bot", initial_level=TrustLevel.SENIOR)
    framework.register_agent("agent-principal", "Principal Bot", initial_level=TrustLevel.PRINCIPAL)
    return framework


class TestAgentRegistration:
    def test_register_agent(self, framework: AgenticTrustFramework) -> None:
        profile = framework.register_agent("a1", "Test Agent")
        assert isinstance(profile, AgentProfile)
        assert profile.trust_level == TrustLevel.INTERN

    def test_register_with_level(self, framework: AgenticTrustFramework) -> None:
        profile = framework.register_agent("a2", "Senior", initial_level=TrustLevel.SENIOR)
        assert profile.trust_level == TrustLevel.SENIOR

    def test_register_with_metadata(self, framework: AgenticTrustFramework) -> None:
        profile = framework.register_agent("a3", "Meta", metadata={"model": "gpt-4"})
        assert profile.metadata["model"] == "gpt-4"

    def test_get_agent(self, framework_with_agents: AgenticTrustFramework) -> None:
        agent = framework_with_agents.get_agent("agent-intern")
        assert agent is not None
        assert agent.name == "Intern Bot"

    def test_get_agent_nonexistent(self, framework: AgenticTrustFramework) -> None:
        assert framework.get_agent("nope") is None

    def test_list_all_agents(self, framework_with_agents: AgenticTrustFramework) -> None:
        agents = framework_with_agents.list_agents()
        assert len(agents) == 4

    def test_list_agents_by_level(self, framework_with_agents: AgenticTrustFramework) -> None:
        agents = framework_with_agents.list_agents(level=TrustLevel.INTERN)
        assert len(agents) == 1
        assert agents[0].agent_id == "agent-intern"


class TestPermissions:
    def test_intern_can_read(self, framework_with_agents: AgenticTrustFramework) -> None:
        decision = framework_with_agents.check_permission(
            ActionRequest(agent_id="agent-intern", permission=PermissionScope.READ_CODE),
        )
        assert decision.outcome == ActionOutcome.ALLOWED

    def test_intern_cannot_write(self, framework_with_agents: AgenticTrustFramework) -> None:
        decision = framework_with_agents.check_permission(
            ActionRequest(agent_id="agent-intern", permission=PermissionScope.WRITE_CODE),
        )
        assert decision.outcome in (ActionOutcome.DENIED, ActionOutcome.ESCALATED)

    def test_junior_can_write(self, framework_with_agents: AgenticTrustFramework) -> None:
        decision = framework_with_agents.check_permission(
            ActionRequest(agent_id="agent-junior", permission=PermissionScope.WRITE_CODE),
        )
        assert decision.outcome == ActionOutcome.ALLOWED

    def test_junior_cannot_deploy(self, framework_with_agents: AgenticTrustFramework) -> None:
        decision = framework_with_agents.check_permission(
            ActionRequest(agent_id="agent-junior", permission=PermissionScope.DEPLOY_STAGING),
        )
        assert decision.outcome in (ActionOutcome.DENIED, ActionOutcome.ESCALATED)

    def test_senior_can_deploy_staging(self, framework_with_agents: AgenticTrustFramework) -> None:
        decision = framework_with_agents.check_permission(
            ActionRequest(agent_id="agent-senior", permission=PermissionScope.DEPLOY_STAGING),
        )
        assert decision.outcome == ActionOutcome.ALLOWED

    def test_senior_cannot_deploy_prod(self, framework_with_agents: AgenticTrustFramework) -> None:
        decision = framework_with_agents.check_permission(
            ActionRequest(agent_id="agent-senior", permission=PermissionScope.DEPLOY_PRODUCTION),
        )
        assert decision.outcome in (ActionOutcome.DENIED, ActionOutcome.ESCALATED)

    def test_principal_can_do_everything(
        self, framework_with_agents: AgenticTrustFramework,
    ) -> None:
        for perm in PermissionScope:
            decision = framework_with_agents.check_permission(
                ActionRequest(agent_id="agent-principal", permission=perm),
            )
            assert decision.outcome == ActionOutcome.ALLOWED

    def test_unregistered_agent_denied(self, framework: AgenticTrustFramework) -> None:
        decision = framework.check_permission(
            ActionRequest(agent_id="ghost", permission=PermissionScope.READ_CODE),
        )
        assert decision.outcome == ActionOutcome.DENIED

    def test_escalation_one_level_below(self, framework_with_agents: AgenticTrustFramework) -> None:
        # Junior trying senior action → escalated
        decision = framework_with_agents.check_permission(
            ActionRequest(agent_id="agent-junior", permission=PermissionScope.DEPLOY_STAGING),
        )
        assert decision.outcome == ActionOutcome.ESCALATED


class TestTaskOutcomes:
    def test_record_success(self, framework_with_agents: AgenticTrustFramework) -> None:
        framework_with_agents.record_task_outcome("agent-intern", success=True)
        agent = framework_with_agents.get_agent("agent-intern")
        assert agent is not None
        assert agent.tasks_completed == 1

    def test_record_failure(self, framework_with_agents: AgenticTrustFramework) -> None:
        framework_with_agents.record_task_outcome("agent-intern", success=False)
        agent = framework_with_agents.get_agent("agent-intern")
        assert agent is not None
        assert agent.tasks_failed == 1

    def test_security_violation_demotes(self, framework_with_agents: AgenticTrustFramework) -> None:
        framework_with_agents.record_task_outcome(
            "agent-junior", success=False, security_violation=True,
        )
        agent = framework_with_agents.get_agent("agent-junior")
        assert agent is not None
        assert agent.trust_level == TrustLevel.INTERN
        assert agent.security_violations == 1

    def test_intern_not_demoted_below_intern(
        self, framework_with_agents: AgenticTrustFramework,
    ) -> None:
        framework_with_agents.record_task_outcome(
            "agent-intern", success=False, security_violation=True,
        )
        agent = framework_with_agents.get_agent("agent-intern")
        assert agent is not None
        assert agent.trust_level == TrustLevel.INTERN

    def test_record_nonexistent_agent(self, framework: AgenticTrustFramework) -> None:
        # Should not raise
        framework.record_task_outcome("ghost", success=True)


class TestPromotion:
    def test_check_eligibility_not_enough_tasks(
        self, framework_with_agents: AgenticTrustFramework,
    ) -> None:
        req = framework_with_agents.check_promotion_eligibility("agent-intern")
        assert req is not None
        assert req.status == PromotionStatus.DENIED

    def test_check_eligibility_met(self, framework_with_agents: AgenticTrustFramework) -> None:
        # Record enough successes
        for _ in range(15):
            framework_with_agents.record_task_outcome("agent-intern", success=True)
        req = framework_with_agents.check_promotion_eligibility("agent-intern")
        assert req is not None
        assert req.status == PromotionStatus.PENDING

    def test_promote_agent(self, framework_with_agents: AgenticTrustFramework) -> None:
        for _ in range(15):
            framework_with_agents.record_task_outcome("agent-intern", success=True)
        req = framework_with_agents.promote_agent("agent-intern")
        assert req is not None
        assert req.status == PromotionStatus.APPROVED
        agent = framework_with_agents.get_agent("agent-intern")
        assert agent is not None
        assert agent.trust_level == TrustLevel.JUNIOR

    def test_auto_promote(self, framework_with_agents: AgenticTrustFramework) -> None:
        for _ in range(15):
            framework_with_agents.record_task_outcome("agent-intern", success=True)
        req = framework_with_agents.promote_agent("agent-intern", auto=True)
        assert req is not None
        assert req.status == PromotionStatus.AUTO_PROMOTED

    def test_cannot_promote_principal(self, framework_with_agents: AgenticTrustFramework) -> None:
        req = framework_with_agents.check_promotion_eligibility("agent-principal")
        assert req is None

    def test_promote_denied_on_violations(
        self, framework_with_agents: AgenticTrustFramework,
    ) -> None:
        for _ in range(15):
            framework_with_agents.record_task_outcome("agent-junior", success=True)
        framework_with_agents.record_task_outcome(
            "agent-junior", success=False, security_violation=True,
        )
        # After demotion the agent is back to INTERN
        req = framework_with_agents.check_promotion_eligibility("agent-junior")
        if req:
            no_viol = req.criteria_met.get("no_violations")
            assert no_viol is False or req.status == PromotionStatus.DENIED

    def test_promotion_history(self, framework_with_agents: AgenticTrustFramework) -> None:
        for _ in range(15):
            framework_with_agents.record_task_outcome("agent-intern", success=True)
        framework_with_agents.promote_agent("agent-intern")
        agent = framework_with_agents.get_agent("agent-intern")
        assert agent is not None
        assert len(agent.promotion_history) == 1
        assert agent.promotion_history[0]["to"] == "JUNIOR"

    def test_custom_criteria(self, framework: AgenticTrustFramework) -> None:
        framework.set_level_criteria(
            TrustLevel.JUNIOR,
            PromotionCriteria(min_tasks_completed=2, min_success_rate=0.5),
        )
        framework.register_agent("a1", "Test")
        for _ in range(3):
            framework.record_task_outcome("a1", success=True)
        req = framework.check_promotion_eligibility("a1")
        assert req is not None
        assert req.status == PromotionStatus.PENDING


class TestLevelPermissions:
    def test_intern_permissions(self) -> None:
        perms = LEVEL_PERMISSIONS[TrustLevel.INTERN]
        assert PermissionScope.READ_CODE in perms
        assert PermissionScope.WRITE_CODE not in perms

    def test_junior_permissions(self) -> None:
        perms = LEVEL_PERMISSIONS[TrustLevel.JUNIOR]
        assert PermissionScope.WRITE_CODE in perms
        assert PermissionScope.RUN_TESTS in perms

    def test_principal_has_all(self) -> None:
        perms = LEVEL_PERMISSIONS[TrustLevel.PRINCIPAL]
        for p in PermissionScope:
            assert p in perms

    def test_permissions_are_cumulative(self) -> None:
        for i in range(len(TrustLevel) - 1):
            lower = LEVEL_PERMISSIONS[TrustLevel(i)]
            upper = LEVEL_PERMISSIONS[TrustLevel(i + 1)]
            assert lower.issubset(upper)


class TestAnalytics:
    def test_analytics(self, framework_with_agents: AgenticTrustFramework) -> None:
        framework_with_agents.check_permission(
            ActionRequest(agent_id="agent-intern", permission=PermissionScope.READ_CODE),
        )
        stats = framework_with_agents.analytics()
        assert isinstance(stats, TrustAnalytics)
        assert stats.total_agents == 4
        assert stats.total_actions >= 1

    def test_analytics_empty(self, framework: AgenticTrustFramework) -> None:
        stats = framework.analytics()
        assert stats.total_agents == 0

    def test_audit_log(self, framework_with_agents: AgenticTrustFramework) -> None:
        log = framework_with_agents.get_audit_log()
        assert len(log) >= 4  # 4 registrations

    def test_action_log(self, framework_with_agents: AgenticTrustFramework) -> None:
        framework_with_agents.check_permission(
            ActionRequest(agent_id="agent-intern", permission=PermissionScope.READ_CODE),
        )
        actions = framework_with_agents.get_action_log()
        assert len(actions) >= 1
