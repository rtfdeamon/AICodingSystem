"""BaseAgent — abstract foundation for all AI provider agents."""

from __future__ import annotations

import abc
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AiLog, AiLogStatus

logger = logging.getLogger(__name__)


# ── Token pricing (USD per 1 000 tokens) ────────────────────────────────
# Updated as of early 2026.  Add new models here when available.
TOKEN_PRICES: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "claude-opus-4-6": {"input": 0.015, "output": 0.075},
    # OpenAI
    "gpt-4o": {"input": 0.0025, "output": 0.010},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    # Google
    "gemini-2.5-pro": {"input": 0.00125, "output": 0.005},
    "gemini-2.5-flash": {"input": 0.00015, "output": 0.0006},
}

# Default timeout for a single agent call (seconds).
DEFAULT_TIMEOUT_S: float = 120.0


@dataclass
class AgentResponse:
    """Standardised response from any AI agent."""

    content: str
    model_id: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


def calculate_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return estimated USD cost for the given token counts.

    Falls back to zero if the model is not in the pricing table.
    """
    prices = TOKEN_PRICES.get(model_id)
    if prices is None:
        logger.warning("No pricing data for model '%s'; cost will be reported as $0", model_id)
        return 0.0
    return (prompt_tokens / 1_000) * prices["input"] + (completion_tokens / 1_000) * prices[
        "output"
    ]


def validate_output(response: dict, schema: type[BaseModel]) -> dict:
    """Validate an AI response dict against a Pydantic model schema.

    Returns the validated (and potentially coerced) dict if validation succeeds,
    or the original *response* unchanged if validation fails (graceful degradation).
    """
    try:
        validated = schema.model_validate(response)
        return validated.model_dump()
    except ValidationError as exc:
        logger.warning(
            "Output validation failed against %s: %s",
            schema.__name__,
            exc,
        )
        return response


class BaseAgent(abc.ABC):
    """Abstract base for every AI provider wrapper.

    Subclasses must implement :meth:`generate`.  The wrapper method
    :meth:`invoke` adds logging, cost tracking, and timeout handling.
    """

    name: str  # e.g. "claude", "codex", "gemini"
    supported_models: list[str]

    # ------------------------------------------------------------------
    # Abstract
    # ------------------------------------------------------------------

    @abc.abstractmethod
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
        """Send a request to the AI provider and return a structured response.

        Parameters
        ----------
        prompt:
            The user/task prompt.
        context:
            Additional context (e.g. relevant code snippets).
        system_prompt:
            An optional system-level instruction.
        model_id:
            Override the default model for this agent.
        temperature:
            Sampling temperature.
        max_tokens:
            Maximum tokens to generate.
        """

    # ------------------------------------------------------------------
    # Wrapper that logs every call
    # ------------------------------------------------------------------

    async def invoke(
        self,
        prompt: str,
        context: str = "",
        *,
        db: AsyncSession | None = None,
        ticket_id: uuid.UUID | None = None,
        action_type: str = "general",
        system_prompt: str | None = None,
        model_id: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: float = DEFAULT_TIMEOUT_S,
        **kwargs: Any,
    ) -> AgentResponse:
        """Call :meth:`generate` with logging, cost calculation, and error handling.

        If *db* is provided, persists an :class:`AiLog` row.
        """
        import asyncio

        start = time.perf_counter()
        response: AgentResponse | None = None
        log_status = AiLogStatus.SUCCESS
        error_msg: str | None = None

        try:
            response = await asyncio.wait_for(
                self.generate(
                    prompt,
                    context,
                    system_prompt=system_prompt,
                    model_id=model_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                ),
                timeout=timeout,
            )
            elapsed_ms = int((time.perf_counter() - start) * 1_000)
            response.latency_ms = elapsed_ms
            response.cost_usd = calculate_cost(
                response.model_id,
                response.prompt_tokens,
                response.completion_tokens,
            )
            logger.info(
                "Agent '%s' (%s) completed in %dms — %d prompt / %d completion tokens, $%.4f",
                self.name,
                response.model_id,
                elapsed_ms,
                response.prompt_tokens,
                response.completion_tokens,
                response.cost_usd,
            )
            return response

        except TimeoutError:
            elapsed_ms = int((time.perf_counter() - start) * 1_000)
            log_status = AiLogStatus.TIMEOUT
            error_msg = f"Agent '{self.name}' timed out after {timeout}s"
            logger.error(error_msg)
            raise

        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1_000)
            log_status = AiLogStatus.ERROR
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception("Agent '%s' failed: %s", self.name, error_msg)
            raise

        finally:
            if db is not None:
                try:
                    log_entry = AiLog(
                        ticket_id=ticket_id,
                        agent_name=self.name,
                        action_type=action_type,
                        model_id=(
                            response.model_id
                            if response
                            else (model_id or self.supported_models[0])
                        ),
                        prompt_text=prompt[:10_000] if prompt else None,
                        response_text=(response.content[:10_000] if response else None),
                        prompt_tokens=response.prompt_tokens if response else 0,
                        completion_tokens=response.completion_tokens if response else 0,
                        cost_usd=response.cost_usd if response else 0.0,
                        latency_ms=elapsed_ms,
                        status=log_status,
                        error_message=error_msg,
                        metadata=response.metadata if response else None,
                    )
                    db.add(log_entry)
                    await db.flush()
                except Exception:
                    logger.exception("Failed to persist AiLog entry")
