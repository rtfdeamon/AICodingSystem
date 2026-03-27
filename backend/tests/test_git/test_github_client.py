"""Tests for app.git.github_client — GitHub REST API client."""

from __future__ import annotations

from base64 import b64encode
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.git.github_client import GITHUB_OAUTH_AUTHORIZE, GitHubClient

# Test-only token value — not a real credential
_TEST_TOKEN = "ghp_test123"  # noqa: S105
_TOK = "tok"  # noqa: S105

# ── Constructor ──────────────────────────────────────────────────────


class TestGitHubClientInit:
    def test_unauthenticated_client(self) -> None:
        client = GitHubClient()
        assert "Authorization" not in client._headers
        assert "Accept" in client._headers
        assert client._access_token is None

    def test_authenticated_client(self) -> None:
        client = GitHubClient(access_token=_TEST_TOKEN)
        assert client._headers["Authorization"] == f"Bearer {_TEST_TOKEN}"
        assert client._access_token == _TEST_TOKEN

    def test_headers_include_api_version(self) -> None:
        client = GitHubClient()
        assert client._headers["X-GitHub-Api-Version"] == "2022-11-28"
        assert client._headers["Accept"] == "application/vnd.github+json"


# ── _client helper ───────────────────────────────────────────────────


class TestClientHelper:
    def test_returns_httpx_async_client(self) -> None:
        gh = GitHubClient(access_token=_TOK)
        c = gh._client(timeout=10.0)
        # Should be an httpx.AsyncClient context manager
        assert hasattr(c, "__aenter__")

    def test_custom_timeout(self) -> None:
        gh = GitHubClient()
        c = gh._client(timeout=5.0)
        assert hasattr(c, "__aenter__")


# ── get_repo_info ────────────────────────────────────────────────────


class TestGetRepoInfo:
    async def test_returns_repo_data(self) -> None:
        gh = GitHubClient(access_token=_TOK)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"name": "my-repo", "full_name": "owner/my-repo"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client):
            result = await gh.get_repo_info("owner", "my-repo")

        assert result["name"] == "my-repo"
        mock_client.get.assert_called_once_with("/repos/owner/my-repo")

    async def test_raises_on_http_error(self) -> None:
        import httpx

        gh = GitHubClient(access_token=_TOK)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=MagicMock()
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client), pytest.raises(
            httpx.HTTPStatusError,
        ):
            await gh.get_repo_info("owner", "missing")


# ── list_files ───────────────────────────────────────────────────────


class TestListFiles:
    async def test_lists_root_directory(self) -> None:
        gh = GitHubClient(access_token=_TOK)
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"name": "README.md", "type": "file"},
            {"name": "src", "type": "dir"},
        ]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client):
            result = await gh.list_files("owner", "repo")

        assert len(result) == 2
        mock_client.get.assert_called_once_with(
            "/repos/owner/repo/contents/",
            params={"ref": "main"},
        )

    async def test_lists_subdirectory_on_branch(self) -> None:
        gh = GitHubClient(access_token=_TOK)
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"name": "app.py"}]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client):
            await gh.list_files("owner", "repo", path="src", branch="dev")

        mock_client.get.assert_called_once_with(
            "/repos/owner/repo/contents/src",
            params={"ref": "dev"},
        )


# ── get_file_content ─────────────────────────────────────────────────


class TestGetFileContent:
    async def test_decodes_base64_content(self) -> None:
        gh = GitHubClient(access_token=_TOK)
        file_content = "print('hello world')"
        encoded = b64encode(file_content.encode("utf-8")).decode("ascii")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"content": encoded}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client):
            result = await gh.get_file_content("owner", "repo", "main.py")

        assert result == file_content

    async def test_empty_content(self) -> None:
        gh = GitHubClient(access_token=_TOK)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"content": ""}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client):
            result = await gh.get_file_content("owner", "repo", "empty.py")

        assert result == ""


# ── create_branch ────────────────────────────────────────────────────


class TestCreateBranch:
    async def test_creates_branch_from_main(self) -> None:
        gh = GitHubClient(access_token=_TOK)

        ref_resp = MagicMock()
        ref_resp.json.return_value = {"object": {"sha": "abc123def456"}}
        ref_resp.raise_for_status = MagicMock()

        create_resp = MagicMock()
        create_resp.json.return_value = {"ref": "refs/heads/feature/new-branch"}
        create_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=ref_resp)
        mock_client.post = AsyncMock(return_value=create_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client):
            result = await gh.create_branch("owner", "repo", "feature/new-branch")

        assert result["ref"] == "refs/heads/feature/new-branch"
        mock_client.post.assert_called_once_with(
            "/repos/owner/repo/git/refs",
            json={"ref": "refs/heads/feature/new-branch", "sha": "abc123def456"},
        )

    async def test_creates_branch_from_custom_base(self) -> None:
        gh = GitHubClient(access_token=_TOK)

        ref_resp = MagicMock()
        ref_resp.json.return_value = {"object": {"sha": "sha999"}}
        ref_resp.raise_for_status = MagicMock()

        create_resp = MagicMock()
        create_resp.json.return_value = {"ref": "refs/heads/hotfix"}
        create_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=ref_resp)
        mock_client.post = AsyncMock(return_value=create_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client):
            await gh.create_branch("owner", "repo", "hotfix", from_branch="develop")

        mock_client.get.assert_called_once_with(
            "/repos/owner/repo/git/ref/heads/develop",
        )


# ── create_pull_request ──────────────────────────────────────────────


class TestCreatePullRequest:
    async def test_creates_pr(self) -> None:
        gh = GitHubClient(access_token=_TOK)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "number": 42,
            "title": "Add feature X",
            "html_url": "https://github.com/owner/repo/pull/42",
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client):
            result = await gh.create_pull_request(
                "owner", "repo", "Add feature X", "Description here", "feature-branch"
            )

        assert result["number"] == 42
        mock_client.post.assert_called_once_with(
            "/repos/owner/repo/pulls",
            json={
                "title": "Add feature X",
                "body": "Description here",
                "head": "feature-branch",
                "base": "main",
            },
        )


# ── get_pull_request ─────────────────────────────────────────────────


class TestGetPullRequest:
    async def test_gets_pr(self) -> None:
        gh = GitHubClient(access_token=_TOK)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"number": 10, "state": "open"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client):
            result = await gh.get_pull_request("owner", "repo", 10)

        assert result["number"] == 10
        assert result["state"] == "open"


# ── create_webhook ───────────────────────────────────────────────────


class TestCreateWebhook:
    async def test_creates_webhook_default_events(self) -> None:
        gh = GitHubClient(access_token=_TOK)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 123, "active": True}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client):
            result = await gh.create_webhook("owner", "repo", "https://example.com/webhook")

        assert result["id"] == 123
        call_json = mock_client.post.call_args[1]["json"]
        assert call_json["events"] == ["push", "pull_request"]

    async def test_creates_webhook_custom_events(self) -> None:
        gh = GitHubClient(access_token=_TOK)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 456}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch.object(gh, "_client", return_value=mock_client):
            await gh.create_webhook(
                "owner", "repo", "https://example.com/hook", events=["issues"]
            )

        call_json = mock_client.post.call_args[1]["json"]
        assert call_json["events"] == ["issues"]


# ── OAuth helpers ────────────────────────────────────────────────────


class TestGetOAuthUrl:
    def test_builds_oauth_url(self) -> None:
        with patch("app.git.github_client.settings") as mock_settings:
            mock_settings.GITHUB_CLIENT_ID = "client_abc"
            url = GitHubClient.get_oauth_url()
        assert "client_id=client_abc" in url
        assert GITHUB_OAUTH_AUTHORIZE in url
        assert "scope=repo+read" in url or "scope=repo" in url

    def test_includes_state_parameter(self) -> None:
        with patch("app.git.github_client.settings") as mock_settings:
            mock_settings.GITHUB_CLIENT_ID = "client_abc"
            url = GitHubClient.get_oauth_url(state="random_state_123")
        assert "state=random_state_123" in url

    def test_raises_without_client_id(self) -> None:
        with patch("app.git.github_client.settings") as mock_settings, pytest.raises(
            ValueError, match="GITHUB_CLIENT_ID"
        ):
            mock_settings.GITHUB_CLIENT_ID = ""
            GitHubClient.get_oauth_url()


class TestExchangeCode:
    async def test_exchanges_code_for_token(self) -> None:
        with patch("app.git.github_client.settings") as mock_settings:
            mock_settings.GITHUB_CLIENT_ID = "cid"
            mock_settings.GITHUB_CLIENT_SECRET = "csecret"

            mock_resp = MagicMock()
            mock_resp.json.return_value = {"access_token": "gho_abc123"}
            mock_resp.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client):
                token = await GitHubClient.exchange_code("auth_code_xyz")

        assert token == "gho_abc123"

    async def test_raises_on_missing_token(self) -> None:
        with patch("app.git.github_client.settings") as mock_settings:
            mock_settings.GITHUB_CLIENT_ID = "cid"
            mock_settings.GITHUB_CLIENT_SECRET = "csecret"

            mock_resp = MagicMock()
            mock_resp.json.return_value = {"error": "bad_code", "error_description": "Code expired"}
            mock_resp.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client), pytest.raises(
                ValueError, match="Code expired"
            ):
                await GitHubClient.exchange_code("bad_code")

    async def test_raises_without_credentials(self) -> None:
        with patch("app.git.github_client.settings") as mock_settings, pytest.raises(
            ValueError, match="GITHUB_CLIENT_ID"
        ):
            mock_settings.GITHUB_CLIENT_ID = ""
            mock_settings.GITHUB_CLIENT_SECRET = ""
            await GitHubClient.exchange_code("code")

    async def test_raises_unknown_error_description(self) -> None:
        with patch("app.git.github_client.settings") as mock_settings:
            mock_settings.GITHUB_CLIENT_ID = "cid"
            mock_settings.GITHUB_CLIENT_SECRET = "csecret"

            mock_resp = MagicMock()
            mock_resp.json.return_value = {"error": "unknown"}
            mock_resp.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client), pytest.raises(
                ValueError, match="Unknown error"
            ):
                await GitHubClient.exchange_code("code")
