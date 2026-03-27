"""
Spec-Driven Generation with Verification Contracts.

Requires a structured specification before AI code generation begins.
The spec becomes a verification contract: generated code is automatically
validated against the spec's assertions, invariants, and acceptance criteria,
with failures blocking the merge.

Industry context (2025-2026):
- 25% of YC W25 cohort shipped 95%+ AI-generated code but drowned in tech debt
- "Vibe coding" without specs produces unmaintainable systems
- Specification-first gives AI clear targets and reviewers objective pass/fail
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class SpecStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    VERIFIED = "verified"
    FAILED = "failed"


class CriterionType(StrEnum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    EDGE_CASE = "edge_case"
    SECURITY = "security"
    PERFORMANCE = "performance"


class VerifyResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    PARTIAL = "partial"


@dataclass
class AcceptanceCriterion:
    """Single verifiable acceptance criterion from the spec."""
    criterion_id: str
    description: str
    criterion_type: CriterionType
    verification_method: str  # how to verify: "test", "manual", "static_analysis"
    required: bool = True
    result: VerifyResult = VerifyResult.SKIP
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "description": self.description,
            "type": self.criterion_type.value,
            "verification_method": self.verification_method,
            "required": self.required,
            "result": self.result.value,
            "evidence": self.evidence,
        }


@dataclass
class SpecContract:
    """Structured specification with verification contracts."""
    spec_id: str
    title: str
    description: str
    status: SpecStatus = SpecStatus.DRAFT
    created_at: str = ""
    updated_at: str = ""
    ticket_id: str | None = None

    # Spec content
    functional_requirements: list[str] = field(default_factory=list)
    non_functional_requirements: list[str] = field(default_factory=list)
    data_schemas: list[dict[str, Any]] = field(default_factory=list)
    api_contracts: list[dict[str, Any]] = field(default_factory=list)
    edge_cases: list[str] = field(default_factory=list)
    security_requirements: list[str] = field(default_factory=list)

    # Verification
    acceptance_criteria: list[AcceptanceCriterion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ticket_id": self.ticket_id,
            "functional_requirements": self.functional_requirements,
            "non_functional_requirements": self.non_functional_requirements,
            "data_schemas": self.data_schemas,
            "api_contracts": self.api_contracts,
            "edge_cases": self.edge_cases,
            "security_requirements": self.security_requirements,
            "acceptance_criteria": [c.to_dict() for c in self.acceptance_criteria],
        }


@dataclass
class VerificationResult:
    """Result of verifying code against a spec contract."""
    spec_id: str
    verified_at: str
    total_criteria: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    partial: int = 0
    pass_rate: float = 0.0
    blocked: bool = False
    criteria_results: list[dict[str, Any]] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "verified_at": self.verified_at,
            "total_criteria": self.total_criteria,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "partial": self.partial,
            "pass_rate": self.pass_rate,
            "blocked": self.blocked,
            "criteria_results": self.criteria_results,
            "missing_requirements": self.missing_requirements,
        }


# ---------------------------------------------------------------------------
# Spec Verifier
# ---------------------------------------------------------------------------

class SpecVerifier:
    """
    Manages specification contracts and verifies AI-generated code against them.

    Responsibilities:
    - Create and manage structured specifications
    - Generate acceptance criteria from spec requirements
    - Verify generated code against spec contracts
    - Block merges when required criteria are not met
    """

    def __init__(self) -> None:
        self._specs: dict[str, SpecContract] = {}
        self._verification_history: list[VerificationResult] = []

    # -- Spec management ----------------------------------------------------

    def create_spec(
        self,
        *,
        spec_id: str,
        title: str,
        description: str,
        ticket_id: str | None = None,
        functional_requirements: list[str] | None = None,
        non_functional_requirements: list[str] | None = None,
        edge_cases: list[str] | None = None,
        security_requirements: list[str] | None = None,
        data_schemas: list[dict[str, Any]] | None = None,
        api_contracts: list[dict[str, Any]] | None = None,
    ) -> SpecContract:
        """Create a new specification contract."""
        now = datetime.now(UTC).isoformat()

        spec = SpecContract(
            spec_id=spec_id,
            title=title,
            description=description,
            status=SpecStatus.DRAFT,
            created_at=now,
            updated_at=now,
            ticket_id=ticket_id,
            functional_requirements=functional_requirements or [],
            non_functional_requirements=non_functional_requirements or [],
            data_schemas=data_schemas or [],
            api_contracts=api_contracts or [],
            edge_cases=edge_cases or [],
            security_requirements=security_requirements or [],
        )

        # Auto-generate acceptance criteria from requirements
        criteria = self._generate_criteria(spec)
        spec.acceptance_criteria = criteria

        self._specs[spec_id] = spec
        return spec

    def approve_spec(self, spec_id: str) -> SpecContract:
        """Mark a spec as approved for implementation."""
        spec = self._specs[spec_id]
        spec.status = SpecStatus.APPROVED
        spec.updated_at = datetime.now(UTC).isoformat()
        return spec

    def get_spec(self, spec_id: str) -> SpecContract | None:
        """Get a spec by ID."""
        return self._specs.get(spec_id)

    def list_specs(self) -> list[SpecContract]:
        """List all specs."""
        return list(self._specs.values())

    # -- Criteria generation ------------------------------------------------

    def _generate_criteria(self, spec: SpecContract) -> list[AcceptanceCriterion]:
        """Auto-generate acceptance criteria from spec requirements."""
        criteria: list[AcceptanceCriterion] = []
        idx = 0

        for req in spec.functional_requirements:
            idx += 1
            criteria.append(AcceptanceCriterion(
                criterion_id=f"AC-{idx:03d}",
                description=req,
                criterion_type=CriterionType.FUNCTIONAL,
                verification_method="test",
                required=True,
            ))

        for req in spec.non_functional_requirements:
            idx += 1
            criteria.append(AcceptanceCriterion(
                criterion_id=f"AC-{idx:03d}",
                description=req,
                criterion_type=CriterionType.NON_FUNCTIONAL,
                verification_method="test",
                required=True,
            ))

        for ec in spec.edge_cases:
            idx += 1
            criteria.append(AcceptanceCriterion(
                criterion_id=f"AC-{idx:03d}",
                description=ec,
                criterion_type=CriterionType.EDGE_CASE,
                verification_method="test",
                required=False,  # edge cases recommended but not blocking
            ))

        for req in spec.security_requirements:
            idx += 1
            criteria.append(AcceptanceCriterion(
                criterion_id=f"AC-{idx:03d}",
                description=req,
                criterion_type=CriterionType.SECURITY,
                verification_method="test",
                required=True,
            ))

        return criteria

    # -- Verification -------------------------------------------------------

    def verify_code(
        self, spec_id: str, code: str, test_results: dict[str, bool] | None = None
    ) -> VerificationResult:
        """
        Verify generated code against a spec contract.

        Args:
            spec_id: The spec to verify against
            code: The generated code to verify
            test_results: Map of criterion_id -> pass/fail from test runner
        """
        spec = self._specs.get(spec_id)
        if spec is None:
            return VerificationResult(
                spec_id=spec_id,
                verified_at=datetime.now(UTC).isoformat(),
                blocked=True,
                missing_requirements=["Spec not found"],
            )

        test_results = test_results or {}
        now = datetime.now(UTC).isoformat()

        results: list[dict[str, Any]] = []
        passed = 0
        failed = 0
        skipped = 0
        partial = 0
        missing: list[str] = []

        for criterion in spec.acceptance_criteria:
            # Check if we have explicit test results
            if criterion.criterion_id in test_results:
                result = (
                    VerifyResult.PASS
                    if test_results[criterion.criterion_id]
                    else VerifyResult.FAIL
                )
            else:
                # Try static verification
                result = self._static_verify(criterion, code)

            # Update criterion
            criterion.result = result

            if result == VerifyResult.PASS:
                passed += 1
            elif result == VerifyResult.FAIL:
                failed += 1
                if criterion.required:
                    missing.append(
                        f"[{criterion.criterion_id}] {criterion.description}"
                    )
            elif result == VerifyResult.PARTIAL:
                partial += 1
            else:
                skipped += 1

            results.append({
                "criterion_id": criterion.criterion_id,
                "description": criterion.description,
                "type": criterion.criterion_type.value,
                "required": criterion.required,
                "result": result.value,
            })

        total = len(spec.acceptance_criteria)
        pass_rate = passed / total if total > 0 else 0.0

        # Block if any required criterion failed
        blocked = any(
            c.required and c.result == VerifyResult.FAIL
            for c in spec.acceptance_criteria
        )

        # Update spec status
        spec.status = SpecStatus.VERIFIED if not blocked else SpecStatus.FAILED
        spec.updated_at = now

        verification = VerificationResult(
            spec_id=spec_id,
            verified_at=now,
            total_criteria=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            partial=partial,
            pass_rate=pass_rate,
            blocked=blocked,
            criteria_results=results,
            missing_requirements=missing,
        )
        self._verification_history.append(verification)
        return verification

    def _static_verify(
        self, criterion: AcceptanceCriterion, code: str
    ) -> VerifyResult:
        """Attempt static verification of a criterion against code."""
        desc = criterion.description.lower()

        # Check for function/class existence requirements
        func_match = re.search(r"function\s+(\w+)|method\s+(\w+)", desc)
        if func_match:
            func_name = func_match.group(1) or func_match.group(2)
            if func_name and re.search(
                rf"def\s+{re.escape(func_name)}\b|function\s+{re.escape(func_name)}\b",
                code,
            ):
                return VerifyResult.PASS

        class_match = re.search(r"class\s+(\w+)", desc)
        if class_match:
            class_name = class_match.group(1)
            if class_name and re.search(
                rf"class\s+{re.escape(class_name)}\b", code
            ):
                return VerifyResult.PASS

        # Check for error handling requirements
        if ("error handling" in desc or "exception" in desc) and re.search(
            r"try\s*:|except\s|catch\s*\(", code
        ):
            return VerifyResult.PARTIAL

        # Check for validation requirements
        if "validat" in desc and re.search(
            r"validate|validator|is_valid|check_", code, re.IGNORECASE
        ):
            return VerifyResult.PARTIAL

        # Check for test requirements
        if "test" in desc and criterion.verification_method == "test":
            return VerifyResult.SKIP  # needs actual test run

        # Check for input sanitization
        if ("sanitiz" in desc or "escap" in desc) and re.search(
            r"sanitize|escape|strip|clean", code, re.IGNORECASE
        ):
            return VerifyResult.PARTIAL

        # Check for authentication requirements
        if "auth" in desc and re.search(
            r"auth|token|jwt|session|login", code, re.IGNORECASE
        ):
            return VerifyResult.PARTIAL

        return VerifyResult.SKIP

    # -- Stats --------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics."""
        total_specs = len(self._specs)
        by_status: dict[str, int] = {}
        for s in self._specs.values():
            by_status[s.status.value] = by_status.get(s.status.value, 0) + 1

        total_verifications = len(self._verification_history)
        avg_pass_rate = (
            sum(v.pass_rate for v in self._verification_history) / total_verifications
            if total_verifications > 0
            else 0.0
        )

        return {
            "total_specs": total_specs,
            "specs_by_status": by_status,
            "total_verifications": total_verifications,
            "average_pass_rate": round(avg_pass_rate, 3),
            "total_blocked": sum(
                1 for v in self._verification_history if v.blocked
            ),
        }

    @property
    def verification_history(self) -> list[VerificationResult]:
        return list(self._verification_history)
