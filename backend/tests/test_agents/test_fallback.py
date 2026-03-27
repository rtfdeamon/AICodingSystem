"""Tests for app.agents.fallback — execute_with_chain logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, PropertyMock

import pytest

from app.agents.base import AgentResponse, BaseAgent
from app.agents.fallback import execute_with_chain

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(name: str, side_effect=None, response: AgentResponse | None = None) -> BaseAgent:
    """Create a mock BaseAgent with the given name and invoke behaviour."""
    agent = AsyncMock(spec=BaseAgent)
    type(agent).name = PropertyMock(return_value=name)
    if side_effect is not None:
        agent.invoke.side_effect = side_effect
    elif response is not None:
        agent.invoke.return_value = response
    return agent


def _ok_response(content: str = "ok", model_id: str = "test-model") -> AgentResponse:
    return AgentResponse(content=content, model_id=model_id, metadata={})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_chain_raises_value_error():
    with pytest.raises(ValueError, match="must not be empty"):
        await execute_with_chain([], prompt="hello")


@pytest.mark.asyncio
async def test_first_agent_succeeds():
    agent = _make_agent("agent-a", response=_ok_response("answer"))
    result = await execute_with_chain([agent], prompt="hi", context="ctx")
    assert result.content == "answer"
    agent.invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_first_fails_second_succeeds():
    failing = _make_agent("bad", side_effect=RuntimeError("boom"))
    good = _make_agent("good", response=_ok_response("success"))
    result = await execute_with_chain([failing, good], prompt="p")
    assert result.content == "success"
    failing.invoke.assert_awaited_once()
    good.invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_agents_fail_raises_runtime_error():
    a = _make_agent("a", side_effect=RuntimeError("err1"))
    b = _make_agent("b", side_effect=RuntimeError("err2"))
    with pytest.raises(RuntimeError, match="All agents in chain"):
        await execute_with_chain([a, b], prompt="p")


@pytest.mark.asyncio
async def test_timeout_error_handled():
    """TimeoutError on the first agent is caught and the chain continues."""
    slow = _make_agent("slow", side_effect=TimeoutError("timed out"))
    fast = _make_agent("fast", response=_ok_response("fast-reply"))
    result = await execute_with_chain([slow, fast], prompt="p")
    assert result.content == "fast-reply"


@pytest.mark.asyncio
async def test_fallback_metadata_populated():
    failing = _make_agent("bad", side_effect=ValueError("oops"))
    good = _make_agent("good", response=_ok_response("ok"))
    result = await execute_with_chain([failing, good], prompt="p")

    assert result.metadata["fallback_chain_tried"] == ["bad", "good"]
    assert len(result.metadata["fallback_errors"]) == 1
    assert result.metadata["fallback_errors"][0]["agent"] == "bad"
    assert "oops" in result.metadata["fallback_errors"][0]["error"]


@pytest.mark.asyncio
async def test_kwargs_forwarded_to_agents():
    agent = _make_agent("a", response=_ok_response())
    await execute_with_chain(
        [agent], prompt="p", context="c", timeout_per_agent=30, db="fake_db", ticket_id=42
    )
    _, kwargs = agent.invoke.call_args
    assert kwargs["db"] == "fake_db"
    assert kwargs["ticket_id"] == 42
    assert kwargs["timeout"] == 30
