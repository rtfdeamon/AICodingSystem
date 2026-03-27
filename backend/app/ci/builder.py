"""Build trigger — triggers GitHub Actions workflows and polls for completion."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
POLL_INTERVAL_S = 10
MAX_POLL_DURATION_S = 1800  # 30 minutes


@dataclass
class BuildResult:
    """Result from a CI build run."""

    status: str  # success | failure | cancelled | timed_out
    log_url: str
    duration_ms: int
    artifacts: list[dict[str, Any]]  # [{name, url, size_bytes}]


def _github_headers() -> dict[str, str]:
    """Build authorization headers for GitHub API calls."""
    token = settings.GITHUB_CLIENT_SECRET
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def trigger_build(
    project: str,
    branch: str,
    commit_sha: str,
) -> BuildResult:
    """Trigger a GitHub Actions workflow and poll until completion.

    Parameters
    ----------
    project:
        GitHub repo in "owner/repo" format.
    branch:
        Branch to build.
    commit_sha:
        Commit SHA to build.

    Returns
    -------
    BuildResult with status, log URL, duration, and artifacts.
    """
    workflow_file = "ci-backend.yml"
    dispatch_url = f"{GITHUB_API_BASE}/repos/{project}/actions/workflows/{workflow_file}/dispatches"

    headers = _github_headers()
    start_time = time.perf_counter()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Trigger the workflow
        dispatch_resp = await client.post(
            dispatch_url,
            headers=headers,
            json={"ref": branch, "inputs": {"commit_sha": commit_sha}},
        )

        if dispatch_resp.status_code not in (204, 200):
            logger.error(
                "Failed to trigger workflow: HTTP %d — %s",
                dispatch_resp.status_code,
                dispatch_resp.text[:500],
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return BuildResult(
                status="failure",
                log_url=f"https://github.com/{project}/actions",
                duration_ms=elapsed_ms,
                artifacts=[],
            )

        logger.info("Triggered workflow '%s' on %s@%s", workflow_file, project, branch)

        # Brief delay before polling for the new run
        await asyncio.sleep(3)

        # Find the workflow run triggered by our dispatch
        runs_url = f"{GITHUB_API_BASE}/repos/{project}/actions/runs"
        run_id: int | None = None
        run_html_url = f"https://github.com/{project}/actions"

        for _ in range(5):
            runs_resp = await client.get(
                runs_url,
                headers=headers,
                params={"branch": branch, "per_page": 5, "event": "workflow_dispatch"},
            )
            if runs_resp.status_code == 200:
                runs_data = runs_resp.json()
                for run in runs_data.get("workflow_runs", []):
                    if run.get("head_sha", "").startswith(commit_sha[:7]):
                        run_id = run["id"]
                        run_html_url = run.get("html_url", run_html_url)
                        break
                if run_id:
                    break
            await asyncio.sleep(2)

        if not run_id:
            logger.warning("Could not find workflow run after dispatch; returning pending status")
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return BuildResult(
                status="failure",
                log_url=run_html_url,
                duration_ms=elapsed_ms,
                artifacts=[],
            )

        # Poll for completion
        run_url = f"{GITHUB_API_BASE}/repos/{project}/actions/runs/{run_id}"
        final_status = "timed_out"

        while (time.perf_counter() - start_time) < MAX_POLL_DURATION_S:
            run_resp = await client.get(run_url, headers=headers)
            if run_resp.status_code != 200:
                logger.warning("Failed to poll run status: HTTP %d", run_resp.status_code)
                await asyncio.sleep(POLL_INTERVAL_S)
                continue

            run_data = run_resp.json()
            run_html_url = run_data.get("html_url", run_html_url)
            run_status = run_data.get("status")
            conclusion = run_data.get("conclusion")

            if run_status == "completed":
                if conclusion == "success":
                    final_status = "success"
                elif conclusion == "cancelled":
                    final_status = "cancelled"
                else:
                    final_status = "failure"
                break

            await asyncio.sleep(POLL_INTERVAL_S)

        # Fetch artifacts
        artifacts: list[dict[str, Any]] = []
        artifacts_url = f"{GITHUB_API_BASE}/repos/{project}/actions/runs/{run_id}/artifacts"
        art_resp = await client.get(artifacts_url, headers=headers)
        if art_resp.status_code == 200:
            for art in art_resp.json().get("artifacts", []):
                artifacts.append(
                    {
                        "name": art.get("name", ""),
                        "url": art.get("archive_download_url", ""),
                        "size_bytes": art.get("size_in_bytes", 0),
                    }
                )

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    logger.info(
        "Build %s completed: status=%s duration=%dms artifacts=%d",
        run_id,
        final_status,
        elapsed_ms,
        len(artifacts),
    )

    return BuildResult(
        status=final_status,
        log_url=run_html_url,
        duration_ms=elapsed_ms,
        artifacts=artifacts,
    )
