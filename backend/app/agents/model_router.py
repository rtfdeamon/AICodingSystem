"""Multi-Model Router with Cost-Aware Cascading.

Routes requests to the most appropriate model based on task complexity,
cost constraints, and provider health (circuit breaker pattern).

1. Classifies incoming tasks by complexity (trivial / standard / complex).
2. Selects the cheapest healthy model in the matching tier.
3. Falls back to higher tiers when the preferred provider is unavailable.
4. Tracks routing decisions and exposes aggregate statistics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────

class TaskComplexity(StrEnum):
    TRIVIAL = "trivial"
    STANDARD = "standard"
    COMPLEX = "complex"


class ModelTier(StrEnum):
    FAST = "fast"
    STANDARD = "standard"
    FRONTIER = "frontier"


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ── Data classes ──────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    """Configuration for a single model endpoint."""

    model_id: str
    provider: str
    tier: ModelTier
    cost_per_1k_input: float
    cost_per_1k_output: float
    max_tokens: int
    avg_latency_ms: float


@dataclass
class RoutingDecision:
    """Result of routing a request to a specific model."""

    model_config: ModelConfig
    complexity: TaskComplexity
    reason: str
    estimated_cost: float
    fallback_models: list[ModelConfig] = field(default_factory=list)


@dataclass
class CircuitBreaker:
    """Per-provider circuit breaker to avoid cascading failures."""

    provider: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_at: datetime | None = None
    cooldown_seconds: int = 1800

    # Number of consecutive failures before the circuit trips open.
    _failure_threshold: int = 5


@dataclass
class RoutingStats:
    """Aggregated routing statistics."""

    total_requests: int
    escalations: int
    circuit_breaks: int
    avg_cost: float
    cost_by_tier: dict[str, float]


# ── In-memory stores (MVP) ───────────────────────────────────────────

_model_registry: list[ModelConfig] = []
_circuit_breakers: dict[str, CircuitBreaker] = {}
_routing_history: list[RoutingDecision] = []


# ── Complexity-to-tier mapping ────────────────────────────────────────

_COMPLEXITY_TIER_MAP: dict[TaskComplexity, ModelTier] = {
    TaskComplexity.TRIVIAL: ModelTier.FAST,
    TaskComplexity.STANDARD: ModelTier.STANDARD,
    TaskComplexity.COMPLEX: ModelTier.FRONTIER,
}

_TIER_ESCALATION: dict[ModelTier, ModelTier | None] = {
    ModelTier.FAST: ModelTier.STANDARD,
    ModelTier.STANDARD: ModelTier.FRONTIER,
    ModelTier.FRONTIER: None,
}


# ── Public API ────────────────────────────────────────────────────────

def register_model(
    model_id: str,
    provider: str,
    tier: ModelTier | str,
    cost_input: float,
    cost_output: float,
    max_tokens: int,
    avg_latency: float,
) -> ModelConfig:
    """Register a model in the global registry.

    Parameters
    ----------
    model_id:
        Unique identifier for the model (e.g. ``"gpt-4o-mini"``).
    provider:
        Provider name (e.g. ``"openai"``).
    tier:
        Model tier — FAST, STANDARD, or FRONTIER.
    cost_input:
        Cost per 1 000 input tokens (USD).
    cost_output:
        Cost per 1 000 output tokens (USD).
    max_tokens:
        Maximum context window size.
    avg_latency:
        Average response latency in milliseconds.
    """
    tier = ModelTier(tier)
    config = ModelConfig(
        model_id=model_id,
        provider=provider,
        tier=tier,
        cost_per_1k_input=cost_input,
        cost_per_1k_output=cost_output,
        max_tokens=max_tokens,
        avg_latency_ms=avg_latency,
    )
    _model_registry.append(config)
    logger.info("Registered model %s (provider=%s, tier=%s)", model_id, provider, tier)
    return config


def classify_task_complexity(
    prompt: str,
    file_count: int = 1,
    line_count: int = 0,
) -> TaskComplexity:
    """Classify the complexity of a coding task using simple heuristics.

    Rules
    -----
    * **COMPLEX** — multi-file (>3 files) *or* large line count (>500) *or*
      prompt contains architecture / refactor keywords.
    * **TRIVIAL** — single file, short prompt (<80 chars), low line count (<50).
    * **STANDARD** — everything else.
    """
    prompt_lower = prompt.lower()
    complex_keywords = (
        "refactor", "architect", "redesign", "migration", "microservice",
        "distributed", "scalab",
    )

    if file_count > 3 or line_count > 500:
        return TaskComplexity.COMPLEX
    if any(kw in prompt_lower for kw in complex_keywords):
        return TaskComplexity.COMPLEX

    if file_count <= 1 and len(prompt) < 80 and line_count < 50:
        return TaskComplexity.TRIVIAL

    return TaskComplexity.STANDARD


def route_request(
    prompt: str,
    file_count: int = 1,
    line_count: int = 0,
    preferred_tier: ModelTier | str | None = None,
) -> RoutingDecision:
    """Select the best model for a given request.

    Considers task complexity, provider health (circuit state), and cost.
    If the ideal tier has no healthy models the router escalates to the
    next tier.

    Raises
    ------
    RuntimeError
        If no healthy model can be found across any tier.
    """
    complexity = classify_task_complexity(prompt, file_count, line_count)

    if preferred_tier is not None:
        target_tier = ModelTier(preferred_tier)
    else:
        target_tier = _COMPLEXITY_TIER_MAP[complexity]

    selected, reason, fallbacks = _select_model_with_fallback(target_tier)

    if selected is None:
        raise RuntimeError("No healthy model available across any tier")

    estimated = estimate_cost(selected, input_tokens=len(prompt) * 2, output_tokens=500)

    decision = RoutingDecision(
        model_config=selected,
        complexity=complexity,
        reason=reason,
        estimated_cost=estimated,
        fallback_models=fallbacks,
    )
    _routing_history.append(decision)

    logger.info(
        "Routed request: model=%s tier=%s complexity=%s cost=%.6f",
        selected.model_id,
        selected.tier,
        complexity,
        estimated,
    )
    return decision


def record_failure(provider: str) -> CircuitState:
    """Record a provider failure and potentially trip the circuit breaker.

    Returns the new circuit state after recording the failure.
    """
    cb = _get_or_create_breaker(provider)
    cb.failure_count += 1
    cb.last_failure_at = datetime.now(UTC)

    if cb.failure_count >= cb._failure_threshold:
        cb.state = CircuitState.OPEN
        logger.warning(
            "Circuit breaker OPEN for provider '%s' after %d failures",
            provider,
            cb.failure_count,
        )
    return cb.state


def record_success(provider: str) -> None:
    """Record a successful call and reset the circuit breaker."""
    cb = _get_or_create_breaker(provider)
    cb.failure_count = 0
    cb.state = CircuitState.CLOSED
    cb.last_failure_at = None
    logger.debug("Circuit breaker reset for provider '%s'", provider)


def check_circuit(provider: str) -> CircuitState:
    """Return the current circuit state for *provider*.

    Transitions OPEN -> HALF_OPEN when the cooldown has elapsed.
    """
    cb = _get_or_create_breaker(provider)

    if cb.state == CircuitState.OPEN and cb.last_failure_at is not None:
        elapsed = (datetime.now(UTC) - cb.last_failure_at).total_seconds()
        if elapsed >= cb.cooldown_seconds:
            cb.state = CircuitState.HALF_OPEN
            logger.info(
                "Circuit breaker HALF_OPEN for provider '%s' (cooldown elapsed)",
                provider,
            )

    return cb.state


def get_routing_stats() -> RoutingStats:
    """Compute aggregate routing statistics from the history."""
    total = len(_routing_history)
    if total == 0:
        return RoutingStats(
            total_requests=0,
            escalations=0,
            circuit_breaks=0,
            avg_cost=0.0,
            cost_by_tier={},
        )

    escalations = sum(
        1
        for rd in _routing_history
        if rd.model_config.tier != _COMPLEXITY_TIER_MAP.get(rd.complexity)
    )
    circuit_breaks = sum(
        1 for cb in _circuit_breakers.values() if cb.state == CircuitState.OPEN
    )
    total_cost = sum(rd.estimated_cost for rd in _routing_history)
    cost_by_tier: dict[str, float] = {}
    for rd in _routing_history:
        tier_key = rd.model_config.tier.value
        cost_by_tier[tier_key] = cost_by_tier.get(tier_key, 0.0) + rd.estimated_cost

    return RoutingStats(
        total_requests=total,
        escalations=escalations,
        circuit_breaks=circuit_breaks,
        avg_cost=round(total_cost / total, 6),
        cost_by_tier={k: round(v, 6) for k, v in cost_by_tier.items()},
    )


def get_models_for_tier(tier: ModelTier | str) -> list[ModelConfig]:
    """Return all registered models for the given tier."""
    tier = ModelTier(tier)
    return [m for m in _model_registry if m.tier == tier]


def estimate_cost(
    model: ModelConfig,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate the USD cost for a given token count."""
    input_cost = (input_tokens / 1000) * model.cost_per_1k_input
    output_cost = (output_tokens / 1000) * model.cost_per_1k_output
    return round(input_cost + output_cost, 6)


def clear_router_state() -> None:
    """Reset all in-memory state (for testing)."""
    _model_registry.clear()
    _circuit_breakers.clear()
    _routing_history.clear()


def routing_decision_to_json(rd: RoutingDecision) -> dict:
    """Serialize a RoutingDecision to a JSON-compatible dict."""
    return {
        "model_id": rd.model_config.model_id,
        "provider": rd.model_config.provider,
        "tier": rd.model_config.tier.value,
        "complexity": rd.complexity.value,
        "reason": rd.reason,
        "estimated_cost": rd.estimated_cost,
        "fallback_models": [
            {"model_id": m.model_id, "provider": m.provider, "tier": m.tier.value}
            for m in rd.fallback_models
        ],
    }


# ── Internal helpers ──────────────────────────────────────────────────

def _get_or_create_breaker(provider: str) -> CircuitBreaker:
    """Return the circuit breaker for *provider*, creating one if needed."""
    if provider not in _circuit_breakers:
        _circuit_breakers[provider] = CircuitBreaker(provider=provider)
    return _circuit_breakers[provider]


def _is_provider_healthy(provider: str) -> bool:
    """Return True if the provider's circuit is not OPEN."""
    state = check_circuit(provider)
    return state != CircuitState.OPEN


def _select_model_with_fallback(
    target_tier: ModelTier,
) -> tuple[ModelConfig | None, str, list[ModelConfig]]:
    """Select the cheapest healthy model in *target_tier*, escalating if needed.

    Returns ``(selected_model, reason, fallback_models)``.
    """
    tier: ModelTier | None = target_tier
    reason_parts: list[str] = []
    fallbacks: list[ModelConfig] = []

    while tier is not None:
        candidates = [
            m for m in _model_registry
            if m.tier == tier and _is_provider_healthy(m.provider)
        ]
        # Sort by input cost (cheapest first).
        candidates.sort(key=lambda m: m.cost_per_1k_input)

        if candidates:
            selected = candidates[0]
            if tier == target_tier:
                reason_parts.append(
                    f"Selected cheapest healthy model in {tier.value} tier"
                )
            else:
                reason_parts.append(
                    f"Escalated from {target_tier.value} to {tier.value} tier"
                )
            # Remaining candidates become fallbacks.
            fallbacks = candidates[1:]
            return selected, "; ".join(reason_parts), fallbacks

        reason_parts.append(f"No healthy models in {tier.value} tier")
        tier = _TIER_ESCALATION.get(tier)

    return None, "; ".join(reason_parts), []
