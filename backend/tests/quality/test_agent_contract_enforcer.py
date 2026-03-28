"""Tests for Agent Contract Enforcer."""

from __future__ import annotations

from app.quality.agent_contract_enforcer import (
    AgentContractEnforcer,
    ContractStatus,
    EnforcerConfig,
    GateDecision,
    ResourceLimits,
    ResourceUsage,
    ViolationType,
    _check_conservation_law,
    _check_violations,
    _compute_utilisation,
    _gate_from_utilisation,
    _remaining_limits,
)

# ── Helper factories ──────────────────────────────────────────────────────


def _make_enforcer(**overrides) -> AgentContractEnforcer:
    config = EnforcerConfig(**overrides) if overrides else None
    return AgentContractEnforcer(config)


def _small_limits() -> ResourceLimits:
    return ResourceLimits(
        max_tokens=1000,
        max_api_calls=10,
        max_wall_clock_seconds=60.0,
        max_cost_usd=1.0,
    )


# ── Pure helper tests ─────────────────────────────────────────────────────


class TestComputeUtilisation:
    def test_zero_usage(self):
        usage = ResourceUsage()
        limits = ResourceLimits(max_tokens=100)
        util = _compute_utilisation(usage, limits)
        assert util["tokens"] == 0.0

    def test_half_usage(self):
        usage = ResourceUsage(tokens_used=500)
        limits = ResourceLimits(max_tokens=1000)
        util = _compute_utilisation(usage, limits)
        assert util["tokens"] == 0.5

    def test_full_usage(self):
        usage = ResourceUsage(
            tokens_used=1000,
            api_calls_made=50,
            elapsed_seconds=300.0,
            cost_usd=5.0,
        )
        limits = ResourceLimits()
        util = _compute_utilisation(usage, limits)
        assert util["tokens"] == 0.01  # 1000/100000

    def test_zero_limits(self):
        usage = ResourceUsage(tokens_used=10)
        limits = ResourceLimits(max_tokens=0)
        util = _compute_utilisation(usage, limits)
        assert util["tokens"] == 0.0


class TestCheckViolations:
    def test_no_violations(self):
        usage = ResourceUsage(tokens_used=50)
        limits = ResourceLimits(max_tokens=100)
        violations = _check_violations(usage, limits)
        assert len(violations) == 0

    def test_token_violation(self):
        usage = ResourceUsage(tokens_used=200)
        limits = ResourceLimits(max_tokens=100)
        violations = _check_violations(usage, limits)
        assert len(violations) == 1
        assert violations[0].violation_type == ViolationType.TOKEN_LIMIT

    def test_multiple_violations(self):
        usage = ResourceUsage(
            tokens_used=2000,
            api_calls_made=100,
            elapsed_seconds=999.0,
            cost_usd=99.0,
        )
        limits = _small_limits()
        violations = _check_violations(usage, limits)
        assert len(violations) == 4

    def test_cost_violation(self):
        usage = ResourceUsage(cost_usd=10.0)
        limits = ResourceLimits(max_cost_usd=5.0)
        violations = _check_violations(usage, limits)
        assert violations[0].violation_type == ViolationType.COST_LIMIT


class TestCheckConservationLaw:
    def test_within_budget(self):
        parent = ResourceLimits(
            max_tokens=1000, max_api_calls=10, max_cost_usd=5.0,
        )
        child = ResourceLimits(
            max_tokens=500, max_api_calls=5, max_cost_usd=2.0,
        )
        ok, reason = _check_conservation_law(parent, child)
        assert ok

    def test_exceeds_tokens(self):
        parent = ResourceLimits(max_tokens=100)
        child = ResourceLimits(max_tokens=200)
        ok, reason = _check_conservation_law(parent, child)
        assert not ok
        assert "tokens" in reason.lower()

    def test_exceeds_api_calls(self):
        parent = ResourceLimits(max_api_calls=5)
        child = ResourceLimits(max_api_calls=10)
        ok, _ = _check_conservation_law(parent, child)
        assert not ok

    def test_exceeds_cost(self):
        parent = ResourceLimits(max_cost_usd=1.0)
        child = ResourceLimits(max_cost_usd=2.0)
        ok, _ = _check_conservation_law(parent, child)
        assert not ok


class TestRemainingLimits:
    def test_no_usage(self):
        from app.quality.agent_contract_enforcer import Contract
        c = Contract(
            limits=ResourceLimits(max_tokens=1000),
            usage=ResourceUsage(),
        )
        rem = _remaining_limits(c)
        assert rem.max_tokens == 1000

    def test_partial_usage(self):
        from app.quality.agent_contract_enforcer import Contract
        c = Contract(
            limits=ResourceLimits(max_tokens=1000, max_cost_usd=5.0),
            usage=ResourceUsage(tokens_used=300, cost_usd=2.0),
        )
        rem = _remaining_limits(c)
        assert rem.max_tokens == 700
        assert rem.max_cost_usd == 3.0

    def test_over_usage_clamps_zero(self):
        from app.quality.agent_contract_enforcer import Contract
        c = Contract(
            limits=ResourceLimits(max_tokens=100),
            usage=ResourceUsage(tokens_used=200),
        )
        rem = _remaining_limits(c)
        assert rem.max_tokens == 0


class TestGateFromUtilisation:
    def test_low_util(self):
        util = {"tokens": 0.3, "cost": 0.2}
        assert _gate_from_utilisation(util, 0.8, 1.0) == GateDecision.PASS

    def test_soft_threshold(self):
        util = {"tokens": 0.85}
        assert _gate_from_utilisation(util, 0.8, 1.0) == GateDecision.WARN

    def test_hard_threshold(self):
        util = {"tokens": 1.1}
        assert _gate_from_utilisation(util, 0.8, 1.0) == GateDecision.BLOCK

    def test_empty(self):
        assert _gate_from_utilisation({}, 0.8, 1.0) == GateDecision.PASS


# ── Enforcer class tests ─────────────────────────────────────────────────


class TestCreateContract:
    def test_basic_creation(self):
        e = _make_enforcer()
        cid, msg = e.create_contract("agent-1")
        assert cid
        assert "created" in msg.lower()

    def test_with_custom_limits(self):
        e = _make_enforcer()
        limits = _small_limits()
        cid, _ = e.create_contract("agent-1", limits=limits)
        c = e.get_contract(cid)
        assert c.limits.max_tokens == 1000

    def test_with_parent(self):
        e = _make_enforcer()
        pid, _ = e.create_contract(
            "parent",
            limits=ResourceLimits(max_tokens=10000),
        )
        cid, msg = e.create_contract(
            "child",
            limits=ResourceLimits(max_tokens=5000),
            parent_contract_id=pid,
        )
        assert cid

    def test_conservation_violation(self):
        e = _make_enforcer()
        pid, _ = e.create_contract(
            "parent",
            limits=ResourceLimits(max_tokens=100),
        )
        cid, msg = e.create_contract(
            "child",
            limits=ResourceLimits(max_tokens=200),
            parent_contract_id=pid,
        )
        assert not cid
        assert "exceeds" in msg.lower()

    def test_parent_not_found(self):
        e = _make_enforcer()
        cid, msg = e.create_contract(
            "child",
            parent_contract_id="nonexistent",
        )
        assert not cid


class TestActivate:
    def test_activate_proposed(self):
        e = _make_enforcer()
        cid, _ = e.create_contract("agent-1")
        ok, msg = e.activate(cid)
        assert ok
        assert e.get_contract(cid).status == ContractStatus.ACTIVE

    def test_activate_not_found(self):
        e = _make_enforcer()
        ok, _ = e.activate("nope")
        assert not ok

    def test_double_activate(self):
        e = _make_enforcer()
        cid, _ = e.create_contract("agent-1")
        e.activate(cid)
        ok, msg = e.activate(cid)
        assert not ok


class TestRecordUsage:
    def test_within_limits(self):
        e = _make_enforcer()
        cid, _ = e.create_contract(
            "agent-1", limits=_small_limits(),
        )
        check = e.record_usage(cid, tokens=100)
        assert check.within_limits
        assert check.gate == GateDecision.PASS

    def test_exceeds_limit(self):
        e = _make_enforcer()
        cid, _ = e.create_contract(
            "agent-1", limits=_small_limits(),
        )
        check = e.record_usage(cid, tokens=2000)
        assert not check.within_limits
        assert check.gate == GateDecision.BLOCK
        assert len(check.violations) > 0

    def test_cumulative_usage(self):
        e = _make_enforcer()
        cid, _ = e.create_contract(
            "agent-1", limits=_small_limits(),
        )
        e.record_usage(cid, tokens=600)
        check = e.record_usage(cid, tokens=600)
        assert not check.within_limits

    def test_soft_threshold_warns(self):
        e = _make_enforcer(soft_threshold=0.8)
        cid, _ = e.create_contract(
            "agent-1", limits=_small_limits(),
        )
        check = e.record_usage(cid, tokens=850)
        assert check.within_limits
        assert check.gate == GateDecision.WARN

    def test_not_found(self):
        e = _make_enforcer()
        check = e.record_usage("nope", tokens=1)
        assert not check.within_limits

    def test_auto_suspend(self):
        e = _make_enforcer(auto_suspend_on_violation=True)
        cid, _ = e.create_contract(
            "agent-1", limits=_small_limits(),
        )
        e.record_usage(cid, tokens=2000)
        c = e.get_contract(cid)
        assert c.status == ContractStatus.SUSPENDED


class TestComplete:
    def test_complete_active(self):
        e = _make_enforcer()
        cid, _ = e.create_contract("agent-1")
        e.activate(cid)
        ok, msg = e.complete(cid)
        assert ok

    def test_complete_not_found(self):
        e = _make_enforcer()
        ok, _ = e.complete("nope")
        assert not ok


class TestDelegate:
    def test_successful_delegation(self):
        e = _make_enforcer()
        pid, _ = e.create_contract(
            "parent",
            limits=ResourceLimits(max_tokens=10000),
        )
        result = e.delegate(
            pid, "child",
            ResourceLimits(max_tokens=5000),
        )
        assert result.allowed
        assert result.child_contract_id

    def test_delegation_exceeds_budget(self):
        e = _make_enforcer()
        pid, _ = e.create_contract(
            "parent",
            limits=ResourceLimits(max_tokens=100),
        )
        result = e.delegate(
            pid, "child",
            ResourceLimits(max_tokens=200),
        )
        assert not result.allowed

    def test_delegation_parent_not_found(self):
        e = _make_enforcer()
        result = e.delegate(
            "nope", "child",
            ResourceLimits(),
        )
        assert not result.allowed


class TestEnforcerReport:
    def test_empty(self):
        e = _make_enforcer()
        report = e.enforcer_report()
        assert report.total_contracts == 0
        assert report.gate == GateDecision.PASS

    def test_with_contracts(self):
        e = _make_enforcer()
        cid1, _ = e.create_contract("a")
        e.activate(cid1)
        cid2, _ = e.create_contract("b")
        e.activate(cid2)
        e.complete(cid2)
        report = e.enforcer_report()
        assert report.total_contracts == 2
        assert report.active == 1
        assert report.completed == 1

    def test_violated_blocks(self):
        e = _make_enforcer()
        cid, _ = e.create_contract(
            "a", limits=_small_limits(),
        )
        e.record_usage(cid, tokens=5000)
        report = e.enforcer_report()
        assert report.violated == 1
        assert report.gate == GateDecision.BLOCK
