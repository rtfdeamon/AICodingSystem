"""Tests for app.context.embeddings — embedding generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.context.embeddings import (
    EMBEDDING_DIM,
    MAX_BATCH_SIZE,
    MODEL_NAME,
    EmbeddingService,
)

# ── Constructor ──────────────────────────────────────────────────────


class TestEmbeddingServiceInit:
    def test_uses_provided_key(self) -> None:
        svc = EmbeddingService(api_key="sk-test123")
        assert svc._api_key == "sk-test123"

    def test_falls_back_to_settings(self) -> None:
        with patch("app.context.embeddings.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-from-settings"
            svc = EmbeddingService()
        assert svc._api_key == "sk-from-settings"

    def test_available_with_key(self) -> None:
        svc = EmbeddingService(api_key="sk-test")
        assert svc._available is True

    def test_not_available_without_key(self) -> None:
        with patch("app.context.embeddings.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            svc = EmbeddingService()
        assert svc._available is False


# ── _zero_vector ─────────────────────────────────────────────────────


class TestZeroVector:
    def test_correct_dimension(self) -> None:
        svc = EmbeddingService(api_key="sk-test")
        vec = svc._zero_vector()
        assert len(vec) == EMBEDDING_DIM
        assert all(v == 0.0 for v in vec)


# ── _call_api ────────────────────────────────────────────────────────


class TestCallApi:
    async def test_sends_correct_payload(self) -> None:
        svc = EmbeddingService(api_key="sk-test")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"index": 0, "embedding": [0.1] * EMBEDDING_DIM},
                {"index": 1, "embedding": [0.2] * EMBEDDING_DIM},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await svc._call_api(["hello", "world"])

        assert len(result) == 2
        assert result[0][0] == 0.1
        assert result[1][0] == 0.2

    async def test_sorts_by_index(self) -> None:
        svc = EmbeddingService(api_key="sk-test")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"index": 1, "embedding": [0.2] * EMBEDDING_DIM},
                {"index": 0, "embedding": [0.1] * EMBEDDING_DIM},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await svc._call_api(["a", "b"])

        # Should be sorted by index
        assert result[0][0] == 0.1
        assert result[1][0] == 0.2


# ── embed_texts ──────────────────────────────────────────────────────


class TestEmbedTexts:
    async def test_empty_list_returns_empty(self) -> None:
        svc = EmbeddingService(api_key="sk-test")
        result = await svc.embed_texts([])
        assert result == []

    async def test_returns_zero_vectors_when_unavailable(self) -> None:
        with patch("app.context.embeddings.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            svc = EmbeddingService()

        result = await svc.embed_texts(["hello", "world"])
        assert len(result) == 2
        assert all(v == 0.0 for v in result[0])
        assert len(result[0]) == EMBEDDING_DIM

    async def test_successful_embedding(self) -> None:
        svc = EmbeddingService(api_key="sk-test")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"index": 0, "embedding": [0.5] * EMBEDDING_DIM}]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await svc.embed_texts(["test text"])

        assert len(result) == 1
        assert result[0][0] == 0.5

    async def test_sanitizes_empty_strings(self) -> None:
        svc = EmbeddingService(api_key="sk-test")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"index": 0, "embedding": [0.1] * EMBEDDING_DIM},
                {"index": 1, "embedding": [0.2] * EMBEDDING_DIM},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await svc.embed_texts(["hello", ""])

        # Should succeed (empty string replaced with " ")
        assert len(result) == 2
        # Verify the API was called with sanitized input
        call_json = mock_client.post.call_args[1]["json"]
        assert call_json["input"][1] == " "

    async def test_handles_http_status_error(self) -> None:
        svc = EmbeddingService(api_key="sk-test")

        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "rate limit", request=mock_request, response=mock_response
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await svc.embed_texts(["test"])

        # Should return zero vectors on error
        assert len(result) == 1
        assert all(v == 0.0 for v in result[0])

    async def test_handles_request_error(self) -> None:
        svc = EmbeddingService(api_key="sk-test")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.RequestError("connection timeout")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await svc.embed_texts(["test"])

        assert len(result) == 1
        assert all(v == 0.0 for v in result[0])

    async def test_batching_large_input(self) -> None:
        svc = EmbeddingService(api_key="sk-test")

        call_count = 0

        async def mock_call_api(texts):
            nonlocal call_count
            call_count += 1
            return [[0.1] * EMBEDDING_DIM for _ in texts]

        with patch.object(svc, "_call_api", side_effect=mock_call_api):
            # Create input larger than MAX_BATCH_SIZE
            texts = ["text"] * (MAX_BATCH_SIZE + 10)
            result = await svc.embed_texts(texts)

        assert len(result) == MAX_BATCH_SIZE + 10
        assert call_count == 2  # Should be split into 2 batches


# ── embed_single ─────────────────────────────────────────────────────


class TestEmbedSingle:
    async def test_embeds_single_text(self) -> None:
        svc = EmbeddingService(api_key="sk-test")

        with patch.object(
            svc, "embed_texts", return_value=[[0.42] * EMBEDDING_DIM]
        ):
            result = await svc.embed_single("hello world")

        assert len(result) == EMBEDDING_DIM
        assert result[0] == 0.42


# ── Constants ────────────────────────────────────────────────────────


class TestConstants:
    def test_model_name(self) -> None:
        assert MODEL_NAME == "text-embedding-3-small"

    def test_embedding_dim(self) -> None:
        assert EMBEDDING_DIM == 1536

    def test_max_batch_size(self) -> None:
        assert MAX_BATCH_SIZE == 2048
