"""Tests for app.agents.gemini_agent — Google Generative AI wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import AgentResponse

# ── Constructor ──────────────────────────────────────────────────────


class TestGeminiAgentInit:
    def test_raises_without_api_key(self) -> None:
        with patch("app.agents.gemini_agent.settings") as mock_settings:
            mock_settings.GOOGLE_AI_API_KEY = ""
            from app.agents.gemini_agent import GeminiAgent

            with pytest.raises(ValueError, match="GOOGLE_AI_API_KEY"):
                GeminiAgent()

    def test_creates_with_provided_key(self) -> None:
        with patch("app.agents.gemini_agent.genai") as mock_genai:
            mock_genai.Client = MagicMock()
            from app.agents.gemini_agent import GeminiAgent

            agent = GeminiAgent(api_key="test-key-123")
            assert agent._api_key == "test-key-123"
            mock_genai.Client.assert_called_once_with(api_key="test-key-123")

    def test_class_attributes(self) -> None:
        from app.agents.gemini_agent import GeminiAgent

        assert GeminiAgent.name == "gemini"
        assert "gemini-2.5-pro" in GeminiAgent.supported_models
        assert "gemini-2.5-flash" in GeminiAgent.supported_models


# ── generate ─────────────────────────────────────────────────────────


class TestGeminiAgentGenerate:
    async def test_generate_basic(self) -> None:
        with patch("app.agents.gemini_agent.genai") as mock_genai:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client

            # Create mock response
            mock_response = MagicMock()
            mock_response.text = "Generated code here"
            mock_response.usage_metadata = MagicMock()
            mock_response.usage_metadata.prompt_token_count = 50
            mock_response.usage_metadata.candidates_token_count = 100
            mock_candidate = MagicMock()
            mock_candidate.finish_reason = MagicMock()
            mock_candidate.finish_reason.name = "STOP"
            mock_response.candidates = [mock_candidate]

            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            from app.agents.gemini_agent import GeminiAgent

            agent = GeminiAgent(api_key="test-key")
            result = await agent.generate("Write hello world")

        assert isinstance(result, AgentResponse)
        assert result.content == "Generated code here"
        assert result.prompt_tokens == 50
        assert result.completion_tokens == 100

    async def test_generate_with_context(self) -> None:
        with patch("app.agents.gemini_agent.genai") as mock_genai:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = "result"
            mock_response.usage_metadata = None
            mock_response.candidates = []

            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            from app.agents.gemini_agent import GeminiAgent

            agent = GeminiAgent(api_key="test-key")
            result = await agent.generate("task", context="some context")

        assert result.content == "result"
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0

    async def test_generate_unsupported_model_falls_back(self) -> None:
        with patch("app.agents.gemini_agent.genai") as mock_genai:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = "ok"
            mock_response.usage_metadata = None
            mock_response.candidates = []

            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            from app.agents.gemini_agent import GeminiAgent

            agent = GeminiAgent(api_key="test-key")
            result = await agent.generate("task", model_id="gemini-unknown-99")

        assert result.model_id == "gemini-2.5-flash"

    async def test_generate_with_system_prompt(self) -> None:
        with patch("app.agents.gemini_agent.genai") as mock_genai:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = "system response"
            mock_response.usage_metadata = None
            mock_response.candidates = []

            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            from app.agents.gemini_agent import GeminiAgent

            agent = GeminiAgent(api_key="test-key")
            result = await agent.generate(
                "task",
                system_prompt="You are an expert.",
            )

        assert result.content == "system response"

    async def test_generate_empty_response(self) -> None:
        with patch("app.agents.gemini_agent.genai") as mock_genai:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = None  # Empty response
            mock_response.usage_metadata = None
            mock_response.candidates = []

            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            from app.agents.gemini_agent import GeminiAgent

            agent = GeminiAgent(api_key="test-key")
            result = await agent.generate("task")

        assert result.content == ""

    async def test_finish_reason_extraction(self) -> None:
        with patch("app.agents.gemini_agent.genai") as mock_genai:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client

            mock_response = MagicMock()
            mock_response.text = "done"
            mock_response.usage_metadata = MagicMock()
            mock_response.usage_metadata.prompt_token_count = 10
            mock_response.usage_metadata.candidates_token_count = 20
            mock_candidate = MagicMock()
            mock_candidate.finish_reason = None
            mock_response.candidates = [mock_candidate]

            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            from app.agents.gemini_agent import GeminiAgent

            agent = GeminiAgent(api_key="test-key")
            result = await agent.generate("task")

        assert result.metadata["finish_reason"] is None
