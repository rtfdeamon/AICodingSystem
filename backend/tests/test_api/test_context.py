"""Tests for app.api.v1.context — index, status, search, and dependencies."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_project(client: AsyncClient, headers: dict) -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Context Test Proj"},
        headers=headers,
    )
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Index status — no embeddings yet
# ---------------------------------------------------------------------------


async def test_context_index_status_not_indexed(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    project_id = await _create_project(async_client, auth_headers)
    resp = await async_client.get(
        f"/api/v1/projects/{project_id}/context/status",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["indexed"] is False


async def test_context_index_status_project_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.get(
        f"/api/v1/projects/{fake_id}/context/status",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Trigger index — requires cloned repo
# ---------------------------------------------------------------------------


async def test_context_trigger_index_no_repo(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Index trigger should fail when repo is not cloned."""
    project_id = await _create_project(async_client, auth_headers)
    resp = await async_client.post(
        f"/api/v1/projects/{project_id}/context/index",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "not been cloned" in resp.json()["detail"]


async def test_context_trigger_index_project_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/projects/{fake_id}/context/index",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------


async def test_context_search_empty_results(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Search should return empty results when nothing is indexed."""
    from unittest.mock import AsyncMock, patch

    project_id = await _create_project(async_client, auth_headers)

    # Mock the ContextEngine.search since SQLite doesn't support vector ops
    with patch("app.api.v1.context.ContextEngine") as mock_engine:
        mock_instance = AsyncMock()
        mock_instance.search.return_value = []
        mock_engine.return_value = mock_instance

        resp = await async_client.post(
            f"/api/v1/projects/{project_id}/context/search",
            json={"query": "authentication handler", "top_k": 5},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert body["total"] == 0
    assert body["query"] == "authentication handler"


async def test_context_search_project_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.post(
        f"/api/v1/projects/{fake_id}/context/search",
        json={"query": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# File dependencies (placeholder)
# ---------------------------------------------------------------------------


async def test_context_file_dependencies(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await async_client.get(
        "/api/v1/context/deps/app/main.py",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["file_path"] == "app/main.py"
    assert body["dependencies"] == []
    assert "not yet implemented" in body["message"]


async def test_context_requires_auth(
    async_client: AsyncClient,
) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.get(f"/api/v1/projects/{fake_id}/context/status")
    assert resp.status_code == 401
