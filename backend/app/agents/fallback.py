"""Fallback execution logic — tries a chain of agents until one succeeds."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import DEFAULT_TIMEOUT_S, AgentResponse, BaseAgent

logger = logging.getLogger(__name__)


async def execute_with_chain(
    agents_chain: list[BaseAgent],
    prompt: str,
    context: str = "",
    *,
    timeout_per_agent: float = DEFAULT_TIMEOUT_S,
    **kwargs: Any,
) -> AgentResponse:
    """Try each agent in *agents_chain* sequentially, returning the first success.

    Parameters
    ----------
    agents_chain:
        Ordered list of agent instances to try.
    prompt:
        The prompt to send.
    context:
        Additional context for the prompt.
    timeout_per_agent:
        Maximum seconds to wait for each individual agent call.
    **kwargs:
        Forwarded to :meth:`BaseAgent.invoke` (e.g. ``db``, ``ticket_id``).

    Returns
    -------
    AgentResponse
        The response from the first agent that succeeds.

    Raises
    ------
    RuntimeError
        If every agent in the chain fails.
    """
    if not agents_chain:
        raise ValueError("agents_chain must not be empty")

    errors: list[tuple[str, Exception]] = []

    for agent in agents_chain:
        try:
            logger.info("Attempting agent '%s' in fallback chain", agent.name)
            response = await agent.invoke(
                prompt=prompt,
                context=context,
                timeout=timeout_per_agent,
                **kwargs,
            )
            logger.info(
                "Agent '%s' succeeded in fallback chain (after %d prior failure(s))",
                agent.name,
                len(errors),
            )

            # Annotate the response with fallback metadata.
            response.metadata["fallback_chain_tried"] = [name for name, _ in errors] + [agent.name]
            response.metadata["fallback_errors"] = [
                {"agent": name, "error": str(exc)} for name, exc in errors
            ]
            return response

        except TimeoutError as exc:
            logger.warning(
                "Agent '%s' timed out after %.1fs in fallback chain",
                agent.name,
                timeout_per_agent,
            )
            errors.append((agent.name, exc))

        except Exception as exc:
            logger.warning(
                "Agent '%s' failed in fallback chain: %s: %s",
                agent.name,
                type(exc).__name__,
                exc,
            )
            errors.append((agent.name, exc))

    # All agents exhausted.
    agent_names = [a.name for a in agents_chain]
    error_summary = "; ".join(f"{name}: {exc}" for name, exc in errors)
    raise RuntimeError(f"All agents in chain {agent_names} failed. Errors: {error_summary}")
