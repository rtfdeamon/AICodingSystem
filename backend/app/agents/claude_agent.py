"""Claude agent — Anthropic Claude API wrapper."""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from app.agents.base import AgentResponse, BaseAgent
from app.config import settings

logger = logging.getLogger(__name__)

# Default model when none is specified.
_DEFAULT_MODEL = "claude-sonnet-4-6"


class ClaudeAgent(BaseAgent):
    """Async wrapper around the Anthropic Messages API.

    Supports ``claude-sonnet-4-6`` (fast, cost-effective) and
    ``claude-opus-4-6`` (highest capability).
    """

    name = "claude"
    supported_models = ["claude-sonnet-4-6", "claude-opus-4-6"]

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.ANTHROPIC_API_KEY
        if not self._api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        self._client = anthropic.AsyncAnthropic(api_key=self._api_key)

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
        model = model_id or _DEFAULT_MODEL
        if model not in self.supported_models:
            logger.warning(
                "Requested model '%s' not in supported list; falling back to '%s'",
                model,
                _DEFAULT_MODEL,
            )
            model = _DEFAULT_MODEL

        # Build the user message with optional context section.
        user_content = prompt
        if context:
            user_content = f"<context>\n{context}\n</context>\n\n<task>\n{prompt}\n</task>"

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_content},
        ]

        request_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            request_kwargs["system"] = system_prompt

        logger.debug(
            "Calling Claude model=%s max_tokens=%d temperature=%.2f",
            model,
            max_tokens,
            temperature,
        )

        response = await self._client.messages.create(**request_kwargs)

        # Extract the text content from the response.
        content_blocks = response.content
        text_parts: list[str] = []
        for block in content_blocks:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        content = "\n".join(text_parts)

        return AgentResponse(
            content=content,
            model_id=response.model,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            metadata={
                "stop_reason": response.stop_reason,
                "id": response.id,
            },
        )
