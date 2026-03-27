"""Gemini agent — Google Generative AI wrapper."""

from __future__ import annotations

import logging
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.agents.base import AgentResponse, BaseAgent
from app.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiAgent(BaseAgent):
    """Async wrapper around the Google Generative AI SDK.

    Supports ``gemini-2.5-pro`` and ``gemini-2.5-flash``.
    """

    name = "gemini"
    supported_models = ["gemini-2.5-pro", "gemini-2.5-flash"]

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.GOOGLE_AI_API_KEY
        if not self._api_key:
            raise ValueError("GOOGLE_AI_API_KEY not configured")
        self._client = genai.Client(api_key=self._api_key)

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

        # Build the prompt content.
        user_content = prompt
        if context:
            user_content = f"**Context:**\n{context}\n\n**Task:**\n{prompt}"

        config = genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if system_prompt:
            config.system_instruction = system_prompt

        logger.debug(
            "Calling Gemini model=%s max_tokens=%d temperature=%.2f",
            model,
            max_tokens,
            temperature,
        )

        response = await self._client.aio.models.generate_content(
            model=model,
            contents=user_content,
            config=config,
        )

        content = response.text or ""

        # Extract token counts from usage metadata.
        prompt_tokens = 0
        completion_tokens = 0
        if response.usage_metadata:
            prompt_tokens = response.usage_metadata.prompt_token_count or 0
            completion_tokens = response.usage_metadata.candidates_token_count or 0

        return AgentResponse(
            content=content,
            model_id=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            metadata={
                "finish_reason": (
                    response.candidates[0].finish_reason.name
                    if response.candidates and response.candidates[0].finish_reason
                    else None
                ),
            },
        )
