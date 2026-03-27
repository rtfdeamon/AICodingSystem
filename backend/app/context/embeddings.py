"""Embedding generation using OpenAI text-embedding-3-small."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings"
MODEL_NAME = "text-embedding-3-small"
EMBEDDING_DIM = 1536
MAX_BATCH_SIZE = 2048


class EmbeddingService:
    """Generate text embeddings via the OpenAI API.

    If ``OPENAI_API_KEY`` is not configured, returns zero vectors so the
    system can run in development without an API key.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.OPENAI_API_KEY

    @property
    def _available(self) -> bool:
        return bool(self._api_key)

    def _zero_vector(self) -> list[float]:
        return [0.0] * EMBEDDING_DIM

    async def _call_api(self, texts: list[str]) -> list[list[float]]:
        """Send a single batch to the OpenAI embeddings endpoint."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": MODEL_NAME,
            "input": texts,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                OPENAI_EMBEDDING_URL,
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        # OpenAI returns embeddings sorted by index
        embeddings_data: list[dict[str, Any]] = data["data"]
        embeddings_data.sort(key=lambda x: x["index"])
        return [item["embedding"] for item in embeddings_data]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, handling batching automatically.

        Parameters
        ----------
        texts:
            Strings to embed.  Empty strings are replaced with a
            placeholder to avoid API errors.

        Returns
        -------
        list[list[float]]
            One embedding vector per input text.
        """
        if not texts:
            return []

        if not self._available:
            logger.warning(
                "OPENAI_API_KEY not configured; returning zero vectors for %d texts.",
                len(texts),
            )
            return [self._zero_vector() for _ in texts]

        # Sanitise: OpenAI rejects empty strings
        sanitised = [t if t.strip() else " " for t in texts]

        all_embeddings: list[list[float]] = []
        for offset in range(0, len(sanitised), MAX_BATCH_SIZE):
            batch = sanitised[offset : offset + MAX_BATCH_SIZE]
            try:
                batch_embeddings = await self._call_api(batch)
                all_embeddings.extend(batch_embeddings)
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "OpenAI embedding API error (status %d): %s",
                    exc.response.status_code,
                    exc.response.text[:500],
                )
                # Fill with zeros so callers always get the expected count
                all_embeddings.extend(self._zero_vector() for _ in batch)
            except httpx.RequestError as exc:
                logger.error("OpenAI embedding request failed: %s", exc)
                all_embeddings.extend(self._zero_vector() for _ in batch)

        return all_embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text string."""
        results = await self.embed_texts([text])
        return results[0]
