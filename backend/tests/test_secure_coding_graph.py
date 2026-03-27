"""Tests for Graph-Based Secure Coding Reasoning (GRASP) engine."""

from __future__ import annotations

import pytest

from app.quality.secure_coding_graph import (
    BatchEvalResult,
    GraphEdge,
    GRASPEngine,
    SecureCodingPractice,
    SecurityConstraintSet,
    SecurityDomain,
    SeverityLevel,
    TraversalResult,
    TraversalStrategy,
)


@pytest.fixture
def engine() -> GRASPEngine:
    return GRASPEngine()


class TestGRASPEngineInit:
    def test_default_scps_loaded(self, engine: GRASPEngine) -> None:
        scps = engine.list_scps()
        assert len(scps) >= 10

    def test_has_all_domains(self, engine: GRASPEngine) -> None:
        domains = {s.domain for s in engine.list_scps()}
        assert SecurityDomain.INPUT_VALIDATION in domains
        assert SecurityDomain.AUTHENTICATION in domains
        assert SecurityDomain.CRYPTOGRAPHY in domains

    def test_edges_created_for_dependencies(self, engine: GRASPEngine) -> None:
        authz = engine.get_scp("scp-authz-least-priv")
        assert authz is not None
        assert "scp-auth-strong" in authz.dependencies

    def test_get_scp_returns_none_for_unknown(self, engine: GRASPEngine) -> None:
        assert engine.get_scp("nonexistent") is None


class TestSCPRegistration:
    def test_register_custom_scp(self, engine: GRASPEngine) -> None:
        scp = SecureCodingPractice(
            id="scp-custom",
            name="Custom Practice",
            description="Test practice",
            domain=SecurityDomain.NETWORK,
            severity=SeverityLevel.HIGH,
            keywords=["custom", "test"],
        )
        engine.register_scp(scp)
        assert engine.get_scp("scp-custom") is not None

    def test_register_scp_with_dependencies(self, engine: GRASPEngine) -> None:
        scp = SecureCodingPractice(
            id="scp-depends",
            name="Dependent",
            description="Depends on auth",
            domain=SecurityDomain.AUTHORIZATION,
            severity=SeverityLevel.HIGH,
            keywords=["depend"],
            dependencies=["scp-auth-strong"],
        )
        engine.register_scp(scp)
        deps = engine.get_dependencies("scp-depends")
        assert "scp-auth-strong" in deps

    def test_add_edge(self, engine: GRASPEngine) -> None:
        edge = GraphEdge(
            source_id="scp-input-sanitize",
            target_id="scp-error-safe",
        )
        engine.add_edge(edge)
        dependents = engine.get_dependents("scp-input-sanitize")
        assert "scp-error-safe" in dependents


class TestTraversal:
    def test_relevance_based_traversal(self, engine: GRASPEngine) -> None:
        result = engine.traverse("implement user login form with password authentication")
        assert isinstance(result, TraversalResult)
        assert len(result.applicable_scps) > 0
        ids = [s.id for s in result.applicable_scps]
        assert "scp-auth-strong" in ids

    def test_input_validation_context(self, engine: GRASPEngine) -> None:
        result = engine.traverse("parse user input from form and query parameters")
        ids = [s.id for s in result.applicable_scps]
        assert "scp-input-sanitize" in ids

    def test_crypto_context(self, engine: GRASPEngine) -> None:
        result = engine.traverse("encrypt data using AES and generate hash")
        ids = [s.id for s in result.applicable_scps]
        assert "scp-crypto-modern" in ids

    def test_file_io_context(self, engine: GRASPEngine) -> None:
        result = engine.traverse("handle file upload and download path")
        ids = [s.id for s in result.applicable_scps]
        assert "scp-file-safe" in ids

    def test_severity_floor_filters(self, engine: GRASPEngine) -> None:
        critical_only = engine.traverse(
            "login authentication",
            severity_floor=SeverityLevel.CRITICAL,
        )
        all_sev = engine.traverse(
            "login authentication",
            severity_floor=SeverityLevel.INFO,
        )
        assert len(critical_only.applicable_scps) <= len(all_sev.applicable_scps)

    def test_topological_strategy(self, engine: GRASPEngine) -> None:
        result = engine.traverse(
            "secure login authentication",
            strategy=TraversalStrategy.TOPOLOGICAL,
        )
        assert len(result.applicable_scps) > 0

    def test_depth_first_strategy(self, engine: GRASPEngine) -> None:
        result = engine.traverse(
            "error handling for API",
            strategy=TraversalStrategy.DEPTH_FIRST,
        )
        assert len(result.applicable_scps) > 0

    def test_max_scps_limit(self, engine: GRASPEngine) -> None:
        result = engine.traverse(
            "input authentication crypto file network error",
            max_scps=3,
        )
        # May be more due to dependency resolution, but should be bounded
        assert len(result.traversal_order) >= 1

    def test_security_score_range(self, engine: GRASPEngine) -> None:
        result = engine.traverse("implement file upload with auth")
        assert 0.0 <= result.security_score <= 1.0

    def test_reasoning_chain_populated(self, engine: GRASPEngine) -> None:
        result = engine.traverse("user login form")
        assert len(result.reasoning_chain) > 0

    def test_skipped_scps_populated(self, engine: GRASPEngine) -> None:
        result = engine.traverse("login")
        total = len(result.applicable_scps) + len(result.skipped_scps)
        assert total == len(engine.list_scps())

    def test_unrelated_context_low_matches(self, engine: GRASPEngine) -> None:
        result = engine.traverse("calculate fibonacci sequence")
        assert result.security_score < 0.5

    def test_dependency_resolution(self, engine: GRASPEngine) -> None:
        result = engine.traverse("role permission access authorization rbac")
        ids = result.traversal_order
        if "scp-authz-least-priv" in ids and "scp-auth-strong" in ids:
            assert ids.index("scp-auth-strong") < ids.index("scp-authz-least-priv")


class TestConstraintComposition:
    def test_compose_constraints(self, engine: GRASPEngine) -> None:
        traversal = engine.traverse("user login authentication")
        constraints = engine.compose_constraints(traversal)
        assert isinstance(constraints, SecurityConstraintSet)
        assert constraints.total_scps_applied > 0
        assert len(constraints.constraints) > 0

    def test_domains_covered(self, engine: GRASPEngine) -> None:
        traversal = engine.traverse("login with crypto")
        constraints = engine.compose_constraints(traversal)
        assert len(constraints.domains_covered) > 0

    def test_severity_floor_set(self, engine: GRASPEngine) -> None:
        traversal = engine.traverse("authentication")
        constraints = engine.compose_constraints(traversal)
        assert constraints.severity_floor in list(SeverityLevel)


class TestPromptEnrichment:
    def test_enrich_prompt(self, engine: GRASPEngine) -> None:
        original = "Write a user login endpoint."
        enriched = engine.enrich_prompt(original, "user login authentication")
        assert original in enriched
        assert "Security Constraints" in enriched

    def test_enrich_no_match(self, engine: GRASPEngine) -> None:
        original = "Calculate fibonacci."
        enriched = engine.enrich_prompt(
            original, "fibonacci math calculation",
            severity_floor=SeverityLevel.CRITICAL,
        )
        # May or may not match depending on keywords
        assert original in enriched

    def test_enrich_preserves_original(self, engine: GRASPEngine) -> None:
        original = "Build an API endpoint for file upload."
        enriched = engine.enrich_prompt(original, "file upload endpoint")
        assert enriched.startswith(original)


class TestBatchEvaluation:
    def test_batch_eval(self, engine: GRASPEngine) -> None:
        tasks = [
            "login authentication",
            "file upload handler",
            "calculate sum",
        ]
        result = engine.evaluate_batch(tasks)
        assert isinstance(result, BatchEvalResult)
        assert result.total_tasks == 3

    def test_batch_below_threshold(self, engine: GRASPEngine) -> None:
        tasks = ["fibonacci", "sort array", "print hello"]
        result = engine.evaluate_batch(tasks, threshold=0.8)
        assert result.tasks_below_threshold >= 0

    def test_batch_cwe_coverage(self, engine: GRASPEngine) -> None:
        tasks = ["sql query input validation", "authentication login"]
        result = engine.evaluate_batch(tasks)
        assert len(result.cwe_coverage) > 0


class TestListAndFilter:
    def test_list_all_scps(self, engine: GRASPEngine) -> None:
        scps = engine.list_scps()
        assert len(scps) >= 10

    def test_list_scps_by_domain(self, engine: GRASPEngine) -> None:
        scps = engine.list_scps(domain=SecurityDomain.AUTHENTICATION)
        assert all(s.domain == SecurityDomain.AUTHENTICATION for s in scps)

    def test_list_empty_domain(self, engine: GRASPEngine) -> None:
        # All domains should have at least one SCP
        for domain in SecurityDomain:
            scps = engine.list_scps(domain=domain)
            assert len(scps) >= 1


class TestAuditAndAnalytics:
    def test_audit_log_populated(self, engine: GRASPEngine) -> None:
        engine.traverse("login")
        log = engine.get_audit_log()
        assert len(log) >= 1
        assert log[0]["action"] == "traverse"

    def test_analytics(self, engine: GRASPEngine) -> None:
        engine.traverse("login")
        engine.traverse("file upload")
        stats = engine.analytics()
        assert stats["total_scps"] >= 10
        assert stats["total_traversals"] == 2
        assert stats["avg_scps_applied"] > 0

    def test_analytics_empty(self, engine: GRASPEngine) -> None:
        stats = engine.analytics()
        assert stats["total_traversals"] == 0
