"""GitHub REST API client with OAuth support."""

from __future__ import annotations

import logging
from base64 import b64decode
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_OAUTH_TOKEN = "https://github.com/login/oauth/access_token"


class GitHubClient:
    """Async GitHub REST API client.

    Parameters
    ----------
    access_token:
        Personal access token or OAuth token.  If *None*, unauthenticated
        requests are made (subject to stricter rate limits).
    """

    def __init__(self, access_token: str | None = None) -> None:
        self._access_token = access_token
        self._headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if access_token:
            self._headers["Authorization"] = f"Bearer {access_token}"

    # ── helpers ───────────────────────────────────────────────────────

    def _client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=GITHUB_API_BASE,
            headers=self._headers,
            timeout=timeout,
        )

    # ── repository info ──────────────────────────────────────────────

    async def get_repo_info(self, owner: str, repo: str) -> dict[str, Any]:
        """Return repository metadata via ``GET /repos/{owner}/{repo}``."""
        async with self._client() as client:
            resp = await client.get(f"/repos/{owner}/{repo}")
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            logger.info("Fetched repo info for %s/%s", owner, repo)
            return data

    # ── file operations ──────────────────────────────────────────────

    async def list_files(
        self,
        owner: str,
        repo: str,
        path: str = "",
        branch: str = "main",
    ) -> list[dict[str, Any]]:
        """List directory contents at *path* on *branch*."""
        async with self._client() as client:
            resp = await client.get(
                f"/repos/{owner}/{repo}/contents/{path}",
                params={"ref": branch},
            )
            resp.raise_for_status()
            result: list[dict[str, Any]] = resp.json()
            return result

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        branch: str = "main",
    ) -> str:
        """Return the decoded text content of a single file."""
        async with self._client() as client:
            resp = await client.get(
                f"/repos/{owner}/{repo}/contents/{path}",
                params={"ref": branch},
            )
            resp.raise_for_status()
            payload = resp.json()
            content_b64: str = payload.get("content", "")
            return b64decode(content_b64).decode("utf-8")

    # ── branch operations ────────────────────────────────────────────

    async def create_branch(
        self,
        owner: str,
        repo: str,
        branch_name: str,
        from_branch: str = "main",
    ) -> dict[str, Any]:
        """Create a new branch from *from_branch*.

        Steps:
        1. Resolve the SHA of *from_branch*.
        2. Create a new ref ``refs/heads/{branch_name}`` pointing at that SHA.
        """
        async with self._client() as client:
            # Resolve source branch SHA
            ref_resp = await client.get(
                f"/repos/{owner}/{repo}/git/ref/heads/{from_branch}",
            )
            ref_resp.raise_for_status()
            sha: str = ref_resp.json()["object"]["sha"]

            # Create new ref
            create_resp = await client.post(
                f"/repos/{owner}/{repo}/git/refs",
                json={"ref": f"refs/heads/{branch_name}", "sha": sha},
            )
            create_resp.raise_for_status()
            result: dict[str, Any] = create_resp.json()
            logger.info(
                "Created branch %s on %s/%s from %s (%s)",
                branch_name,
                owner,
                repo,
                from_branch,
                sha[:8],
            )
            return result

    # ── diff ──────────────────────────────────────────────────────────

    async def get_branch_diff(
        self,
        branch: str,
        base: str = "main",
        owner: str | None = None,
        repo: str | None = None,
    ) -> str | None:
        """Return the raw unified diff between *base* and *branch*.

        Uses the GitHub compare API with the ``.diff`` media type.
        Falls back to ``settings.GITHUB_OWNER`` / ``settings.GITHUB_REPO``
        when *owner* or *repo* are not provided.  Returns ``None`` when the
        required configuration is missing or the API call fails.
        """
        owner = owner or settings.GITHUB_OWNER
        repo = repo or settings.GITHUB_REPO
        if not owner or not repo:
            logger.debug("get_branch_diff skipped: GITHUB_OWNER/GITHUB_REPO not set")
            return None

        async with self._client() as client:
            resp = await client.get(
                f"/repos/{owner}/{repo}/compare/{base}...{branch}",
                headers={"Accept": "application/vnd.github.diff"},
            )
            if resp.status_code != 200:
                logger.warning(
                    "GitHub compare API returned %d for %s...%s",
                    resp.status_code,
                    base,
                    branch,
                )
                return None
            return resp.text

    # ── pull requests ────────────────────────────────────────────────

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
    ) -> dict[str, Any]:
        """Open a new pull request."""
        async with self._client() as client:
            resp = await client.post(
                f"/repos/{owner}/{repo}/pulls",
                json={
                    "title": title,
                    "body": body,
                    "head": head,
                    "base": base,
                },
            )
            resp.raise_for_status()
            pr: dict[str, Any] = resp.json()
            logger.info(
                "Created PR #%d on %s/%s: %s",
                pr["number"],
                owner,
                repo,
                title,
            )
            return pr

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> dict[str, Any]:
        """Fetch a single pull request by number."""
        async with self._client() as client:
            resp = await client.get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}",
            )
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result

    # ── webhooks ─────────────────────────────────────────────────────

    async def create_webhook(
        self,
        owner: str,
        repo: str,
        url: str,
        events: list[str] | None = None,
    ) -> dict[str, Any]:
        """Register a webhook on the repository."""
        if events is None:
            events = ["push", "pull_request"]

        async with self._client() as client:
            resp = await client.post(
                f"/repos/{owner}/{repo}/hooks",
                json={
                    "name": "web",
                    "active": True,
                    "events": events,
                    "config": {
                        "url": url,
                        "content_type": "json",
                        "insecure_ssl": "0",
                    },
                },
            )
            resp.raise_for_status()
            hook: dict[str, Any] = resp.json()
            logger.info(
                "Created webhook %d on %s/%s -> %s",
                hook["id"],
                owner,
                repo,
                url,
            )
            return hook

    # ── OAuth helpers ────────────────────────────────────────────────

    @staticmethod
    def get_oauth_url(state: str | None = None) -> str:
        """Build the GitHub OAuth authorization URL.

        Requires ``GITHUB_CLIENT_ID`` to be configured.
        """
        if not settings.GITHUB_CLIENT_ID:
            raise ValueError("GITHUB_CLIENT_ID is not configured.")

        params: dict[str, str] = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "scope": "repo read:user",
        }
        if state:
            params["state"] = state

        return f"{GITHUB_OAUTH_AUTHORIZE}?{urlencode(params)}"

    @staticmethod
    async def exchange_code(code: str) -> str:
        """Exchange an OAuth authorization code for an access token.

        Returns the raw access token string.
        """
        if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
            raise ValueError("GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET must be configured.")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                GITHUB_OAUTH_TOKEN,
                json={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        token: str | None = data.get("access_token")
        if not token:
            error_desc = data.get("error_description", "Unknown error")
            raise ValueError(f"GitHub OAuth token exchange failed: {error_desc}")

        logger.info("Successfully exchanged OAuth code for access token.")
        return token
