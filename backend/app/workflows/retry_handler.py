"""Retry handler — self-correction loop for AI agent outputs."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from app.agents.base import AgentResponse, BaseAgent

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Type alias for a validator function.
# Receives the raw response content, returns (success, error_message).
ValidatorFn = Callable[[str], tuple[bool, str]]


async def retry_with_feedback(
    agent: BaseAgent,
    prompt: str,
    validator_fn: ValidatorFn,
    *,
    context: str = "",
    system_prompt: str | None = None,
    max_retries: int = 3,
    **kwargs: Any,
) -> AgentResponse:
    """Execute an agent call with validation and self-correcting retries.

    Implements the multi-step prompting pattern: on each failure the
    validator's error message is appended to the prompt, giving the agent
    progressively richer feedback to correct its output.

    Parameters
    ----------
    agent:
        The AI agent to invoke.
    prompt:
        The initial prompt.
    validator_fn:
        A callable ``(response_content) -> (success: bool, error_msg: str)``.
        When ``success`` is ``False``, *error_msg* is fed back to the agent
        as additional context for the next attempt.
    context:
        Additional context passed to the agent.
    system_prompt:
        System-level instructions.
    max_retries:
        Maximum number of retry attempts (in addition to the first call).
    **kwargs:
        Forwarded to :meth:`BaseAgent.invoke`.

    Returns
    -------
    AgentResponse
        The first response that passes validation.

    Raises
    ------
    ValueError
        If the agent fails validation after all retries.
    """
    accumulated_errors: list[str] = []
    current_prompt = prompt

    for attempt in range(1, max_retries + 2):  # +2 because attempt 1 is the initial try
        response = await agent.invoke(
            prompt=current_prompt,
            context=context,
            system_prompt=system_prompt,
            **kwargs,
        )

        success, error_msg = validator_fn(response.content)
        if success:
            if attempt > 1:
                logger.info(
                    "Agent '%s' passed validation on attempt %d/%d",
                    agent.name,
                    attempt,
                    max_retries + 1,
                )
            response.metadata["retry_count"] = attempt - 1
            response.metadata["validation_errors"] = accumulated_errors
            return response

        accumulated_errors.append(error_msg)
        logger.warning(
            "Agent '%s' failed validation (attempt %d/%d): %s",
            agent.name,
            attempt,
            max_retries + 1,
            error_msg[:500],
        )

        if attempt > max_retries:
            # Exhausted all retries.
            break

        # Build an augmented prompt with progressive error context.
        # Each retry includes ALL prior errors so the agent can see the pattern.
        error_section_parts = []
        for i, err in enumerate(accumulated_errors, 1):
            error_section_parts.append(f"### Attempt {i} Error\n{err}")
        error_section = "\n\n".join(error_section_parts)

        current_prompt = (
            f"{prompt}\n\n"
            f"---\n"
            f"## Previous Attempts Failed Validation\n\n"
            f"{error_section}\n\n"
            f"---\n"
            f"Please fix ALL the issues described above and try again.  "
            f"Pay careful attention to the error messages."
        )

        # Progressively add more context on each retry.
        if attempt >= 2:
            current_prompt += (
                "\n\nIMPORTANT: This is retry attempt #{attempt}.  "
                "Review your output very carefully before responding."
            )

    raise ValueError(
        f"Agent '{agent.name}' failed validation after {max_retries + 1} attempts.  "
        f"Errors: {accumulated_errors}"
    )
