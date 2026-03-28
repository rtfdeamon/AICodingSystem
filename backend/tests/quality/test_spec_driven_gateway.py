"""Tests for Spec-Driven Development Gateway."""

from __future__ import annotations

from app.quality.spec_driven_gateway import (
    GateDecision,
    GatewayConfig,
    IOContract,
    RigorLevel,
    Scenario,
    ScenarioKind,
    Spec,
    SpecDrivenGateway,
    SpecStatus,
    _compute_drift,
    _content_hash,
    _decompose_to_tasks,
    _gate_from_stats,
    _validate_spec,
)

# ── Helper factories ──────────────────────────────────────────────────────


def _make_gateway(**overrides) -> SpecDrivenGateway:
    config = GatewayConfig(**overrides) if overrides else None
    return SpecDrivenGateway(config)


_SENTINEL: list = None  # type: ignore[assignment]


def _make_scenario(
    kind: ScenarioKind = ScenarioKind.GIVEN_WHEN_THEN,
    description: str = "User logs in",
    preconditions: list[str] | None = _SENTINEL,
    actions: list[str] | None = _SENTINEL,
    outcomes: list[str] | None = _SENTINEL,
) -> Scenario:
    return Scenario(
        kind=kind,
        description=description,
        preconditions=(
            ["User exists"] if preconditions is _SENTINEL
            else (preconditions or [])
        ),
        actions=(
            ["Submit credentials"] if actions is _SENTINEL
            else (actions or [])
        ),
        expected_outcomes=(
            ["Token returned"] if outcomes is _SENTINEL
            else (outcomes or [])
        ),
    )


def _make_spec(
    title: str = "Auth Feature",
    scenarios: list[Scenario] | None = _SENTINEL,
    io_contract: IOContract | None = _SENTINEL,
) -> Spec:
    return Spec(
        title=title,
        description="Authentication feature",
        scenarios=(
            [_make_scenario()] if scenarios is _SENTINEL
            else (scenarios or [])
        ),
        io_contract=(
            IOContract(
                input_types={"username": "str", "password": "str"},
                output_type="AuthToken",
            )
            if io_contract is _SENTINEL
            else io_contract
        ),
    )


DEFAULT_CONFIG = GatewayConfig()


# ── Pure helper tests ─────────────────────────────────────────────────────


class TestContentHash:
    def test_deterministic(self):
        spec = _make_spec()
        h1 = _content_hash(spec)
        h2 = _content_hash(spec)
        assert h1 == h2
        assert len(h1) == 16

    def test_different_titles(self):
        s1 = _make_spec(title="A")
        s2 = _make_spec(title="B")
        assert _content_hash(s1) != _content_hash(s2)

    def test_no_contract(self):
        spec = _make_spec(io_contract=None)
        spec.io_contract = None
        h = _content_hash(spec)
        assert len(h) == 16


class TestValidateSpec:
    def test_valid_spec(self):
        spec = _make_spec()
        result = _validate_spec(spec, DEFAULT_CONFIG)
        assert result.valid
        assert result.gate == GateDecision.PASS

    def test_empty_title(self):
        spec = _make_spec(title="")
        result = _validate_spec(spec, DEFAULT_CONFIG)
        assert not result.valid
        assert "title is empty" in result.errors[0]

    def test_no_scenarios(self):
        spec = _make_spec(scenarios=[])
        result = _validate_spec(spec, DEFAULT_CONFIG)
        assert not result.valid
        assert result.gate == GateDecision.BLOCK

    def test_missing_io_contract_source_of_truth(self):
        config = GatewayConfig(rigor=RigorLevel.SOURCE_OF_TRUTH)
        spec = _make_spec()
        spec.io_contract = None
        result = _validate_spec(spec, config)
        assert not result.valid

    def test_missing_io_contract_anchored_warns(self):
        config = GatewayConfig(rigor=RigorLevel.ANCHORED)
        spec = _make_spec()
        spec.io_contract = None
        result = _validate_spec(spec, config)
        assert result.valid
        assert result.gate == GateDecision.WARN

    def test_gwt_no_outcomes(self):
        sc = _make_scenario(outcomes=[])
        spec = _make_spec(scenarios=[sc])
        result = _validate_spec(spec, DEFAULT_CONFIG)
        assert not result.valid

    def test_gwt_no_preconditions_warns(self):
        sc = _make_scenario(preconditions=[])
        spec = _make_spec(scenarios=[sc])
        result = _validate_spec(spec, DEFAULT_CONFIG)
        assert result.valid
        assert len(result.warnings) > 0

    def test_empty_scenario_description(self):
        sc = _make_scenario(description="")
        spec = _make_spec(scenarios=[sc])
        result = _validate_spec(spec, DEFAULT_CONFIG)
        assert not result.valid

    def test_io_scenario_valid(self):
        sc = Scenario(
            kind=ScenarioKind.INPUT_OUTPUT,
            description="Transform data",
        )
        spec = _make_spec(scenarios=[sc])
        result = _validate_spec(spec, DEFAULT_CONFIG)
        assert result.valid


class TestDecomposeToTasks:
    def test_single_scenario(self):
        spec = _make_spec()
        tasks = _decompose_to_tasks(spec, max_depth=10)
        assert len(tasks) >= 1
        assert "Implement" in tasks[0].title

    def test_with_io_contract(self):
        spec = _make_spec()
        tasks = _decompose_to_tasks(spec, max_depth=10)
        contract_task = [
            t for t in tasks if "I/O contract" in t.title
        ]
        assert len(contract_task) == 1

    def test_max_depth_limit(self):
        scenarios = [_make_scenario(description=f"S{i}") for i in range(20)]
        spec = _make_spec(scenarios=scenarios)
        tasks = _decompose_to_tasks(spec, max_depth=5)
        assert len(tasks) <= 6  # 5 + possibly IO contract

    def test_dependency_chain(self):
        scenarios = [
            _make_scenario(description="Step A"),
            _make_scenario(description="Step B"),
        ]
        spec = _make_spec(scenarios=scenarios)
        tasks = _decompose_to_tasks(spec, max_depth=10)
        assert len(tasks[1].depends_on) > 0

    def test_no_scenarios(self):
        spec = _make_spec(scenarios=[])
        tasks = _decompose_to_tasks(spec, max_depth=10)
        assert len(tasks) == 1  # Only IO contract


class TestComputeDrift:
    def test_no_drift(self):
        spec = _make_spec(
            scenarios=[_make_scenario(description="login")],
        )
        report = _compute_drift(spec, ["login"])
        assert report.drift_score == 0.0
        assert report.gate == GateDecision.PASS

    def test_missing_scenario(self):
        spec = _make_spec(
            scenarios=[
                _make_scenario(description="login"),
                _make_scenario(description="logout"),
            ],
        )
        report = _compute_drift(spec, ["login"])
        assert report.drift_score > 0
        assert len(report.missing_scenarios) == 1

    def test_extra_behaviour(self):
        spec = _make_spec(
            scenarios=[_make_scenario(description="login")],
        )
        report = _compute_drift(spec, ["login", "extra feature"])
        assert len(report.extra_behaviours) == 1

    def test_high_drift_blocks(self):
        spec = _make_spec(
            scenarios=[
                _make_scenario(description="a"),
                _make_scenario(description="b"),
                _make_scenario(description="c"),
            ],
        )
        report = _compute_drift(spec, ["x", "y", "z"])
        assert report.gate == GateDecision.BLOCK

    def test_contract_mismatch(self):
        contract = IOContract(
            input_types={"x": "int"},
            output_type="int",
            constraints=["must be positive"],
        )
        spec = _make_spec(
            scenarios=[_make_scenario(description="calc")],
            io_contract=contract,
        )
        report = _compute_drift(spec, ["calc"])
        assert len(report.contract_mismatches) == 1

    def test_empty(self):
        spec = _make_spec(scenarios=[])
        report = _compute_drift(spec, [])
        assert report.drift_score == 0.0


class TestGateFromStats:
    def test_empty(self):
        assert _gate_from_stats(0, 0, 0) == GateDecision.PASS

    def test_all_validated(self):
        assert _gate_from_stats(5, 5, 0) == GateDecision.PASS

    def test_drifted(self):
        assert _gate_from_stats(5, 5, 1) == GateDecision.WARN

    def test_not_all_validated(self):
        assert _gate_from_stats(3, 5, 0) == GateDecision.WARN


# ── Gateway class tests ───────────────────────────────────────────────────


class TestRegisterSpec:
    def test_valid_spec(self):
        gw = _make_gateway()
        spec = _make_spec()
        sid, result = gw.register_spec(spec)
        assert sid
        assert result.valid
        assert gw.get_spec(sid).status == SpecStatus.VALIDATED

    def test_invalid_spec(self):
        gw = _make_gateway()
        spec = _make_spec(title="")
        sid, result = gw.register_spec(spec)
        assert not result.valid
        assert gw.get_spec(sid).status == SpecStatus.DRAFT

    def test_content_hash_set(self):
        gw = _make_gateway()
        spec = _make_spec()
        sid, _ = gw.register_spec(spec)
        assert gw.get_spec(sid).content_hash


class TestApproveSpec:
    def test_approve_validated(self):
        gw = _make_gateway()
        spec = _make_spec()
        sid, _ = gw.register_spec(spec)
        ok, msg = gw.approve_spec(sid)
        assert ok
        assert gw.get_spec(sid).status == SpecStatus.APPROVED

    def test_approve_draft_fails(self):
        gw = _make_gateway()
        spec = _make_spec(title="")
        sid, _ = gw.register_spec(spec)
        ok, msg = gw.approve_spec(sid)
        assert not ok

    def test_approve_not_found(self):
        gw = _make_gateway()
        ok, msg = gw.approve_spec("nonexistent")
        assert not ok


class TestDecompose:
    def test_approved_spec(self):
        gw = _make_gateway()
        spec = _make_spec()
        sid, _ = gw.register_spec(spec)
        gw.approve_spec(sid)
        tasks = gw.decompose(sid)
        assert len(tasks) > 0

    def test_unapproved_blocked_at_anchored(self):
        gw = _make_gateway(rigor=RigorLevel.ANCHORED)
        spec = _make_spec()
        sid, _ = gw.register_spec(spec)
        tasks = gw.decompose(sid)
        assert len(tasks) == 0

    def test_guidance_allows_validated(self):
        gw = _make_gateway(rigor=RigorLevel.GUIDANCE)
        spec = _make_spec()
        sid, _ = gw.register_spec(spec)
        tasks = gw.decompose(sid)
        assert len(tasks) > 0

    def test_not_found(self):
        gw = _make_gateway()
        assert gw.decompose("nope") == []


class TestCheckDrift:
    def test_no_drift(self):
        gw = _make_gateway()
        spec = _make_spec(
            scenarios=[_make_scenario(description="login")],
        )
        sid, _ = gw.register_spec(spec)
        report = gw.check_drift(sid, ["login"])
        assert report.drift_score == 0.0
        assert gw.get_spec(sid).status == SpecStatus.IMPLEMENTED

    def test_high_drift_marks_drifted(self):
        gw = _make_gateway(drift_threshold=0.1)
        spec = _make_spec(
            scenarios=[
                _make_scenario(description="a"),
                _make_scenario(description="b"),
            ],
        )
        sid, _ = gw.register_spec(spec)
        gw.check_drift(sid, ["x"])
        assert gw.get_spec(sid).status == SpecStatus.DRIFTED

    def test_not_found(self):
        gw = _make_gateway()
        assert gw.check_drift("nope", []) is None


class TestGatewayReport:
    def test_empty(self):
        gw = _make_gateway()
        report = gw.gateway_report()
        assert report.total_specs == 0
        assert report.gate == GateDecision.PASS

    def test_with_specs(self):
        gw = _make_gateway()
        s1 = _make_spec(title="A")
        s2 = _make_spec(title="B")
        gw.register_spec(s1)
        gw.register_spec(s2)
        gw.approve_spec(s1.spec_id)
        report = gw.gateway_report()
        assert report.total_specs == 2
        assert report.validated == 2
        assert report.approved == 1

    def test_list_specs(self):
        gw = _make_gateway()
        gw.register_spec(_make_spec())
        assert len(gw.list_specs()) == 1
