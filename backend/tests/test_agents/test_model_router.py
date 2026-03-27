"""Tests for app.agents.model_router — multi-model routing with cost cascading."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agents.model_router import (
    CircuitState,
    ModelConfig,
    ModelTier,
    TaskComplexity,
    check_circuit,
    classify_task_complexity,
    clear_router_state,
    estimate_cost,
    get_models_for_tier,
    get_routing_stats,
    record_failure,
    record_success,
    register_model,
    route_request,
    routing_decision_to_json,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_state():
    """Ensure each test starts with a blank router state."""
    clear_router_state()
    yield
    clear_router_state()


def _register_defaults() -> tuple[ModelConfig, ModelConfig, ModelConfig]:
    """Register one model per tier and return them."""
    fast = register_model(
        "gpt-4o-mini", "openai", ModelTier.FAST,
        cost_input=0.15, cost_output=0.60, max_tokens=128_000, avg_latency=200,
    )
    std = register_model(
        "claude-sonnet", "anthropic", ModelTier.STANDARD,
        cost_input=3.0, cost_output=15.0, max_tokens=200_000, avg_latency=800,
    )
    frontier = register_model(
        "claude-opus", "anthropic-frontier", ModelTier.FRONTIER,
        cost_input=15.0, cost_output=75.0, max_tokens=200_000, avg_latency=2000,
    )
    return fast, std, frontier


# ---------------------------------------------------------------------------
# Task complexity classification
# ---------------------------------------------------------------------------


class TestClassifyTaskComplexity:
    def test_trivial_short_prompt_single_file(self):
        result = classify_task_complexity("fix typo", file_count=1, line_count=10)
        assert result == TaskComplexity.TRIVIAL

    def test_standard_medium_prompt(self):
        prompt = (
            "Add input validation to the user registration"
            " endpoint and return proper error codes"
        )
        result = classify_task_complexity(prompt, file_count=2, line_count=100)
        assert result == TaskComplexity.STANDARD

    def test_complex_many_files(self):
        result = classify_task_complexity("update tests", file_count=5, line_count=30)
        assert result == TaskComplexity.COMPLEX

    def test_complex_high_line_count(self):
        result = classify_task_complexity("update tests", file_count=1, line_count=600)
        assert result == TaskComplexity.COMPLEX

    def test_complex_keyword_refactor(self):
        result = classify_task_complexity("refactor the auth module", file_count=1, line_count=10)
        assert result == TaskComplexity.COMPLEX

    def test_complex_keyword_architect(self):
        result = classify_task_complexity("architect the new microservice layer")
        assert result == TaskComplexity.COMPLEX

    def test_trivial_empty_prompt(self):
        result = classify_task_complexity("", file_count=1, line_count=0)
        assert result == TaskComplexity.TRIVIAL


# ---------------------------------------------------------------------------
# Model registration
# ---------------------------------------------------------------------------


class TestRegisterModel:
    def test_register_and_retrieve(self):
        model = register_model(
            "test-model", "test-provider", ModelTier.FAST,
            cost_input=0.1, cost_output=0.2, max_tokens=4096, avg_latency=100,
        )
        assert model.model_id == "test-model"
        assert model.tier == ModelTier.FAST
        models = get_models_for_tier(ModelTier.FAST)
        assert len(models) == 1
        assert models[0].model_id == "test-model"

    def test_register_string_tier(self):
        model = register_model(
            "m", "p", "standard",
            cost_input=1.0, cost_output=2.0, max_tokens=8192, avg_latency=500,
        )
        assert model.tier == ModelTier.STANDARD


# ---------------------------------------------------------------------------
# Routing decisions
# ---------------------------------------------------------------------------


class TestRouteRequest:
    def test_trivial_routes_to_fast(self):
        _register_defaults()
        decision = route_request("fix typo", file_count=1, line_count=5)
        assert decision.complexity == TaskComplexity.TRIVIAL
        assert decision.model_config.tier == ModelTier.FAST

    def test_complex_routes_to_frontier(self):
        _register_defaults()
        decision = route_request("refactor the entire auth module", file_count=5, line_count=1000)
        assert decision.complexity == TaskComplexity.COMPLEX
        assert decision.model_config.tier == ModelTier.FRONTIER

    def test_preferred_tier_overrides_classification(self):
        _register_defaults()
        decision = route_request("fix typo", preferred_tier=ModelTier.FRONTIER)
        assert decision.model_config.tier == ModelTier.FRONTIER

    def test_no_models_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="No healthy model"):
            route_request("hello")

    def test_cheapest_model_selected_within_tier(self):
        register_model(
            "expensive", "prov-a", ModelTier.FAST,
            cost_input=5.0, cost_output=10.0, max_tokens=4096, avg_latency=100,
        )
        register_model(
            "cheap", "prov-b", ModelTier.FAST,
            cost_input=0.1, cost_output=0.2, max_tokens=4096, avg_latency=100,
        )
        decision = route_request("fix typo", file_count=1, line_count=5)
        assert decision.model_config.model_id == "cheap"


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


class TestEstimateCost:
    def test_basic_cost_calculation(self):
        model = ModelConfig(
            model_id="m", provider="p", tier=ModelTier.FAST,
            cost_per_1k_input=1.0, cost_per_1k_output=2.0,
            max_tokens=4096, avg_latency_ms=100,
        )
        cost = estimate_cost(model, input_tokens=1000, output_tokens=1000)
        assert cost == 3.0

    def test_zero_tokens(self):
        model = ModelConfig(
            model_id="m", provider="p", tier=ModelTier.FAST,
            cost_per_1k_input=1.0, cost_per_1k_output=2.0,
            max_tokens=4096, avg_latency_ms=100,
        )
        assert estimate_cost(model, input_tokens=0, output_tokens=0) == 0.0


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        assert check_circuit("new-provider") == CircuitState.CLOSED

    def test_failure_below_threshold_stays_closed(self):
        for _ in range(4):
            state = record_failure("prov")
        assert state == CircuitState.CLOSED

    def test_failure_at_threshold_trips_open(self):
        for _ in range(5):
            state = record_failure("prov")
        assert state == CircuitState.OPEN

    def test_success_resets_breaker(self):
        for _ in range(4):
            record_failure("prov")
        record_success("prov")
        assert check_circuit("prov") == CircuitState.CLOSED

    def test_cooldown_transitions_to_half_open(self):
        for _ in range(5):
            record_failure("prov")
        assert check_circuit("prov") == CircuitState.OPEN

        # Simulate cooldown elapsed by patching datetime.
        past = datetime.now(UTC) - timedelta(seconds=1801)
        from app.agents import model_router as _mod
        _mod._circuit_breakers["prov"].last_failure_at = past

        assert check_circuit("prov") == CircuitState.HALF_OPEN


# ---------------------------------------------------------------------------
# Escalation / fallback
# ---------------------------------------------------------------------------


class TestEscalation:
    def test_escalates_when_tier_unhealthy(self):
        register_model(
            "fast-model", "bad-prov", ModelTier.FAST,
            cost_input=0.1, cost_output=0.2, max_tokens=4096, avg_latency=100,
        )
        register_model(
            "std-model", "good-prov", ModelTier.STANDARD,
            cost_input=1.0, cost_output=2.0, max_tokens=8192, avg_latency=500,
        )
        # Trip the fast provider's circuit.
        for _ in range(5):
            record_failure("bad-prov")

        decision = route_request("fix typo", file_count=1, line_count=5)
        # Should escalate to standard tier.
        assert decision.model_config.tier == ModelTier.STANDARD
        assert "Escalated" in decision.reason

    def test_all_circuits_open_raises(self):
        register_model(
            "m1", "prov1", ModelTier.FAST,
            cost_input=0.1, cost_output=0.2, max_tokens=4096, avg_latency=100,
        )
        register_model(
            "m2", "prov2", ModelTier.STANDARD,
            cost_input=1.0, cost_output=2.0, max_tokens=8192, avg_latency=500,
        )
        register_model(
            "m3", "prov3", ModelTier.FRONTIER,
            cost_input=10.0, cost_output=20.0, max_tokens=32000, avg_latency=2000,
        )
        for prov in ("prov1", "prov2", "prov3"):
            for _ in range(5):
                record_failure(prov)

        with pytest.raises(RuntimeError, match="No healthy model"):
            route_request("anything")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestRoutingStats:
    def test_empty_stats(self):
        stats = get_routing_stats()
        assert stats.total_requests == 0
        assert stats.avg_cost == 0.0
        assert stats.cost_by_tier == {}

    def test_stats_after_requests(self):
        _register_defaults()
        route_request("fix typo", file_count=1, line_count=5)
        route_request("refactor the whole system", file_count=10, line_count=2000)

        stats = get_routing_stats()
        assert stats.total_requests == 2
        assert stats.avg_cost > 0
        assert len(stats.cost_by_tier) >= 1


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------


class TestJsonSerialization:
    def test_routing_decision_to_json(self):
        _register_defaults()
        decision = route_request("fix typo", file_count=1, line_count=5)
        data = routing_decision_to_json(decision)

        assert data["model_id"] == decision.model_config.model_id
        assert data["complexity"] == "trivial"
        assert data["tier"] == decision.model_config.tier.value
        assert "estimated_cost" in data
        assert isinstance(data["fallback_models"], list)

    def test_json_fallback_models_structure(self):
        register_model(
            "m1", "p1", ModelTier.FAST,
            cost_input=0.1, cost_output=0.2, max_tokens=4096, avg_latency=100,
        )
        register_model(
            "m2", "p2", ModelTier.FAST,
            cost_input=0.5, cost_output=1.0, max_tokens=4096, avg_latency=200,
        )
        decision = route_request("fix typo", file_count=1, line_count=5)
        data = routing_decision_to_json(decision)

        assert len(data["fallback_models"]) == 1
        fb = data["fallback_models"][0]
        assert "model_id" in fb
        assert "provider" in fb
        assert "tier" in fb
