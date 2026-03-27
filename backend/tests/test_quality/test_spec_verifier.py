"""Tests for Spec-Driven Generation with Verification Contracts."""

import pytest

from app.quality.spec_verifier import (
    CriterionType,
    SpecContract,
    SpecStatus,
    SpecVerifier,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def verifier():
    return SpecVerifier()


@pytest.fixture
def sample_spec(verifier: SpecVerifier):
    return verifier.create_spec(
        spec_id="SPEC-001",
        title="User authentication module",
        description="Implement login/register with JWT",
        ticket_id="TICKET-42",
        functional_requirements=[
            "Implement function login that accepts username and password",
            "Implement function register that creates a new user",
            "Return JWT token on successful login",
        ],
        non_functional_requirements=[
            "Response time under 200ms",
        ],
        edge_cases=[
            "Handle empty username gracefully",
            "Handle duplicate registration",
        ],
        security_requirements=[
            "Hash passwords before storage",
            "Validate JWT token on every request",
        ],
    )


# ---------------------------------------------------------------------------
# Spec creation tests
# ---------------------------------------------------------------------------

class TestSpecCreation:
    def test_create_basic_spec(self, verifier: SpecVerifier):
        spec = verifier.create_spec(
            spec_id="SPEC-001",
            title="Test spec",
            description="A test specification",
        )
        assert spec.spec_id == "SPEC-001"
        assert spec.title == "Test spec"
        assert spec.status == SpecStatus.DRAFT
        assert spec.created_at != ""

    def test_create_spec_with_requirements(self, sample_spec: SpecContract):
        assert len(sample_spec.functional_requirements) == 3
        assert len(sample_spec.non_functional_requirements) == 1
        assert len(sample_spec.edge_cases) == 2
        assert len(sample_spec.security_requirements) == 2

    def test_auto_generate_criteria(self, sample_spec: SpecContract):
        # 3 functional + 1 non-functional + 2 edge cases + 2 security = 8
        assert len(sample_spec.acceptance_criteria) == 8

    def test_criteria_types(self, sample_spec: SpecContract):
        types = {c.criterion_type for c in sample_spec.acceptance_criteria}
        assert CriterionType.FUNCTIONAL in types
        assert CriterionType.NON_FUNCTIONAL in types
        assert CriterionType.EDGE_CASE in types
        assert CriterionType.SECURITY in types

    def test_edge_cases_not_required(self, sample_spec: SpecContract):
        edge_criteria = [
            c for c in sample_spec.acceptance_criteria
            if c.criterion_type == CriterionType.EDGE_CASE
        ]
        for c in edge_criteria:
            assert c.required is False

    def test_functional_criteria_required(self, sample_spec: SpecContract):
        func_criteria = [
            c for c in sample_spec.acceptance_criteria
            if c.criterion_type == CriterionType.FUNCTIONAL
        ]
        for c in func_criteria:
            assert c.required is True

    def test_criteria_ids_unique(self, sample_spec: SpecContract):
        ids = [c.criterion_id for c in sample_spec.acceptance_criteria]
        assert len(ids) == len(set(ids))

    def test_approve_spec(self, verifier: SpecVerifier, sample_spec: SpecContract):
        verifier.approve_spec("SPEC-001")
        spec = verifier.get_spec("SPEC-001")
        assert spec is not None
        assert spec.status == SpecStatus.APPROVED

    def test_get_nonexistent_spec(self, verifier: SpecVerifier):
        assert verifier.get_spec("NONEXISTENT") is None

    def test_list_specs(self, verifier: SpecVerifier, sample_spec: SpecContract):
        specs = verifier.list_specs()
        assert len(specs) == 1
        assert specs[0].spec_id == "SPEC-001"


# ---------------------------------------------------------------------------
# Verification tests
# ---------------------------------------------------------------------------

class TestVerification:
    def test_verify_with_all_tests_passing(
        self, verifier: SpecVerifier, sample_spec: SpecContract
    ):
        test_results = {
            c.criterion_id: True
            for c in sample_spec.acceptance_criteria
        }
        code = "def login(): pass\ndef register(): pass"
        result = verifier.verify_code("SPEC-001", code, test_results)
        assert result.passed == len(sample_spec.acceptance_criteria)
        assert result.failed == 0
        assert result.blocked is False
        assert result.pass_rate == 1.0

    def test_verify_with_failing_required(
        self, verifier: SpecVerifier, sample_spec: SpecContract
    ):
        # Fail a required criterion
        func_criteria = [
            c for c in sample_spec.acceptance_criteria
            if c.criterion_type == CriterionType.FUNCTIONAL
        ]
        test_results = {
            c.criterion_id: True
            for c in sample_spec.acceptance_criteria
        }
        test_results[func_criteria[0].criterion_id] = False

        result = verifier.verify_code("SPEC-001", "code", test_results)
        assert result.failed >= 1
        assert result.blocked is True
        assert len(result.missing_requirements) >= 1

    def test_verify_with_failing_optional(
        self, verifier: SpecVerifier, sample_spec: SpecContract
    ):
        # Fail only edge case (optional) criteria
        test_results = {}
        for c in sample_spec.acceptance_criteria:
            if c.criterion_type == CriterionType.EDGE_CASE:
                test_results[c.criterion_id] = False
            else:
                test_results[c.criterion_id] = True

        result = verifier.verify_code("SPEC-001", "code", test_results)
        assert result.failed >= 1
        assert result.blocked is False  # edge cases are optional

    def test_verify_nonexistent_spec(self, verifier: SpecVerifier):
        result = verifier.verify_code("NONEXISTENT", "code")
        assert result.blocked is True
        assert "Spec not found" in result.missing_requirements

    def test_static_verify_function_exists(
        self, verifier: SpecVerifier, sample_spec: SpecContract
    ):
        code = "def login(username, password):\n    pass\ndef register(user):\n    pass"
        result = verifier.verify_code("SPEC-001", code)
        # Should statically detect that login and register exist
        assert result.passed >= 2

    def test_static_verify_error_handling(self, verifier: SpecVerifier):
        verifier.create_spec(
            spec_id="SPEC-EH",
            title="Error handling",
            description="Test",
            functional_requirements=["Implement error handling and exception catching"],
        )
        code = "try:\n    do_something()\nexcept Exception as e:\n    handle(e)"
        result = verifier.verify_code("SPEC-EH", code)
        assert result.partial >= 1 or result.passed >= 1

    def test_static_verify_validation(self, verifier: SpecVerifier):
        verifier.create_spec(
            spec_id="SPEC-VAL",
            title="Validation",
            description="Test",
            functional_requirements=["Implement input validation"],
        )
        code = "def validate_input(data):\n    if not is_valid(data): raise ValueError"
        result = verifier.verify_code("SPEC-VAL", code)
        assert result.partial >= 1 or result.passed >= 1

    def test_static_verify_auth(self, verifier: SpecVerifier):
        verifier.create_spec(
            spec_id="SPEC-AUTH",
            title="Auth",
            description="Test",
            security_requirements=["Implement authentication checks"],
        )
        code = "def check_auth(token):\n    jwt.decode(token)"
        result = verifier.verify_code("SPEC-AUTH", code)
        assert result.partial >= 1 or result.passed >= 1

    def test_verify_updates_spec_status_verified(
        self, verifier: SpecVerifier, sample_spec: SpecContract
    ):
        test_results = {
            c.criterion_id: True for c in sample_spec.acceptance_criteria
        }
        verifier.verify_code("SPEC-001", "code", test_results)
        spec = verifier.get_spec("SPEC-001")
        assert spec is not None
        assert spec.status == SpecStatus.VERIFIED

    def test_verify_updates_spec_status_failed(
        self, verifier: SpecVerifier, sample_spec: SpecContract
    ):
        func_criteria = [
            c for c in sample_spec.acceptance_criteria
            if c.required
        ]
        test_results = {func_criteria[0].criterion_id: False}
        verifier.verify_code("SPEC-001", "code", test_results)
        spec = verifier.get_spec("SPEC-001")
        assert spec is not None
        assert spec.status == SpecStatus.FAILED


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_spec_to_dict(self, sample_spec: SpecContract):
        d = sample_spec.to_dict()
        assert d["spec_id"] == "SPEC-001"
        assert "acceptance_criteria" in d
        assert len(d["acceptance_criteria"]) == 8

    def test_verification_result_to_dict(
        self, verifier: SpecVerifier, sample_spec: SpecContract
    ):
        result = verifier.verify_code("SPEC-001", "code")
        d = result.to_dict()
        assert "spec_id" in d
        assert "pass_rate" in d
        assert "criteria_results" in d

    def test_criterion_to_dict(self, sample_spec: SpecContract):
        c = sample_spec.acceptance_criteria[0]
        d = c.to_dict()
        assert "criterion_id" in d
        assert "type" in d
        assert "required" in d


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------

class TestStats:
    def test_empty_stats(self, verifier: SpecVerifier):
        stats = verifier.get_stats()
        assert stats["total_specs"] == 0
        assert stats["total_verifications"] == 0

    def test_stats_after_operations(
        self, verifier: SpecVerifier, sample_spec: SpecContract
    ):
        verifier.verify_code("SPEC-001", "code")
        stats = verifier.get_stats()
        assert stats["total_specs"] == 1
        assert stats["total_verifications"] == 1

    def test_verification_history(
        self, verifier: SpecVerifier, sample_spec: SpecContract
    ):
        verifier.verify_code("SPEC-001", "code")
        verifier.verify_code("SPEC-001", "updated code")
        assert len(verifier.verification_history) == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_spec_with_no_requirements(self, verifier: SpecVerifier):
        spec = verifier.create_spec(
            spec_id="SPEC-EMPTY",
            title="Empty",
            description="No requirements",
        )
        assert len(spec.acceptance_criteria) == 0

    def test_verify_empty_spec(self, verifier: SpecVerifier):
        verifier.create_spec(
            spec_id="SPEC-EMPTY",
            title="Empty",
            description="No requirements",
        )
        result = verifier.verify_code("SPEC-EMPTY", "code")
        assert result.blocked is False
        assert result.pass_rate == 0.0

    def test_spec_with_data_schemas(self, verifier: SpecVerifier):
        spec = verifier.create_spec(
            spec_id="SPEC-DS",
            title="With schemas",
            description="Test",
            data_schemas=[{"name": "User", "fields": ["id", "email"]}],
        )
        assert len(spec.data_schemas) == 1

    def test_spec_with_api_contracts(self, verifier: SpecVerifier):
        spec = verifier.create_spec(
            spec_id="SPEC-API",
            title="With API",
            description="Test",
            api_contracts=[{"path": "/users", "method": "GET", "status": 200}],
        )
        assert len(spec.api_contracts) == 1
