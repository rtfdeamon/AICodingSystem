"""Tests for AI agent provider wrappers (Claude, Codex, Gemini) and BaseAgent."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentResponse, BaseAgent, calculate_cost

# ── calculate_cost ────────────────────────────────────────────────────


def test_calculate_cost_known_model() -> None:
    cost = calculate_cost("gpt-4o", prompt_tokens=1000, completion_tokens=500)
    expected = (1000 / 1000) * 0.0025 + (500 / 1000) * 0.010
    assert abs(cost - expected) < 1e-6


def test_calculate_cost_unknown_model() -> None:
    cost = calculate_cost("unknown-model", prompt_tokens=100, completion_tokens=100)
    assert cost == 0.0


def test_calculate_cost_claude() -> None:
    cost = calculate_cost("claude-sonnet-4-6", prompt_tokens=2000, completion_tokens=1000)
    expected = (2000 / 1000) * 0.003 + (1000 / 1000) * 0.015
    assert abs(cost - expected) < 1e-6


def test_calculate_cost_gemini() -> None:
    cost = calculate_cost("gemini-2.5-flash", prompt_tokens=1000, completion_tokens=1000)
    expected = (1000 / 1000) * 0.00015 + (1000 / 1000) * 0.0006
    assert abs(cost - expected) < 1e-6


# ── AgentResponse ─────────────────────────────────────────────────────


def test_agent_response_defaults() -> None:
    r = AgentResponse(content="hello", model_id="test")
    assert r.prompt_tokens == 0
    assert r.completion_tokens == 0
    assert r.cost_usd == 0.0
    assert r.latency_ms == 0
    assert r.metadata == {}


# ── BaseAgent.invoke ──────────────────────────────────────────────────


class StubAgent(BaseAgent):
    """A concrete stub for testing BaseAgent.invoke."""

    name = "stub"
    supported_models = ["stub-1"]

    def __init__(self, response: AgentResponse | None = None, error: Exception | None = None):
        self._response = response
        self._error = error

    async def generate(self, prompt: str, context: str = "", **kwargs: Any) -> AgentResponse:
        if self._error:
            raise self._error
        return self._response or AgentResponse(
            content="stub response",
            model_id="stub-1",
            prompt_tokens=10,
            completion_tokens=20,
        )


@pytest.mark.asyncio
async def test_invoke_success() -> None:
    agent = StubAgent()
    result = await agent.invoke("test prompt")
    assert result.content == "stub response"
    assert result.latency_ms >= 0
    assert result.cost_usd == 0.0  # unknown model "stub-1"


@pytest.mark.asyncio
async def test_invoke_with_db_logging(db_session: AsyncSession) -> None:
    agent = StubAgent()
    ticket_id = uuid.uuid4()
    result = await agent.invoke(
        "test prompt",
        db=db_session,
        ticket_id=ticket_id,
        action_type="planning",
    )
    assert result.content == "stub response"


@pytest.mark.asyncio
async def test_invoke_error_raises() -> None:
    agent = StubAgent(error=ValueError("API error"))
    with pytest.raises(ValueError, match="API error"):
        await agent.invoke("test prompt")


@pytest.mark.asyncio
async def test_invoke_timeout() -> None:
    import asyncio

    class SlowAgent(BaseAgent):
        name = "slow"
        supported_models = ["slow-1"]

        async def generate(self, prompt: str, context: str = "", **kwargs: Any) -> AgentResponse:
            await asyncio.sleep(10)
            return AgentResponse(content="late", model_id="slow-1")

    agent = SlowAgent()
    with pytest.raises(TimeoutError):
        await agent.invoke("test", timeout=0.01)


# ── ClaudeAgent ───────────────────────────────────────────────────────


def test_claude_agent_requires_key() -> None:
    with patch("app.agents.claude_agent.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = ""
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            from app.agents.claude_agent import ClaudeAgent

            ClaudeAgent()


@pytest.mark.asyncio
@patch("anthropic.AsyncAnthropic")
async def test_claude_agent_generate(mock_anthropic_cls: MagicMock) -> None:
    mock_client = AsyncMock()
    mock_anthropic_cls.return_value = mock_client

    @dataclass
    class _TextBlock:
        text: str = "Generated code"

    @dataclass
    class _Usage:
        input_tokens: int = 100
        output_tokens: int = 200

    mock_response = MagicMock()
    mock_response.content = [_TextBlock()]
    mock_response.model = "claude-sonnet-4-6"
    mock_response.usage = _Usage()
    mock_response.stop_reason = "end_turn"
    mock_response.id = "msg_123"
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("app.agents.claude_agent.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        from app.agents.claude_agent import ClaudeAgent

        agent = ClaudeAgent(api_key="test-key")
        agent._client = mock_client

    result = await agent.generate("Write a function", context="existing code")
    assert result.content == "Generated code"
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 200


# ── CodexAgent ────────────────────────────────────────────────────────


def test_codex_agent_requires_key() -> None:
    with patch("app.agents.codex_agent.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = ""
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            from app.agents.codex_agent import CodexAgent

            CodexAgent()


@pytest.mark.asyncio
@patch("openai.AsyncOpenAI")
async def test_codex_agent_generate(mock_openai_cls: MagicMock) -> None:
    mock_client = AsyncMock()
    mock_openai_cls.return_value = mock_client

    mock_message = MagicMock()
    mock_message.content = "OpenAI response"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 50
    mock_usage.completion_tokens = 150
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o"
    mock_response.usage = mock_usage
    mock_response.id = "chatcmpl-123"
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.agents.codex_agent.settings") as mock_settings:
        mock_settings.OPENAI_API_KEY = "test-key"
        from app.agents.codex_agent import CodexAgent

        agent = CodexAgent(api_key="test-key")
        agent._client = mock_client

    result = await agent.generate("Write tests", system_prompt="You are a tester")
    assert result.content == "OpenAI response"
    assert result.prompt_tokens == 50


# ── GeminiAgent ───────────────────────────────────────────────────────


def test_gemini_agent_requires_key() -> None:
    with patch("app.agents.gemini_agent.settings") as mock_settings:
        mock_settings.GOOGLE_AI_API_KEY = ""
        with pytest.raises(ValueError, match="GOOGLE_AI_API_KEY"):
            from app.agents.gemini_agent import GeminiAgent

            GeminiAgent()
