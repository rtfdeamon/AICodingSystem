"""Codex agent — OpenAI Chat Completions API wrapper."""

from __future__ import annotations

import logging
from typing import Any

import openai

from app.agents.base import AgentResponse, BaseAgent
from app.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o"


class CodexAgent(BaseAgent):
    """Async wrapper around OpenAI Chat Completions.

    Named *Codex* for legacy continuity; uses ``gpt-4o`` and ``gpt-4o-mini``.
    """

    name = "codex"
    supported_models = ["gpt-4o", "gpt-4o-mini"]

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.OPENAI_API_KEY
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY not configured")
        self._client = openai.AsyncOpenAI(api_key=self._api_key)

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

        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_content = prompt
        if context:
            user_content = f"### Context\n{context}\n\n### Task\n{prompt}"
        messages.append({"role": "user", "content": user_content})

        logger.debug(
            "Calling OpenAI model=%s max_tokens=%d temperature=%.2f",
            model,
            max_tokens,
            temperature,
        )

        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
        )

        choice = response.choices[0]
        content = choice.message.content or ""

        return AgentResponse(
            content=content,
            model_id=response.model,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
            metadata={
                "finish_reason": choice.finish_reason,
                "id": response.id,
            },
        )
