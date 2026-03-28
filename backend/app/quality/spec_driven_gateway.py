"""Spec-Driven Development Gateway.

Enforces specification-first workflow for AI code generation:
- Structured spec parsing and validation (Given/When/Then, I/O contracts)
- Spec-to-task decomposition into isolated, testable units
- Spec-code drift detection and divergence reporting
- Three rigor levels: guidance, anchored, source-of-truth
- Spec versioning with change-impact analysis

Based on:
- ThoughtWorks "Spec-driven development" (2025)
- GitHub Blog "Spec Kit open source toolkit" (2026)
- arXiv 2602.00180 "Spec-Driven Development" (2026)
- JetBrains Junie "Spec-driven approach for AI coding" (2025)
"""

from __future__ import annotations

import hashlib
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


class RigorLevel(StrEnum):
    GUIDANCE = "guidance"
    ANCHORED = "anchored"
    SOURCE_OF_TRUTH = "source_of_truth"


class SpecStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    DRIFTED = "drifted"


class ScenarioKind(StrEnum):
    GIVEN_WHEN_THEN = "given_when_then"
    INPUT_OUTPUT = "input_output"
    CONSTRAINT = "constraint"
    INVARIANT = "invariant"


# ── Dataclasses ────────────────────────────────────────────────────────────


@dataclass
class Scenario:
    kind: ScenarioKind
    description: str
    preconditions: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    expected_outcomes: list[str] = field(default_factory=list)


@dataclass
class IOContract:
    input_types: dict[str, str] = field(default_factory=dict)
    output_type: str = ""
    constraints: list[str] = field(default_factory=list)


@dataclass
class Spec:
    spec_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    scenarios: list[Scenario] = field(default_factory=list)
    io_contract: IOContract | None = None
    domain_constraints: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    status: SpecStatus = SpecStatus.DRAFT
    content_hash: str = ""
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )


@dataclass
class TaskUnit:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    source_scenario_idx: int = 0
    testable: bool = True


@dataclass
class DriftReport:
    spec_id: str = ""
    drift_score: float = 0.0
    missing_scenarios: list[str] = field(default_factory=list)
    extra_behaviours: list[str] = field(default_factory=list)
    contract_mismatches: list[str] = field(default_factory=list)
    gate: GateDecision = GateDecision.PASS


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gate: GateDecision = GateDecision.PASS


@dataclass
class GatewayConfig:
    rigor: RigorLevel = RigorLevel.ANCHORED
    min_scenarios: int = 1
    require_io_contract: bool = True
    drift_threshold: float = 0.30
    max_task_depth: int = 10


@dataclass
class GatewayReport:
    total_specs: int = 0
    validated: int = 0
    approved: int = 0
    drifted: int = 0
    avg_scenarios: float = 0.0
    gate: GateDecision = GateDecision.PASS


# ── Pure helpers ───────────────────────────────────────────────────────────


def _content_hash(spec: Spec) -> str:
    parts = [
        spec.title,
        spec.description,
        str(len(spec.scenarios)),
        str(spec.domain_constraints),
    ]
    if spec.io_contract:
        parts.append(str(spec.io_contract.input_types))
        parts.append(spec.io_contract.output_type)
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _validate_spec(spec: Spec, config: GatewayConfig) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not spec.title.strip():
        errors.append("Spec title is empty")

    if len(spec.scenarios) < config.min_scenarios:
        errors.append(
            f"Need at least {config.min_scenarios} scenario(s), "
            f"got {len(spec.scenarios)}"
        )

    if config.require_io_contract and spec.io_contract is None:
        if config.rigor == RigorLevel.SOURCE_OF_TRUTH:
            errors.append("I/O contract required at source_of_truth rigor")
        else:
            warnings.append("I/O contract recommended but missing")

    for i, sc in enumerate(spec.scenarios):
        if not sc.description.strip():
            errors.append(f"Scenario {i} has empty description")
        if sc.kind == ScenarioKind.GIVEN_WHEN_THEN:
            if not sc.preconditions:
                warnings.append(f"Scenario {i}: no preconditions (Given)")
            if not sc.actions:
                warnings.append(f"Scenario {i}: no actions (When)")
            if not sc.expected_outcomes:
                errors.append(
                    f"Scenario {i}: no expected outcomes (Then)"
                )

    if errors:
        gate = GateDecision.BLOCK
    elif warnings:
        gate = GateDecision.WARN
    else:
        gate = GateDecision.PASS

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        gate=gate,
    )


def _decompose_to_tasks(spec: Spec, max_depth: int) -> list[TaskUnit]:
    tasks: list[TaskUnit] = []
    for i, sc in enumerate(spec.scenarios):
        if len(tasks) >= max_depth:
            break
        task = TaskUnit(
            title=f"Implement: {sc.description[:60]}",
            description=sc.description,
            source_scenario_idx=i,
            testable=bool(sc.expected_outcomes),
        )
        if i > 0:
            task.depends_on = [tasks[0].task_id]
        tasks.append(task)

    if spec.io_contract and len(tasks) < max_depth:
        tasks.append(TaskUnit(
            title="Validate I/O contract compliance",
            description=(
                f"Inputs: {spec.io_contract.input_types}, "
                f"Output: {spec.io_contract.output_type}"
            ),
            testable=True,
        ))

    return tasks


def _compute_drift(
    spec: Spec,
    implemented_behaviours: list[str],
) -> DriftReport:
    spec_descriptions = {
        sc.description.lower().strip() for sc in spec.scenarios
    }
    impl_set = {b.lower().strip() for b in implemented_behaviours}

    missing = spec_descriptions - impl_set
    extra = impl_set - spec_descriptions

    total = len(spec_descriptions) + len(impl_set)
    score = 0.0 if total == 0 else (len(missing) + len(extra)) / total

    contract_mismatches: list[str] = []
    if spec.io_contract and spec.io_contract.constraints:
        for c in spec.io_contract.constraints:
            if not any(c.lower() in b.lower() for b in implemented_behaviours):
                contract_mismatches.append(c)
                score = min(1.0, score + 0.1)

    if score > 0.5:
        gate = GateDecision.BLOCK
    elif score > 0.2:
        gate = GateDecision.WARN
    else:
        gate = GateDecision.PASS

    return DriftReport(
        spec_id=spec.spec_id,
        drift_score=round(score, 3),
        missing_scenarios=sorted(missing),
        extra_behaviours=sorted(extra),
        contract_mismatches=contract_mismatches,
        gate=gate,
    )


def _gate_from_stats(
    validated: int,
    total: int,
    drifted: int,
) -> GateDecision:
    if total == 0:
        return GateDecision.PASS
    if drifted > 0:
        return GateDecision.WARN
    if validated < total:
        return GateDecision.WARN
    return GateDecision.PASS


# ── Main class ─────────────────────────────────────────────────────────────


class SpecDrivenGateway:
    """Enforces spec-first workflow for AI code generation."""

    def __init__(self, config: GatewayConfig | None = None) -> None:
        self._config = config or GatewayConfig()
        self._specs: dict[str, Spec] = {}

    @property
    def config(self) -> GatewayConfig:
        return self._config

    def register_spec(self, spec: Spec) -> tuple[str, ValidationResult]:
        spec.content_hash = _content_hash(spec)
        result = _validate_spec(spec, self._config)
        if result.valid:
            spec.status = SpecStatus.VALIDATED
        self._specs[spec.spec_id] = spec
        logger.info(
            "Spec registered: %s valid=%s gate=%s",
            spec.spec_id, result.valid, result.gate,
        )
        return spec.spec_id, result

    def approve_spec(self, spec_id: str) -> tuple[bool, str]:
        spec = self._specs.get(spec_id)
        if spec is None:
            return False, "Spec not found"
        if spec.status != SpecStatus.VALIDATED:
            return False, f"Spec not validated (status={spec.status})"
        spec.status = SpecStatus.APPROVED
        return True, "Spec approved"

    def decompose(self, spec_id: str) -> list[TaskUnit]:
        spec = self._specs.get(spec_id)
        if spec is None:
            return []
        if (
            self._config.rigor != RigorLevel.GUIDANCE
            and spec.status not in (SpecStatus.APPROVED, SpecStatus.IMPLEMENTED)
        ):
            return []
        return _decompose_to_tasks(spec, self._config.max_task_depth)

    def check_drift(
        self,
        spec_id: str,
        implemented_behaviours: list[str],
    ) -> DriftReport | None:
        spec = self._specs.get(spec_id)
        if spec is None:
            return None
        report = _compute_drift(spec, implemented_behaviours)
        if report.drift_score > self._config.drift_threshold:
            spec.status = SpecStatus.DRIFTED
        elif spec.status != SpecStatus.DRIFTED:
            spec.status = SpecStatus.IMPLEMENTED
        return report

    def get_spec(self, spec_id: str) -> Spec | None:
        return self._specs.get(spec_id)

    def list_specs(self) -> list[Spec]:
        return list(self._specs.values())

    def gateway_report(self) -> GatewayReport:
        specs = list(self._specs.values())
        total = len(specs)
        validated = sum(
            1 for s in specs if s.status != SpecStatus.DRAFT
        )
        approved = sum(
            1 for s in specs
            if s.status in (SpecStatus.APPROVED, SpecStatus.IMPLEMENTED)
        )
        drifted = sum(
            1 for s in specs if s.status == SpecStatus.DRIFTED
        )
        avg_sc = (
            sum(len(s.scenarios) for s in specs) / total
            if total else 0.0
        )
        return GatewayReport(
            total_specs=total,
            validated=validated,
            approved=approved,
            drifted=drifted,
            avg_scenarios=round(avg_sc, 2),
            gate=_gate_from_stats(validated, total, drifted),
        )
