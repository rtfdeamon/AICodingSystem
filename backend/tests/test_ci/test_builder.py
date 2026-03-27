"""Tests for the CI builder module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.ci.builder import (
    BuildResult,
    _github_headers,
    trigger_build,
)

# ── BuildResult dataclass ─────────────────────────────────────────────


def test_build_result() -> None:
    r = BuildResult(status="success", log_url="https://example.com", duration_ms=5000, artifacts=[])
    assert r.status == "success"
    assert r.artifacts == []


def test_build_result_with_artifacts() -> None:
    r = BuildResult(
        status="success",
        log_url="https://example.com",
        duration_ms=5000,
        artifacts=[
            {"name": "build.zip", "url": "https://example.com/build.zip", "size_bytes": 1024}
        ],
    )
    assert len(r.artifacts) == 1
    assert r.artifacts[0]["name"] == "build.zip"


def test_build_result_all_fields() -> None:
    r = BuildResult(
        status="cancelled",
        log_url="https://example.com/run/1",
        duration_ms=12345,
        artifacts=[{"name": "a"}, {"name": "b"}],
    )
    assert r.status == "cancelled"
    assert r.log_url == "https://example.com/run/1"
    assert r.duration_ms == 12345
    assert len(r.artifacts) == 2


# ── _github_headers ───────────────────────────────────────────────────


def test_github_headers_with_token() -> None:
    with patch("app.ci.builder.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = "test-token"
        headers = _github_headers()
        assert headers["Authorization"] == "Bearer test-token"
        assert "X-GitHub-Api-Version" in headers


def test_github_headers_without_token() -> None:
    with patch("app.ci.builder.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = ""
        headers = _github_headers()
        assert "Authorization" not in headers


def test_github_headers_none_token() -> None:
    with patch("app.ci.builder.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_SECRET = None
        headers = _github_headers()
        assert "Authorization" not in headers
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"


# ── trigger_build ─────────────────────────────────────────────────────


def _make_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
) -> MagicMock:
    """Helper to build a mock httpx response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data or {}
    return resp


@patch("app.ci.builder.settings")
@patch("app.ci.builder.asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_trigger_build_dispatch_failure(
    mock_sleep: AsyncMock, mock_settings: MagicMock
) -> None:
    """When dispatch returns non-200/204, return failure immediately."""
    mock_settings.GITHUB_CLIENT_SECRET = "tok"

    dispatch_resp = _make_response(status_code=403, text="Forbidden")

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        client.post.return_value = dispatch_resp

        result = await trigger_build("org/repo", "main", "abc1234")

    assert result.status == "failure"
    assert result.duration_ms >= 0
    assert result.artifacts == []
    assert "org/repo" in result.log_url


@patch("app.ci.builder.settings")
@patch("app.ci.builder.asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_trigger_build_run_not_found(mock_sleep: AsyncMock, mock_settings: MagicMock) -> None:
    """When dispatch succeeds (204) but we cannot find the run, return failure."""
    mock_settings.GITHUB_CLIENT_SECRET = "tok"

    dispatch_resp = _make_response(status_code=204)
    # Return empty runs every time so run_id is never set
    runs_resp = _make_response(status_code=200, json_data={"workflow_runs": []})

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        client.post.return_value = dispatch_resp
        client.get.return_value = runs_resp

        result = await trigger_build("org/repo", "main", "abc1234")

    assert result.status == "failure"
    assert result.artifacts == []


@patch("app.ci.builder.settings")
@patch("app.ci.builder.asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_trigger_build_run_not_found_non_200_runs(
    mock_sleep: AsyncMock, mock_settings: MagicMock
) -> None:
    """When listing runs returns non-200 every time, run_id stays None."""
    mock_settings.GITHUB_CLIENT_SECRET = "tok"

    dispatch_resp = _make_response(status_code=204)
    runs_resp = _make_response(status_code=500)

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        client.post.return_value = dispatch_resp
        client.get.return_value = runs_resp

        result = await trigger_build("org/repo", "main", "abc1234")

    assert result.status == "failure"


@patch("app.ci.builder.settings")
@patch("app.ci.builder.asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_trigger_build_success(mock_sleep: AsyncMock, mock_settings: MagicMock) -> None:
    """Happy path: dispatch 204, run found, completed with success, artifacts fetched."""
    mock_settings.GITHUB_CLIENT_SECRET = "tok"

    dispatch_resp = _make_response(status_code=204)
    runs_resp = _make_response(
        status_code=200,
        json_data={
            "workflow_runs": [
                {
                    "id": 42,
                    "head_sha": "abc1234def",
                    "html_url": "https://github.com/org/repo/actions/runs/42",
                }
            ]
        },
    )
    poll_resp = _make_response(
        status_code=200,
        json_data={
            "status": "completed",
            "conclusion": "success",
            "html_url": "https://github.com/org/repo/actions/runs/42",
        },
    )
    artifacts_resp = _make_response(
        status_code=200,
        json_data={
            "artifacts": [
                {
                    "name": "coverage",
                    "archive_download_url": "https://api.github.com/dl/1",
                    "size_in_bytes": 2048,
                }
            ]
        },
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        client.post.return_value = dispatch_resp
        # First get = runs listing, second = poll, third = artifacts
        client.get.side_effect = [runs_resp, poll_resp, artifacts_resp]

        result = await trigger_build("org/repo", "main", "abc1234")

    assert result.status == "success"
    assert result.log_url == "https://github.com/org/repo/actions/runs/42"
    assert len(result.artifacts) == 1
    assert result.artifacts[0]["name"] == "coverage"
    assert result.artifacts[0]["size_bytes"] == 2048
    assert result.duration_ms >= 0


@patch("app.ci.builder.settings")
@patch("app.ci.builder.asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_trigger_build_conclusion_failure(
    mock_sleep: AsyncMock, mock_settings: MagicMock
) -> None:
    """Run completes with conclusion != success and != cancelled => failure."""
    mock_settings.GITHUB_CLIENT_SECRET = "tok"

    dispatch_resp = _make_response(status_code=200)
    runs_resp = _make_response(
        status_code=200,
        json_data={
            "workflow_runs": [
                {"id": 99, "head_sha": "abc1234fff", "html_url": "https://github.com/org/repo/actions/runs/99"}
            ]
        },
    )
    poll_resp = _make_response(
        status_code=200,
        json_data={"status": "completed", "conclusion": "failure", "html_url": "https://github.com/org/repo/actions/runs/99"},
    )
    artifacts_resp = _make_response(status_code=200, json_data={"artifacts": []})

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        client.post.return_value = dispatch_resp
        client.get.side_effect = [runs_resp, poll_resp, artifacts_resp]

        result = await trigger_build("org/repo", "main", "abc1234")

    assert result.status == "failure"
    assert result.artifacts == []


@patch("app.ci.builder.settings")
@patch("app.ci.builder.asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_trigger_build_conclusion_cancelled(
    mock_sleep: AsyncMock, mock_settings: MagicMock
) -> None:
    """Run completes with conclusion == cancelled."""
    mock_settings.GITHUB_CLIENT_SECRET = "tok"

    dispatch_resp = _make_response(status_code=204)
    runs_resp = _make_response(
        status_code=200,
        json_data={
            "workflow_runs": [
                {"id": 7, "head_sha": "abc1234aaa", "html_url": "https://github.com/org/repo/actions/runs/7"}
            ]
        },
    )
    poll_resp = _make_response(
        status_code=200,
        json_data={"status": "completed", "conclusion": "cancelled", "html_url": "https://github.com/org/repo/actions/runs/7"},
    )
    artifacts_resp = _make_response(status_code=200, json_data={"artifacts": []})

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        client.post.return_value = dispatch_resp
        client.get.side_effect = [runs_resp, poll_resp, artifacts_resp]

        result = await trigger_build("org/repo", "main", "abc1234")

    assert result.status == "cancelled"


@patch("app.ci.builder.MAX_POLL_DURATION_S", 0)
@patch("app.ci.builder.settings")
@patch("app.ci.builder.asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_trigger_build_timed_out(mock_sleep: AsyncMock, mock_settings: MagicMock) -> None:
    """When polling exceeds MAX_POLL_DURATION_S the status is timed_out."""
    mock_settings.GITHUB_CLIENT_SECRET = "tok"

    dispatch_resp = _make_response(status_code=204)
    runs_resp = _make_response(
        status_code=200,
        json_data={
            "workflow_runs": [
                {"id": 10, "head_sha": "abc1234bbb", "html_url": "https://github.com/org/repo/actions/runs/10"}
            ]
        },
    )
    # The poll loop condition will be false immediately because MAX_POLL_DURATION_S=0
    artifacts_resp = _make_response(status_code=200, json_data={"artifacts": []})

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        client.post.return_value = dispatch_resp
        client.get.side_effect = [runs_resp, artifacts_resp]

        result = await trigger_build("org/repo", "main", "abc1234")

    assert result.status == "timed_out"


@patch("app.ci.builder.settings")
@patch("app.ci.builder.asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_trigger_build_poll_non_200_then_success(
    mock_sleep: AsyncMock, mock_settings: MagicMock
) -> None:
    """When a poll returns non-200, we continue polling and eventually succeed."""
    mock_settings.GITHUB_CLIENT_SECRET = "tok"

    dispatch_resp = _make_response(status_code=204)
    runs_resp = _make_response(
        status_code=200,
        json_data={
            "workflow_runs": [
                {"id": 55, "head_sha": "abc1234ccc", "html_url": "https://github.com/org/repo/actions/runs/55"}
            ]
        },
    )
    poll_error_resp = _make_response(status_code=502)
    poll_in_progress_resp = _make_response(
        status_code=200,
        json_data={"status": "in_progress", "conclusion": None, "html_url": "https://github.com/org/repo/actions/runs/55"},
    )
    poll_done_resp = _make_response(
        status_code=200,
        json_data={"status": "completed", "conclusion": "success", "html_url": "https://github.com/org/repo/actions/runs/55"},
    )
    artifacts_resp = _make_response(status_code=404)

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        client.post.return_value = dispatch_resp
        # runs listing, poll-error, poll-in-progress, poll-done, artifacts
        client.get.side_effect = [
            runs_resp, poll_error_resp, poll_in_progress_resp,
            poll_done_resp, artifacts_resp,
        ]

        result = await trigger_build("org/repo", "main", "abc1234")

    assert result.status == "success"
    # Artifacts fetch returned 404, so no artifacts
    assert result.artifacts == []


@patch("app.ci.builder.settings")
@patch("app.ci.builder.asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_trigger_build_artifacts_with_missing_fields(
    mock_sleep: AsyncMock, mock_settings: MagicMock
) -> None:
    """Artifacts with missing optional fields default gracefully."""
    mock_settings.GITHUB_CLIENT_SECRET = "tok"

    dispatch_resp = _make_response(status_code=204)
    runs_resp = _make_response(
        status_code=200,
        json_data={
            "workflow_runs": [
                {"id": 77, "head_sha": "abc1234ddd", "html_url": "https://github.com/org/repo/actions/runs/77"}
            ]
        },
    )
    poll_resp = _make_response(
        status_code=200,
        json_data={"status": "completed", "conclusion": "success", "html_url": "https://github.com/org/repo/actions/runs/77"},
    )
    # Artifacts with some fields missing
    artifacts_resp = _make_response(
        status_code=200,
        json_data={
            "artifacts": [
                {},  # all fields missing
                {"name": "report", "size_in_bytes": 512},  # missing archive_download_url
            ]
        },
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        client.post.return_value = dispatch_resp
        client.get.side_effect = [runs_resp, poll_resp, artifacts_resp]

        result = await trigger_build("org/repo", "main", "abc1234")

    assert result.status == "success"
    assert len(result.artifacts) == 2
    assert result.artifacts[0]["name"] == ""
    assert result.artifacts[0]["url"] == ""
    assert result.artifacts[0]["size_bytes"] == 0
    assert result.artifacts[1]["name"] == "report"
    assert result.artifacts[1]["url"] == ""
    assert result.artifacts[1]["size_bytes"] == 512


@patch("app.ci.builder.settings")
@patch("app.ci.builder.asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_trigger_build_dispatch_200_accepted(
    mock_sleep: AsyncMock, mock_settings: MagicMock
) -> None:
    """Dispatch returning 200 (not only 204) is also accepted."""
    mock_settings.GITHUB_CLIENT_SECRET = "tok"

    dispatch_resp = _make_response(status_code=200)
    runs_resp = _make_response(
        status_code=200,
        json_data={
            "workflow_runs": [
                {"id": 1, "head_sha": "abc1234eee", "html_url": "https://github.com/org/repo/actions/runs/1"}
            ]
        },
    )
    poll_resp = _make_response(
        status_code=200,
        json_data={"status": "completed", "conclusion": "success", "html_url": "https://github.com/org/repo/actions/runs/1"},
    )
    artifacts_resp = _make_response(status_code=200, json_data={"artifacts": []})

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        client.post.return_value = dispatch_resp
        client.get.side_effect = [runs_resp, poll_resp, artifacts_resp]

        result = await trigger_build("org/repo", "main", "abc1234")

    assert result.status == "success"


@patch("app.ci.builder.settings")
@patch("app.ci.builder.asyncio.sleep", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_trigger_build_sha_prefix_matching(
    mock_sleep: AsyncMock, mock_settings: MagicMock
) -> None:
    """Run matching uses first 7 chars of commit_sha; non-matching runs are skipped."""
    mock_settings.GITHUB_CLIENT_SECRET = "tok"

    dispatch_resp = _make_response(status_code=204)
    runs_resp = _make_response(
        status_code=200,
        json_data={
            "workflow_runs": [
                # This one does NOT match
                {"id": 100, "head_sha": "zzzzzzz999", "html_url": "https://github.com/org/repo/actions/runs/100"},
                # This one matches
                {"id": 200, "head_sha": "abc1234xyz", "html_url": "https://github.com/org/repo/actions/runs/200"},
            ]
        },
    )
    poll_resp = _make_response(
        status_code=200,
        json_data={"status": "completed", "conclusion": "success", "html_url": "https://github.com/org/repo/actions/runs/200"},
    )
    artifacts_resp = _make_response(status_code=200, json_data={"artifacts": []})

    with patch("httpx.AsyncClient") as mock_client_cls:
        client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        client.post.return_value = dispatch_resp
        client.get.side_effect = [runs_resp, poll_resp, artifacts_resp]

        result = await trigger_build("org/repo", "main", "abc1234full")

    assert result.status == "success"
    assert "200" in result.log_url
