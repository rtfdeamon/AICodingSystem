"""Tests for retry_handler — self-correction loop for AI agent outputs."""

from __future__ import annotations

import pytest

from app.agents.base import AgentResponse, BaseAgent
from app.workflows.retry_handler import retry_with_feedback

# ---------------------------------------------------------------------------
# Fake agent for testing
# ---------------------------------------------------------------------------


class FakeAgent(BaseAgent):
    """Minimal BaseAgent subclass for testing retry_with_feedback."""

    name = "fake"
    supported_models = ["fake-model"]

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self._call_index = 0

    async def generate(self, prompt, context="", **kwargs):
        content = self._responses[self._call_index]
        self._call_index += 1
        return AgentResponse(
            content=content,
            model_id="fake-model",
            prompt_tokens=10,
            completion_tokens=20,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _always_pass(content: str) -> tuple[bool, str]:
    return True, ""


def _always_fail(content: str) -> tuple[bool, str]:
    return False, f"'{content}' is invalid"


def _always_fail_simple(content: str) -> tuple[bool, str]:
    return False, "always fails"


async def test_passes_on_first_attempt():
    """Returns immediately when first response passes validation."""
    agent = FakeAgent(["valid output"])

    response = await retry_with_feedback(agent, "test prompt", _always_pass)

    assert response.content == "valid output"
    assert response.metadata.get("retry_count", 0) == 0


async def test_passes_on_second_attempt():
    """Retries and succeeds on second attempt."""
    agent = FakeAgent(["bad output", "valid output"])
    call_count = 0

    def validator(content: str) -> tuple[bool, str]:
        nonlocal call_count
        call_count += 1
        if content == "valid output":
            return True, ""
        return False, "Output is invalid"

    response = await retry_with_feedback(
        agent,
        "test prompt",
        validator,
        max_retries=3,
    )

    assert response.content == "valid output"
    assert response.metadata["retry_count"] == 1


async def test_exhausts_retries_raises():
    """Raises ValueError after exhausting all retries."""
    agent = FakeAgent(["bad"] * 5)

    with pytest.raises(ValueError, match="failed validation after"):
        await retry_with_feedback(
            agent,
            "test prompt",
            _always_fail,
            max_retries=2,
        )


async def test_retry_count_in_metadata():
    """Records retry count in response metadata."""
    agent = FakeAgent(["fail", "fail", "success"])

    def validator(content: str) -> tuple[bool, str]:
        if content == "success":
            return True, ""
        return False, "not success"

    response = await retry_with_feedback(
        agent,
        "prompt",
        validator,
        max_retries=3,
    )

    assert response.metadata["retry_count"] == 2
    assert len(response.metadata["validation_errors"]) == 2


async def test_validation_errors_accumulated():
    """All validation errors are accumulated in metadata."""
    agent = FakeAgent(["a", "b", "c", "good"])

    def validator(content: str) -> tuple[bool, str]:
        if content == "good":
            return True, ""
        return False, f"Error: {content} is not good"

    response = await retry_with_feedback(
        agent,
        "prompt",
        validator,
        max_retries=5,
    )

    errors = response.metadata["validation_errors"]
    assert len(errors) == 3
    assert "Error: a is not good" in errors[0]
    assert "Error: b is not good" in errors[1]
    assert "Error: c is not good" in errors[2]


async def test_max_retries_zero():
    """With max_retries=0, only the initial attempt is made."""
    agent = FakeAgent(["bad"])

    with pytest.raises(ValueError, match="failed validation after 1 attempts"):
        await retry_with_feedback(
            agent,
            "prompt",
            _always_fail_simple,
            max_retries=0,
        )


async def test_context_and_system_prompt_forwarded():
    """Context and system_prompt are passed to the agent."""
    captured_kwargs = {}

    class CapturingAgent(BaseAgent):
        name = "capture"
        supported_models = ["fake"]

        async def generate(self, prompt, context="", **kwargs):
            captured_kwargs["context"] = context
            captured_kwargs["system_prompt"] = kwargs.get("system_prompt")
            return AgentResponse(content="ok", model_id="fake")

    agent = CapturingAgent()

    await retry_with_feedback(
        agent,
        "prompt",
        _always_pass,
        context="test context",
        system_prompt="be helpful",
    )

    assert captured_kwargs["context"] == "test context"
    assert captured_kwargs["system_prompt"] == "be helpful"
