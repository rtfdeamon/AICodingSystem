"""Tests for app.api.v1.github_oauth — URL generation and callback exchange."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# GET /auth/github/url
# ---------------------------------------------------------------------------


async def test_github_url_returns_auth_url(
    async_client: AsyncClient,
) -> None:
    """Should return GitHub OAuth URL when client ID is configured."""
    with patch("app.api.v1.github_oauth.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_ID = "test-client-id"
        resp = await async_client.get("/api/v1/auth/github/url")

    assert resp.status_code == 200
    body = resp.json()
    assert "url" in body
    assert "test-client-id" in body["url"]
    assert "oauth/authorize" in body["url"]


async def test_github_url_not_configured(
    async_client: AsyncClient,
) -> None:
    """Should return 501 when GitHub client ID is not set."""
    with patch("app.api.v1.github_oauth.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_ID = ""
        resp = await async_client.get("/api/v1/auth/github/url")

    assert resp.status_code == 501


# ---------------------------------------------------------------------------
# POST /auth/github/callback
# ---------------------------------------------------------------------------


async def test_github_callback_not_configured(
    async_client: AsyncClient,
) -> None:
    """Should return 501 when GitHub OAuth is not configured."""
    with patch("app.api.v1.github_oauth.settings") as mock_settings:
        mock_settings.GITHUB_CLIENT_ID = ""
        mock_settings.GITHUB_CLIENT_SECRET = ""
        resp = await async_client.post(
            "/api/v1/auth/github/callback",
            json={"code": "test-code"},
        )

    assert resp.status_code == 501


async def test_github_callback_token_exchange_failure(
    async_client: AsyncClient,
) -> None:
    """Should return 400 when GitHub token exchange fails."""

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 500

    mock_client_instance = AsyncMock()
    mock_client_instance.post.return_value = mock_token_resp
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.api.v1.github_oauth.settings") as mock_settings,
        patch("app.api.v1.github_oauth.httpx.AsyncClient", return_value=mock_client_instance),
    ):
        mock_settings.GITHUB_CLIENT_ID = "test-id"
        mock_settings.GITHUB_CLIENT_SECRET = "test-secret"
        resp = await async_client.post(
            "/api/v1/auth/github/callback",
            json={"code": "bad-code"},
        )

    assert resp.status_code == 400


async def test_github_callback_no_access_token(
    async_client: AsyncClient,
) -> None:
    """Should return 400 when GitHub returns no access token."""

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {
        "error": "bad_verification_code",
        "error_description": "Invalid code",
    }

    mock_client_instance = AsyncMock()
    mock_client_instance.post.return_value = mock_token_resp
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.api.v1.github_oauth.settings") as mock_settings,
        patch("app.api.v1.github_oauth.httpx.AsyncClient", return_value=mock_client_instance),
    ):
        mock_settings.GITHUB_CLIENT_ID = "test-id"
        mock_settings.GITHUB_CLIENT_SECRET = "test-secret"
        resp = await async_client.post(
            "/api/v1/auth/github/callback",
            json={"code": "bad-code"},
        )

    assert resp.status_code == 400
    assert "Invalid code" in resp.json()["detail"]


async def test_github_callback_success_new_user(
    async_client: AsyncClient,
    db_session,
) -> None:
    """Should create a new user and return tokens on successful OAuth."""

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "gh_token_123"}

    mock_user_resp = MagicMock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {
        "id": 12345,
        "login": "testuser",
        "name": "Test User",
        "email": "test@github.com",
        "avatar_url": "https://github.com/avatar.png",
    }

    mock_emails_resp = MagicMock()
    mock_emails_resp.status_code = 200
    mock_emails_resp.json.return_value = [
        {"email": "test@github.com", "primary": True, "verified": True},
    ]

    # We need two httpx.AsyncClient contexts: one for token, one for user+emails
    mock_client_token = AsyncMock()
    mock_client_token.post.return_value = mock_token_resp
    mock_client_token.__aenter__ = AsyncMock(return_value=mock_client_token)
    mock_client_token.__aexit__ = AsyncMock(return_value=None)

    mock_client_user = AsyncMock()
    mock_client_user.get.side_effect = [mock_user_resp, mock_emails_resp]
    mock_client_user.__aenter__ = AsyncMock(return_value=mock_client_user)
    mock_client_user.__aexit__ = AsyncMock(return_value=None)

    clients = [mock_client_token, mock_client_user]
    call_count = {"n": 0}

    def _make_client(*args, **kwargs):
        c = clients[call_count["n"]]
        call_count["n"] += 1
        return c

    with (
        patch("app.api.v1.github_oauth.settings") as mock_settings,
        patch("app.api.v1.github_oauth.httpx.AsyncClient", side_effect=_make_client),
    ):
        mock_settings.GITHUB_CLIENT_ID = "test-id"
        mock_settings.GITHUB_CLIENT_SECRET = "test-secret"
        mock_settings.JWT_EXPIRE_MINUTES = 60
        resp = await async_client.post(
            "/api/v1/auth/github/callback",
            json={"code": "valid-code"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_github_callback_user_no_email(
    async_client: AsyncClient,
    db_session,
) -> None:
    """Should return 400 when no verified email found."""

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "gh_token_456"}

    mock_user_resp = MagicMock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {"id": 99999, "login": "noemail", "name": "No Email"}

    mock_emails_resp = MagicMock()
    mock_emails_resp.status_code = 200
    mock_emails_resp.json.return_value = []

    mock_client_token = AsyncMock()
    mock_client_token.post.return_value = mock_token_resp
    mock_client_token.__aenter__ = AsyncMock(return_value=mock_client_token)
    mock_client_token.__aexit__ = AsyncMock(return_value=None)

    mock_client_user = AsyncMock()
    mock_client_user.get.side_effect = [mock_user_resp, mock_emails_resp]
    mock_client_user.__aenter__ = AsyncMock(return_value=mock_client_user)
    mock_client_user.__aexit__ = AsyncMock(return_value=None)

    clients = [mock_client_token, mock_client_user]
    call_count = {"n": 0}

    def _make_client(*args, **kwargs):
        c = clients[call_count["n"]]
        call_count["n"] += 1
        return c

    with (
        patch("app.api.v1.github_oauth.settings") as mock_settings,
        patch("app.api.v1.github_oauth.httpx.AsyncClient", side_effect=_make_client),
    ):
        mock_settings.GITHUB_CLIENT_ID = "test-id"
        mock_settings.GITHUB_CLIENT_SECRET = "test-secret"
        resp = await async_client.post(
            "/api/v1/auth/github/callback",
            json={"code": "valid-code"},
        )

    assert resp.status_code == 400
    assert "email" in resp.json()["detail"].lower()


async def test_github_callback_failed_user_fetch(
    async_client: AsyncClient,
    db_session,
) -> None:
    """Should return 400 when fetching GitHub user fails."""

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "gh_token_789"}

    mock_user_resp = MagicMock()
    mock_user_resp.status_code = 401

    mock_emails_resp = MagicMock()
    mock_emails_resp.status_code = 401

    mock_client_token = AsyncMock()
    mock_client_token.post.return_value = mock_token_resp
    mock_client_token.__aenter__ = AsyncMock(return_value=mock_client_token)
    mock_client_token.__aexit__ = AsyncMock(return_value=None)

    mock_client_user = AsyncMock()
    mock_client_user.get.side_effect = [mock_user_resp, mock_emails_resp]
    mock_client_user.__aenter__ = AsyncMock(return_value=mock_client_user)
    mock_client_user.__aexit__ = AsyncMock(return_value=None)

    clients = [mock_client_token, mock_client_user]
    call_count = {"n": 0}

    def _make_client(*args, **kwargs):
        c = clients[call_count["n"]]
        call_count["n"] += 1
        return c

    with (
        patch("app.api.v1.github_oauth.settings") as mock_settings,
        patch("app.api.v1.github_oauth.httpx.AsyncClient", side_effect=_make_client),
    ):
        mock_settings.GITHUB_CLIENT_ID = "test-id"
        mock_settings.GITHUB_CLIENT_SECRET = "test-secret"
        resp = await async_client.post(
            "/api/v1/auth/github/callback",
            json={"code": "valid-code"},
        )

    assert resp.status_code == 400
