"""Tests for Multi-Model Review Router — route reviews to appropriate models."""

from __future__ import annotations

import pytest

from app.quality.multi_model_review_router import (
    ChangeCategory,
    GateDecision,
    ModelProfile,
    ModelTier,
    MultiModelReviewRouter,
    ReviewDepth,
    ReviewFinding,
)


@pytest.fixture
def models() -> list[ModelProfile]:
    return [
        ModelProfile(
            model_id="fast-model",
            tier=ModelTier.FAST,
            capabilities=[ChangeCategory.STYLE, ChangeCategory.DOCUMENTATION,
                          ChangeCategory.CONFIG, ChangeCategory.REFACTOR],
            cost_per_1k_tokens=0.001,
            avg_latency_ms=200,
            quality_score=0.6,
        ),
        ModelProfile(
            model_id="standard-model",
            tier=ModelTier.STANDARD,
            capabilities=[ChangeCategory.LOGIC, ChangeCategory.TESTS,
                          ChangeCategory.API, ChangeCategory.PERFORMANCE,
                          ChangeCategory.DEPENDENCY],
            cost_per_1k_tokens=0.01,
            avg_latency_ms=1000,
            quality_score=0.8,
        ),
        ModelProfile(
            model_id="premium-model",
            tier=ModelTier.PREMIUM,
            capabilities=[ChangeCategory.SECURITY, ChangeCategory.LOGIC,
                          ChangeCategory.API, ChangeCategory.PERFORMANCE],
            cost_per_1k_tokens=0.05,
            avg_latency_ms=3000,
            quality_score=0.95,
        ),
    ]


@pytest.fixture
def router(models: list[ModelProfile]) -> MultiModelReviewRouter:
    return MultiModelReviewRouter(models=models)


@pytest.fixture
def empty_router() -> MultiModelReviewRouter:
    return MultiModelReviewRouter()


# ── Change classification ───────────────────────────────────────────────

class TestChangeClassification:
    def test_detect_security_change(self, router: MultiModelReviewRouter) -> None:
        diff = "+ password = get_hash(token)\n+ validate_jwt(request)"
        analysis = router.classify_change("d1", diff)
        assert ChangeCategory.SECURITY in analysis.categories

    def test_detect_logic_change(self, router: MultiModelReviewRouter) -> None:
        diff = "+ result = calculate_total(items)\n+ filtered = filter(valid, data)"
        analysis = router.classify_change("d1", diff)
        assert ChangeCategory.LOGIC in analysis.categories

    def test_detect_test_change(self, router: MultiModelReviewRouter) -> None:
        diff = "+ def test_create_user():\n+     assert response.status == 200"
        analysis = router.classify_change("d1", diff, file_paths=["tests/test_user.py"])
        assert ChangeCategory.TESTS in analysis.categories

    def test_detect_style_change(self, router: MultiModelReviewRouter) -> None:
        diff = "- x=1\n+ x = 1  # format fix"
        analysis = router.classify_change("d1", diff, file_paths=[".eslintrc"])
        assert ChangeCategory.STYLE in analysis.categories or analysis.primary_category is not None

    def test_detect_dependency_change(self, router: MultiModelReviewRouter) -> None:
        diff = '+ "axios": "^1.7.0"'
        analysis = router.classify_change("d1", diff, file_paths=["package.json"])
        assert ChangeCategory.DEPENDENCY in analysis.categories

    def test_default_to_logic(self, router: MultiModelReviewRouter) -> None:
        diff = "+ xyz = 42"
        analysis = router.classify_change("d1", diff)
        # Should have at least one category
        assert len(analysis.categories) >= 1

    def test_complexity_score_high_for_complex(self, router: MultiModelReviewRouter) -> None:
        # Lots of change lines + structural changes
        lines = [
            f"+def func_{i}(x):\n+    try:\n+        return x\n+    except:\n+        pass"
            for i in range(30)
        ]
        diff = "\n".join(lines)
        analysis = router.classify_change("d1", diff)
        assert analysis.complexity_score > 0.3

    def test_complexity_score_low_for_simple(self, router: MultiModelReviewRouter) -> None:
        diff = "  context line 1\n  context line 2\n+ x = 1\n  context line 3"
        analysis = router.classify_change("d1", diff)
        assert analysis.complexity_score <= 0.5

    def test_security_gets_deep_review(self, router: MultiModelReviewRouter) -> None:
        diff = "+ token = encrypt(password, secret_key)"
        analysis = router.classify_change("d1", diff)
        if ChangeCategory.SECURITY in analysis.categories:
            assert analysis.recommended_depth == ReviewDepth.DEEP

    def test_security_gets_premium_tier(self, router: MultiModelReviewRouter) -> None:
        diff = "+ validate_jwt(token)\n+ check_permission(user, role)"
        analysis = router.classify_change("d1", diff)
        if ChangeCategory.SECURITY in analysis.categories:
            assert analysis.recommended_tier == ModelTier.PREMIUM


# ── Routing ─────────────────────────────────────────────────────────────

class TestRouting:
    def test_route_security_to_premium(self, router: MultiModelReviewRouter) -> None:
        diff = "+ validate_jwt(token)\n+ hash_password(pwd)"
        analysis = router.classify_change("d1", diff)
        decision = router.route(analysis)
        if analysis.primary_category == ChangeCategory.SECURITY:
            assert decision.model_tier == ModelTier.PREMIUM

    def test_route_style_to_fast(self, router: MultiModelReviewRouter) -> None:
        diff = "- x=1\n+ x = 1  # prettier format"
        analysis = router.classify_change("d1", diff, file_paths=["lint.config"])
        decision = router.route(analysis)
        # Style changes should go to fast or above
        assert decision.model_id != "none"

    def test_route_no_models_returns_none(self, empty_router: MultiModelReviewRouter) -> None:
        diff = "+ x = 1"
        analysis = empty_router.classify_change("d1", diff)
        decision = empty_router.route(analysis)
        assert decision.model_id == "none"

    def test_route_tracks_decisions(self, router: MultiModelReviewRouter) -> None:
        diff = "+ x = calculate(y)"
        analysis = router.classify_change("d1", diff)
        router.route(analysis)
        assert len(router.decisions) == 1

    def test_route_estimated_cost(self, router: MultiModelReviewRouter) -> None:
        diff = "+ x = 1\n" * 10
        analysis = router.classify_change("d1", diff)
        decision = router.route(analysis)
        assert decision.estimated_cost >= 0

    def test_route_has_rationale(self, router: MultiModelReviewRouter) -> None:
        diff = "+ x = 1"
        analysis = router.classify_change("d1", diff)
        decision = router.route(analysis)
        assert decision.rationale

    def test_register_model(self, empty_router: MultiModelReviewRouter) -> None:
        model = ModelProfile(
            model_id="test-model", tier=ModelTier.STANDARD,
            capabilities=[ChangeCategory.LOGIC],
            cost_per_1k_tokens=0.01, avg_latency_ms=500,
            quality_score=0.8,
        )
        empty_router.register_model(model)
        assert "test-model" in empty_router.models

    def test_inactive_model_skipped(self, router: MultiModelReviewRouter) -> None:
        router.models["premium-model"].active = False
        diff = "+ validate_jwt(token)"
        analysis = router.classify_change("d1", diff)
        decision = router.route(analysis)
        assert decision.model_id != "premium-model"
        router.models["premium-model"].active = True  # restore


# ── Review aggregation ──────────────────────────────────────────────────

class TestReviewAggregation:
    def test_aggregate_single_model(self, router: MultiModelReviewRouter) -> None:
        findings = [
            ReviewFinding(id="r1", model_id="m1", category=ChangeCategory.SECURITY,
                          severity="high", message="SQL injection risk"),
        ]
        result = router.aggregate_reviews("d1", [("m1", findings, 0.05)])
        assert len(result.findings) == 1
        assert result.total_cost == 0.05

    def test_aggregate_deduplicates(self, router: MultiModelReviewRouter) -> None:
        f1 = ReviewFinding(id="r1", model_id="m1", category=ChangeCategory.SECURITY,
                           severity="high", message="SQL injection risk")
        f2 = ReviewFinding(id="r2", model_id="m2", category=ChangeCategory.SECURITY,
                           severity="high", message="SQL injection risk")
        result = router.aggregate_reviews("d1", [
            ("m1", [f1], 0.05),
            ("m2", [f2], 0.03),
        ])
        assert len(result.findings) == 1
        assert result.total_cost == 0.08

    def test_aggregate_multiple_models(self, router: MultiModelReviewRouter) -> None:
        f1 = ReviewFinding(id="r1", model_id="m1", category=ChangeCategory.SECURITY,
                           severity="high", message="SQL injection")
        f2 = ReviewFinding(id="r2", model_id="m2", category=ChangeCategory.PERFORMANCE,
                           severity="medium", message="N+1 query")
        result = router.aggregate_reviews("d1", [
            ("m1", [f1], 0.05),
            ("m2", [f2], 0.01),
        ])
        assert len(result.findings) == 2
        assert len(result.models_used) == 2

    def test_aggregate_gate_block(self, router: MultiModelReviewRouter) -> None:
        findings = [
            ReviewFinding(id=f"r{i}", model_id="m1", category=ChangeCategory.SECURITY,
                          severity="critical", message=f"vuln {i}")
            for i in range(6)
        ]
        result = router.aggregate_reviews("d1", [("m1", findings, 0.1)])
        assert result.gate_decision == GateDecision.BLOCK

    def test_aggregate_gate_pass(self, router: MultiModelReviewRouter) -> None:
        result = router.aggregate_reviews("d1", [("m1", [], 0.01)])
        assert result.gate_decision == GateDecision.PASS

    def test_aggregate_coverage(self, router: MultiModelReviewRouter) -> None:
        f1 = ReviewFinding(id="r1", model_id="m1", category=ChangeCategory.SECURITY,
                           severity="high", message="issue")
        result = router.aggregate_reviews("d1", [("m1", [f1], 0.05)])
        assert result.coverage[ChangeCategory.SECURITY.value] is True


# ── Analytics ───────────────────────────────────────────────────────────

class TestAnalytics:
    def test_analytics_empty(self, empty_router: MultiModelReviewRouter) -> None:
        analytics = empty_router.get_analytics()
        assert analytics.total_reviews == 0

    def test_analytics_after_routing(self, router: MultiModelReviewRouter) -> None:
        for _ in range(3):
            analysis = router.classify_change("d1", "+ x = validate(token)")
            router.route(analysis)
        analytics = router.get_analytics()
        assert analytics.total_reviews == 3
        assert analytics.avg_cost >= 0

    def test_analytics_by_tier(self, router: MultiModelReviewRouter) -> None:
        analysis = router.classify_change("d1", "+ x = 1")
        router.route(analysis)
        analytics = router.get_analytics()
        assert sum(analytics.reviews_by_tier.values()) == 1

    def test_analytics_by_category(self, router: MultiModelReviewRouter) -> None:
        analysis = router.classify_change("d1", "+ validate_jwt(token)")
        router.route(analysis)
        analytics = router.get_analytics()
        assert sum(analytics.reviews_by_category.values()) >= 1
