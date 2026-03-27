"""Unit tests for the agent router: task routing and fallback chains."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.agents.base import AgentResponse, BaseAgent
from app.agents.router import (
    AGENT_ROUTING_TABLE,
    StubAgent,
    _stats,
    clear_agent_cache,
    execute_with_fallback,
    route_task,
)

# Only async tests are individually marked with @pytest.mark.asyncio


class FakeAgent(BaseAgent):
    """A minimal agent for testing routing without real AI calls."""

    def __init__(self, name: str = "fake", should_fail: bool = False) -> None:
        self.name = name
        self.supported_models = ["fake-model"]
        self._should_fail = should_fail

    async def generate(self, prompt: str, context: str = "", **kwargs) -> AgentResponse:
        if self._should_fail:
            raise RuntimeError(f"Agent {self.name} failed")
        return AgentResponse(
            content=f"Response from {self.name}",
            model_id="fake-model",
            prompt_tokens=10,
            completion_tokens=20,
        )


@pytest.fixture(autouse=True)
def _reset_router_state():
    """Clear the agent cache and stats between tests."""
    clear_agent_cache()
    _stats.successes.clear()
    _stats.failures.clear()
    yield
    clear_agent_cache()


class TestRouteTask:
    """Tests for the route_task function."""

    def test_route_task_returns_correct_agent(self) -> None:
        """route_task returns a BaseAgent instance for a known task type."""

        def _fake_get_agent(name: str) -> FakeAgent:
            return FakeAgent(name=name)

        with patch("app.agents.router._get_agent", side_effect=_fake_get_agent):
            agent = route_task("planning")
        assert isinstance(agent, BaseAgent)
        assert agent.name in {"claude", "codex", "gemini"}

    def test_route_task_all_known_types(self) -> None:
        """Every entry in the routing table can be routed without error."""

        def _fake_get_agent(name: str) -> FakeAgent:
            return FakeAgent(name=name)

        with patch("app.agents.router._get_agent", side_effect=_fake_get_agent):
            for task_type in AGENT_ROUTING_TABLE:
                agent = route_task(task_type)
                assert isinstance(agent, BaseAgent)

    def test_route_task_unknown_type_falls_back_to_general(self) -> None:
        """An unknown task type falls back to 'general' routing."""

        def _fake_get_agent(name: str) -> FakeAgent:
            return FakeAgent(name=name)

        with patch("app.agents.router._get_agent", side_effect=_fake_get_agent):
            agent = route_task("nonexistent_task_type")
        assert isinstance(agent, BaseAgent)

    def test_route_task_respects_weighted_selection(self) -> None:
        """Over many calls, all candidate agents should appear at least once.

        This is a probabilistic test — with many iterations and multiple
        weighted candidates, each agent should be selected at least once.
        """

        def _fake_get_agent(name: str) -> FakeAgent:
            return FakeAgent(name=name)

        seen_agents: set[str] = set()
        with patch("app.agents.router._get_agent", side_effect=_fake_get_agent):
            for _ in range(200):
                agent = route_task("coding")
                seen_agents.add(agent.name)

        # With weights [0.5, 0.4, 0.1] over 200 calls, all three agents
        # should appear at least once.
        expected = {name for name, _ in AGENT_ROUTING_TABLE["coding"]}
        assert seen_agents == expected


class TestGracefulDegradation:
    """Tests for graceful degradation when API keys are missing."""

    def test_route_task_returns_stub_when_all_agents_fail(self) -> None:
        """When no agents can be initialised, route_task returns a StubAgent."""

        def _failing_get_agent(name: str) -> BaseAgent:
            raise ValueError(f"{name.upper()}_API_KEY not configured")

        with patch("app.agents.router._get_agent", side_effect=_failing_get_agent):
            agent = route_task("coding")
        assert isinstance(agent, StubAgent)
        assert agent.name == "stub"

    def test_route_task_falls_back_to_available_agent(self) -> None:
        """When the chosen agent fails, route_task tries other candidates."""

        def _selective_get_agent(name: str) -> FakeAgent:
            if name == "claude":
                raise ValueError("ANTHROPIC_API_KEY not configured")
            return FakeAgent(name=name)

        with patch("app.agents.router._get_agent", side_effect=_selective_get_agent):
            agents_seen: set[str] = set()
            for _ in range(50):
                agent = route_task("planning")
                agents_seen.add(agent.name)
        # Should never get claude, but should get at least one of the others.
        assert "claude" not in agents_seen
        assert len(agents_seen) >= 1

    async def test_stub_agent_returns_informative_response(self) -> None:
        """StubAgent.generate() returns a response indicating no agents are available."""
        stub = StubAgent()
        response = await stub.generate("test prompt")
        assert isinstance(response, AgentResponse)
        assert "No AI agents are available" in response.content
        assert response.model_id == "stub-v1"
        assert response.metadata.get("stub") is True

    def test_route_task_without_api_keys_does_not_crash(self) -> None:
        """route_task never raises even when all real agents are unavailable.

        This is the key test for dev/CI environments without API keys.
        """
        # Use the real _get_agent (no mock) — agent constructors will fail
        # because settings.*_API_KEY are None.
        agent = route_task("general")
        assert isinstance(agent, BaseAgent)
        # It could be a StubAgent or a real agent if keys happen to be set.

    async def test_execute_with_fallback_returns_stub_when_all_fail(self) -> None:
        """execute_with_fallback returns a StubAgent response when every agent fails."""
        failing_agent = FakeAgent(name="claude", should_fail=True)

        def mock_get_agent(name: str) -> FakeAgent:
            return FakeAgent(name=name, should_fail=True)

        with patch("app.agents.router._get_agent", side_effect=mock_get_agent):
            response = await execute_with_fallback(
                failing_agent,
                prompt="test prompt",
                max_retries=2,
            )
        assert "StubAgent" in response.content or "No AI agents" in response.content

    async def test_execute_with_fallback_handles_init_failure(self) -> None:
        """execute_with_fallback handles agents that fail to initialise."""
        failing_agent = FakeAgent(name="claude", should_fail=True)
        success_agent = FakeAgent(name="gemini", should_fail=False)

        call_count = 0

        def mock_get_agent(name: str) -> FakeAgent:
            nonlocal call_count
            call_count += 1
            if name == "claude":
                return failing_agent
            if name == "codex":
                raise ValueError("OPENAI_API_KEY not configured")
            return success_agent

        with patch("app.agents.router._get_agent", side_effect=mock_get_agent):
            response = await execute_with_fallback(
                failing_agent,
                prompt="test prompt",
                max_retries=2,
            )
        assert response.content == "Response from gemini"


class TestFallbackChain:
    """Tests for the execute_with_fallback function."""

    async def test_fallback_chain_success_on_first(self) -> None:
        """When the primary agent succeeds, no fallback is attempted."""
        agent = FakeAgent(name="claude", should_fail=False)

        with patch("app.agents.router._get_agent", return_value=agent):
            response = await execute_with_fallback(agent, prompt="test prompt")

        assert response.content == "Response from claude"

    async def test_fallback_chain_tries_next_on_failure(self) -> None:
        """When the primary fails, the fallback agent is tried."""
        failing_agent = FakeAgent(name="claude", should_fail=True)
        success_agent = FakeAgent(name="codex", should_fail=False)

        call_count = 0

        def mock_get_agent(name: str) -> FakeAgent:
            nonlocal call_count
            call_count += 1
            if name == "claude":
                return failing_agent
            return success_agent

        with patch("app.agents.router._get_agent", side_effect=mock_get_agent):
            response = await execute_with_fallback(
                failing_agent,
                prompt="test prompt",
                max_retries=2,
            )

        assert response.content == "Response from codex"
        assert call_count >= 2

    async def test_fallback_chain_all_fail_returns_stub(self) -> None:
        """When all agents in the chain fail, a StubAgent response is returned."""
        failing_agent = FakeAgent(name="claude", should_fail=True)

        def mock_get_agent(name: str) -> FakeAgent:
            return FakeAgent(name=name, should_fail=True)

        with patch("app.agents.router._get_agent", side_effect=mock_get_agent):
            response = await execute_with_fallback(
                failing_agent,
                prompt="test prompt",
                max_retries=2,
            )
        assert "StubAgent" in response.content or "No AI agents" in response.content

    async def test_fallback_chain_records_stats(self) -> None:
        """Success and failure stats are recorded during fallback."""
        failing_agent = FakeAgent(name="claude", should_fail=True)
        success_agent = FakeAgent(name="codex", should_fail=False)

        def mock_get_agent(name: str) -> FakeAgent:
            if name == "claude":
                return failing_agent
            return success_agent

        with patch("app.agents.router._get_agent", side_effect=mock_get_agent):
            await execute_with_fallback(
                failing_agent,
                prompt="test prompt",
                max_retries=2,
            )

        assert _stats.failures["claude"] >= 1
        assert _stats.successes["codex"] >= 1
