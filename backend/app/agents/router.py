"""Agent Router — selects and instantiates the best agent for a given task type."""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from typing import Any

from app.agents.base import AgentResponse, BaseAgent
from app.agents.claude_agent import ClaudeAgent
from app.agents.codex_agent import CodexAgent
from app.agents.gemini_agent import GeminiAgent

logger = logging.getLogger(__name__)


# ── Stub agent for graceful degradation ──────────────────────────────────


class StubAgent(BaseAgent):
    """No-op agent returned when no real agents can be initialised.

    This allows the application (and test suites) to function without
    configured API keys.  Every call returns a canned response that
    clearly indicates no real AI backend was available.
    """

    name = "stub"
    supported_models = ["stub-v1"]

    async def generate(
        self,
        prompt: str,
        context: str = "",
        *,
        system_prompt: str | None = None,
        model_id: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AgentResponse:
        return AgentResponse(
            content=(
                "[StubAgent] No AI agents are available. "
                "Configure at least one API key "
                "(ANTHROPIC_API_KEY, OPENAI_API_KEY, or GOOGLE_AI_API_KEY) "
                "to enable real AI responses."
            ),
            model_id="stub-v1",
            prompt_tokens=0,
            completion_tokens=0,
            metadata={"stub": True},
        )


_stub_agent = StubAgent()


# ── Agent factories ──────────────────────────────────────────────────────

_AGENT_FACTORIES: dict[str, type[BaseAgent]] = {
    "claude": ClaudeAgent,
    "codex": CodexAgent,
    "gemini": GeminiAgent,
}

# ── Routing table: task_type -> [(agent_name, weight)] ────────────────────
# Weights control the probability of selection.  Higher = more likely.
AGENT_ROUTING_TABLE: dict[str, list[tuple[str, float]]] = {
    "planning": [("claude", 0.8), ("codex", 0.2)],
    "coding": [("claude", 0.5), ("codex", 0.4), ("gemini", 0.1)],
    "test_generation": [("gemini", 0.6), ("claude", 0.3), ("codex", 0.1)],
    "security_review": [("claude", 0.7), ("codex", 0.2), ("gemini", 0.1)],
    "code_review": [("claude", 0.6), ("codex", 0.3), ("gemini", 0.1)],
    "general": [("claude", 0.5), ("codex", 0.3), ("gemini", 0.2)],
}

# ── Fallback chains: agent -> ordered list of fallback agents ─────────────
FALLBACK_CHAIN: dict[str, list[str]] = {
    "claude": ["codex", "gemini"],
    "codex": ["claude", "gemini"],
    "gemini": ["claude", "codex"],
}


# ── Adaptive stats ───────────────────────────────────────────────────────


class _AgentStats:
    """Tracks per-agent success/failure counts for adaptive routing."""

    def __init__(self) -> None:
        self.successes: defaultdict[str, int] = defaultdict(int)
        self.failures: defaultdict[str, int] = defaultdict(int)

    def record_success(self, agent_name: str) -> None:
        self.successes[agent_name] += 1

    def record_failure(self, agent_name: str) -> None:
        self.failures[agent_name] += 1

    def success_rate(self, agent_name: str) -> float:
        total = self.successes[agent_name] + self.failures[agent_name]
        if total == 0:
            return 1.0  # Assume perfect until proven otherwise.
        return self.successes[agent_name] / total

    def adjusted_weights(
        self,
        candidates: list[tuple[str, float]],
    ) -> list[tuple[str, float]]:
        """Return candidates with weights multiplied by their success rate."""
        adjusted: list[tuple[str, float]] = []
        for name, base_weight in candidates:
            rate = self.success_rate(name)
            adjusted.append((name, base_weight * rate))
        return adjusted


_stats = _AgentStats()


# ── Singleton agent cache ────────────────────────────────────────────────

_agent_instances: dict[str, BaseAgent] = {}
_unavailable_agents: dict[str, Exception] = {}


def _get_agent(name: str) -> BaseAgent:
    """Return a cached agent instance, creating it on first access.

    If the agent cannot be instantiated (e.g. missing API key), the error
    is logged and the name is added to ``_unavailable_agents`` so that
    repeated attempts are skipped quickly.
    """
    if name in _unavailable_agents:
        raise _unavailable_agents[name]

    if name not in _agent_instances:
        factory = _AGENT_FACTORIES.get(name)
        if factory is None:
            raise ValueError(f"Unknown agent name: '{name}'")
        try:
            _agent_instances[name] = factory()
            logger.info("Instantiated agent '%s'", name)
        except (ValueError, Exception) as exc:
            logger.warning(
                "Could not initialise agent '%s': %s — it will be unavailable.",
                name,
                exc,
            )
            _unavailable_agents[name] = exc
            raise
    return _agent_instances[name]


def clear_agent_cache() -> None:
    """Clear cached agent instances and unavailability markers (useful for testing)."""
    _agent_instances.clear()
    _unavailable_agents.clear()


# ── Public API ───────────────────────────────────────────────────────────


def route_task(task_type: str) -> BaseAgent:
    """Select an agent for *task_type* using weighted random selection.

    Weights are adjusted by each agent's historical success rate so that
    unreliable agents are naturally down-ranked.

    If the chosen agent (and all candidates) cannot be initialised — for
    example because the required API key is missing — a :class:`StubAgent`
    is returned so the caller always gets a usable object.
    """
    candidates = AGENT_ROUTING_TABLE.get(task_type)
    if not candidates:
        logger.warning("No routing entry for task_type '%s'; using 'general'", task_type)
        candidates = AGENT_ROUTING_TABLE["general"]

    adjusted = _stats.adjusted_weights(candidates)
    names = [name for name, _ in adjusted]
    weights = [w for _, w in adjusted]

    # Normalise weights to avoid zero-sum edge case.
    total_weight = sum(weights)
    if total_weight <= 0:
        # All agents have 0 weight — pick uniformly.
        chosen = random.choice(names)  # noqa: S311 – jitter/backoff, not security
    else:
        chosen = random.choices(names, weights=weights, k=1)[0]  # noqa: S311

    logger.info(
        "Routed task_type='%s' to agent '%s' (candidates=%s)",
        task_type,
        chosen,
        [(n, f"{w:.2f}") for n, w in adjusted],
    )

    # Try the chosen agent first, then remaining candidates, then stub.
    try:
        return _get_agent(chosen)
    except Exception:  # noqa: S110
        pass

    # Walk the remaining candidates in order.
    for name in names:
        if name == chosen:
            continue
        try:
            return _get_agent(name)
        except Exception:  # noqa: S112
            continue

    logger.warning(
        "No agents could be initialised for task_type='%s'; returning StubAgent.",
        task_type,
    )
    return _stub_agent


async def execute_with_fallback(
    agent: BaseAgent,
    prompt: str,
    context: str = "",
    *,
    max_retries: int = 2,
    **kwargs: Any,
) -> AgentResponse:
    """Execute a prompt with the given agent, falling back on failure.

    Tries the primary agent first, then walks the :data:`FALLBACK_CHAIN`
    up to *max_retries* additional attempts.  Records success/failure
    stats for adaptive routing.
    """
    chain = [agent.name] + (FALLBACK_CHAIN.get(agent.name, []))[:max_retries]

    for agent_name in chain:
        try:
            current_agent = _get_agent(agent_name)
        except Exception as exc:
            _stats.record_failure(agent_name)
            logger.warning(
                "Agent '%s' unavailable (%s); trying next in fallback chain.",
                agent_name,
                exc,
            )
            continue

        try:
            response = await current_agent.invoke(prompt=prompt, context=context, **kwargs)
            _stats.record_success(agent_name)
            return response
        except Exception as exc:
            _stats.record_failure(agent_name)
            logger.warning(
                "Agent '%s' failed (%s); trying next in fallback chain.",
                agent_name,
                exc,
            )

    # All agents in the chain failed — fall back to stub.
    logger.warning(
        "All agents in fallback chain %s failed; falling back to StubAgent.",
        chain,
    )
    return await _stub_agent.invoke(prompt=prompt, context=context, **kwargs)
