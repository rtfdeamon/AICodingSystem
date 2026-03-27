"""Tests for n8n_service — external workflow trigger integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.n8n_service import WORKFLOW_ENDPOINTS, trigger_workflow


def _mock_httpx_client(response_status=200, response_json=None, raise_error=None):
    """Create a mock httpx.AsyncClient that works as async context manager."""
    mock_response = MagicMock()
    mock_response.status_code = response_status
    mock_response.json.return_value = response_json or {}
    mock_response.text = "Error"
    mock_response.raise_for_status = MagicMock()

    if raise_error:
        mock_response.raise_for_status.side_effect = raise_error

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    return mock_client, mock_response


# ---------------------------------------------------------------------------
# Unknown workflow name
# ---------------------------------------------------------------------------


async def test_trigger_workflow_unknown_name():
    """Raises ValueError for an unknown workflow name."""
    with pytest.raises(ValueError, match="Unknown workflow"):
        await trigger_workflow("nonexistent_workflow", {"key": "value"})


# ---------------------------------------------------------------------------
# N8N_BASE_URL not configured
# ---------------------------------------------------------------------------


async def test_trigger_workflow_no_base_url():
    """Returns skipped status when N8N_BASE_URL is empty."""
    with patch("app.services.n8n_service.settings") as mock_settings:
        mock_settings.N8N_BASE_URL = ""
        result = await trigger_workflow("ai_planning", {"ticket_id": "123"})

    assert result["status"] == "skipped"
    assert "not configured" in result["reason"]


# ---------------------------------------------------------------------------
# Successful workflow trigger
# ---------------------------------------------------------------------------


async def test_trigger_workflow_success():
    """Successfully triggers an n8n workflow and returns JSON response."""
    mock_client, _ = _mock_httpx_client(
        response_status=200,
        response_json={"status": "ok", "execution_id": "abc"},
    )

    with (
        patch("app.services.n8n_service.settings") as mock_settings,
        patch("app.services.n8n_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.N8N_BASE_URL = "http://n8n:5678"
        result = await trigger_workflow("build_test", {"branch": "main"})

    assert result["status"] == "ok"
    assert result["execution_id"] == "abc"


# ---------------------------------------------------------------------------
# HTTP error from n8n
# ---------------------------------------------------------------------------


async def test_trigger_workflow_http_error():
    """Returns error dict on HTTP error response from n8n."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    error = httpx.HTTPStatusError(
        "Server Error",
        request=httpx.Request("POST", "http://n8n:5678/webhook/build-test"),
        response=mock_resp,
    )

    mock_client, _ = _mock_httpx_client(raise_error=error)

    with (
        patch("app.services.n8n_service.settings") as mock_settings,
        patch("app.services.n8n_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.N8N_BASE_URL = "http://n8n:5678"
        result = await trigger_workflow("build_test", {"branch": "main"})

    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Request error (network failure)
# ---------------------------------------------------------------------------


async def test_trigger_workflow_request_error():
    """Returns error dict on network failure."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.RequestError("Connection refused")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.n8n_service.settings") as mock_settings,
        patch("app.services.n8n_service.httpx.AsyncClient", return_value=mock_client),
    ):
        mock_settings.N8N_BASE_URL = "http://n8n:5678"
        result = await trigger_workflow("ai_coding", {"ticket_id": "456"})

    assert result["status"] == "error"
    assert "Connection refused" in result["detail"]


# ---------------------------------------------------------------------------
# WORKFLOW_ENDPOINTS registry
# ---------------------------------------------------------------------------


def test_workflow_endpoints_all_have_webhook_prefix():
    """All workflow endpoint paths start with /webhook/."""
    for name, path in WORKFLOW_ENDPOINTS.items():
        assert path.startswith("/webhook/"), f"{name} path should start with /webhook/"


def test_workflow_endpoints_contains_core_workflows():
    """Registry has entries for all core pipeline workflows."""
    expected = {"ai_planning", "ai_coding", "build_test", "deploy_canary", "notify"}
    assert expected.issubset(set(WORKFLOW_ENDPOINTS.keys()))
