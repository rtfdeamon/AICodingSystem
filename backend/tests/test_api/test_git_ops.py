"""Tests for git_ops API endpoints."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.git.repo_manager import GitCommandError, GitResult
from app.models.project import Project
from app.models.ticket import ColumnName, Priority, Ticket
from app.models.user import User
from app.services.auth_service import create_access_token, hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASS = "strongpassword123"  # noqa: S105


async def _make_user(db: AsyncSession) -> tuple[User, dict[str, str]]:
    """Create a unique user and return (user, auth_headers)."""
    user = User(
        id=uuid.uuid4(),
        email=f"git-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password(_PASS),
        full_name="Git Tester",
        role="owner",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    token = create_access_token(user.id, user.role)
    return user, {"Authorization": f"Bearer {token}"}


async def _make_project(
    db: AsyncSession,
    user: User,
    *,
    github_repo_url: str | None = None,
    default_branch: str = "main",
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name="Git Project",
        slug=f"git-{uuid.uuid4().hex[:8]}",
        created_by=user.id,
        github_repo_url=github_repo_url,
        default_branch=default_branch,
    )
    db.add(project)
    await db.flush()
    return project


async def _make_ticket(
    db: AsyncSession,
    project: Project,
    *,
    branch_name: str | None = None,
) -> Ticket:
    ticket = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        ticket_number=1,
        title="Test Ticket",
        description="desc",
        column_name=ColumnName("backlog"),
        priority=Priority("P2"),
        branch_name=branch_name,
    )
    db.add(ticket)
    await db.flush()
    return ticket


def _git_error(msg: str = "command failed") -> GitCommandError:
    """Build a GitCommandError with a fake GitResult."""
    return GitCommandError(msg, GitResult(returncode=1, stdout="", stderr=msg))


def _fake_path(*, exists: bool = True, has_git: bool = True) -> MagicMock:
    """Build a mock Path with controllable .exists() and / '.git' behaviour."""
    dest = MagicMock(spec=Path)
    dest.exists.return_value = exists
    dest.__str__ = lambda self: "/repos/fake"
    if exists:
        git_dir = MagicMock(spec=Path)
        git_dir.exists.return_value = has_git
        dest.__truediv__ = lambda self, key: git_dir
    return dest


# ---------------------------------------------------------------------------
# OAuth endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_oauth_url_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await _make_user(db_session)
    with patch(
        "app.api.v1.git_ops.GitHubClient.get_oauth_url",
        return_value="https://github.com/login/oauth/authorize?client_id=abc",
    ):
        resp = await async_client.get("/api/v1/git/oauth-url", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://github.com")


@pytest.mark.asyncio
async def test_get_oauth_url_with_state(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await _make_user(db_session)
    with patch(
        "app.api.v1.git_ops.GitHubClient.get_oauth_url",
        return_value="https://github.com/login/oauth/authorize?state=xyz",
    ) as mock_get:
        resp = await async_client.get(
            "/api/v1/git/oauth-url",
            params={"state": "xyz"},
            headers=headers,
        )

    assert resp.status_code == 200
    mock_get.assert_called_once_with(state="xyz")


@pytest.mark.asyncio
async def test_get_oauth_url_value_error(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await _make_user(db_session)
    with patch(
        "app.api.v1.git_ops.GitHubClient.get_oauth_url",
        side_effect=ValueError("Client ID not configured"),
    ):
        resp = await async_client.get("/api/v1/git/oauth-url", headers=headers)

    assert resp.status_code == 503
    assert "Client ID not configured" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_oauth_url_unauthenticated(async_client: AsyncClient) -> None:
    resp = await async_client.get("/api/v1/git/oauth-url")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_oauth_callback_success(async_client: AsyncClient) -> None:
    with patch(
        "app.api.v1.git_ops.GitHubClient.exchange_code",
        new_callable=AsyncMock,
        return_value="gho_fake_token_abc123",
    ):
        resp = await async_client.get(
            "/api/v1/git/callback",
            params={"code": "test-code"},
        )

    assert resp.status_code == 200
    assert resp.json()["access_token"] == "gho_fake_token_abc123"


@pytest.mark.asyncio
async def test_oauth_callback_value_error(async_client: AsyncClient) -> None:
    with patch(
        "app.api.v1.git_ops.GitHubClient.exchange_code",
        new_callable=AsyncMock,
        side_effect=ValueError("Invalid code"),
    ):
        resp = await async_client.get(
            "/api/v1/git/callback",
            params={"code": "bad-code"},
        )

    assert resp.status_code == 400
    assert "Invalid code" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Clone endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clone_project_repo_fresh(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)

    with patch("app.api.v1.git_ops._repo_path") as mock_path, patch(
        "app.api.v1.git_ops.repo_manager.clone_repo",
        new_callable=AsyncMock,
    ) as mock_clone:
        mock_path.return_value = _fake_path(exists=False)

        resp = await async_client.post(
            f"/api/v1/projects/{project.id}/git/clone",
            json={"repo_url": "https://github.com/o/r.git", "branch": "main"},
            headers=headers,
        )

    assert resp.status_code == 202
    assert resp.json()["status"] == "cloned"
    mock_clone.assert_awaited_once()


@pytest.mark.asyncio
async def test_clone_project_repo_already_cloned(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)

    with patch("app.api.v1.git_ops._repo_path") as mock_path, patch(
        "app.api.v1.git_ops.repo_manager._run_git_checked",
        new_callable=AsyncMock,
    ):
        mock_path.return_value = _fake_path(exists=True)

        resp = await async_client.post(
            f"/api/v1/projects/{project.id}/git/clone",
            json={"repo_url": "https://github.com/o/r.git"},
            headers=headers,
        )

    assert resp.status_code == 202
    assert resp.json()["status"] == "updated"


@pytest.mark.asyncio
async def test_clone_project_repo_update_fails(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)

    with patch("app.api.v1.git_ops._repo_path") as mock_path, patch(
        "app.api.v1.git_ops.repo_manager._run_git_checked",
        new_callable=AsyncMock,
        side_effect=_git_error("fetch failed"),
    ):
        mock_path.return_value = _fake_path(exists=True)

        resp = await async_client.post(
            f"/api/v1/projects/{project.id}/git/clone",
            json={"repo_url": "https://github.com/o/r.git"},
            headers=headers,
        )

    assert resp.status_code == 500
    assert "Failed to update repository" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_clone_project_repo_clone_fails(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)

    with patch("app.api.v1.git_ops._repo_path") as mock_path, patch(
        "app.api.v1.git_ops.repo_manager.clone_repo",
        new_callable=AsyncMock,
        side_effect=_git_error("clone failed"),
    ):
        mock_path.return_value = _fake_path(exists=False)

        resp = await async_client.post(
            f"/api/v1/projects/{project.id}/git/clone",
            json={"repo_url": "https://github.com/o/r.git"},
            headers=headers,
        )

    assert resp.status_code == 500
    assert "Clone failed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_clone_project_repo_timeout(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)

    with patch("app.api.v1.git_ops._repo_path") as mock_path, patch(
        "app.api.v1.git_ops.repo_manager.clone_repo",
        new_callable=AsyncMock,
        side_effect=TimeoutError("clone timed out"),
    ):
        mock_path.return_value = _fake_path(exists=False)

        resp = await async_client.post(
            f"/api/v1/projects/{project.id}/git/clone",
            json={"repo_url": "https://github.com/o/r.git"},
            headers=headers,
        )

    assert resp.status_code == 500
    assert "Clone failed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_clone_project_not_found(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await _make_user(db_session)
    fake_id = uuid.uuid4()
    resp = await async_client.post(
        f"/api/v1/projects/{fake_id}/git/clone",
        json={"repo_url": "https://github.com/o/r.git"},
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_clone_fresh_calls_clone_repo(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A fresh clone invokes repo_manager.clone_repo with correct args."""
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user, github_repo_url=None)

    with patch("app.api.v1.git_ops._repo_path") as mock_path, patch(
        "app.api.v1.git_ops.repo_manager.clone_repo",
        new_callable=AsyncMock,
    ) as mock_clone:
        fake_dest = _fake_path(exists=False)
        mock_path.return_value = fake_dest

        resp = await async_client.post(
            f"/api/v1/projects/{project.id}/git/clone",
            json={"repo_url": "https://github.com/o/r.git", "branch": "develop"},
            headers=headers,
        )

    assert resp.status_code == 202
    assert resp.json()["status"] == "cloned"
    mock_clone.assert_awaited_once_with(
        "https://github.com/o/r.git", fake_dest, branch="develop",
    )


# ---------------------------------------------------------------------------
# Clone status endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clone_status_cloned(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)

    with patch("app.api.v1.git_ops._repo_path") as mock_path:
        mock_path.return_value = _fake_path(exists=True, has_git=True)

        resp = await async_client.get(
            f"/api/v1/projects/{project.id}/git/status",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["cloned"] is True
    assert data["repo_path"] is not None


@pytest.mark.asyncio
async def test_clone_status_not_cloned(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)

    with patch("app.api.v1.git_ops._repo_path") as mock_path:
        mock_path.return_value = _fake_path(exists=False)

        resp = await async_client.get(
            f"/api/v1/projects/{project.id}/git/status",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["cloned"] is False
    assert data["repo_path"] is None


@pytest.mark.asyncio
async def test_clone_status_dir_exists_no_git(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Directory exists but .git subdirectory does not."""
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)

    with patch("app.api.v1.git_ops._repo_path") as mock_path:
        mock_path.return_value = _fake_path(exists=True, has_git=False)

        resp = await async_client.get(
            f"/api/v1/projects/{project.id}/git/status",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["cloned"] is False


@pytest.mark.asyncio
async def test_clone_status_project_not_found(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await _make_user(db_session)
    fake_id = uuid.uuid4()
    resp = await async_client.get(
        f"/api/v1/projects/{fake_id}/git/status",
        headers=headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Ticket diff endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ticket_diff_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)
    ticket = await _make_ticket(db_session, project, branch_name="feature/my-branch")

    raw_diff = "diff --git a/foo.py b/foo.py\n+new line"

    with patch("app.api.v1.git_ops._repo_path") as mock_path, patch(
        "app.api.v1.git_ops.repo_manager.get_diff",
        new_callable=AsyncMock,
        return_value=raw_diff,
    ), patch(
        "app.api.v1.git_ops.parse_diff",
        return_value=[
            MagicMock(
                file_path="foo.py",
                old_path="foo.py",
                added_lines=1,
                removed_lines=0,
            ),
        ],
    ):
        mock_path.return_value = _fake_path(exists=True)

        resp = await async_client.get(
            f"/api/v1/tickets/{ticket.id}/git/diff",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["head_branch"] == "feature/my-branch"
    assert data["base_branch"] == "main"
    assert len(data["files"]) == 1
    assert data["files"][0]["file_path"] == "foo.py"
    assert data["raw_diff"] == raw_diff


@pytest.mark.asyncio
async def test_ticket_diff_no_branch(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)
    ticket = await _make_ticket(db_session, project, branch_name=None)

    resp = await async_client.get(
        f"/api/v1/tickets/{ticket.id}/git/diff",
        headers=headers,
    )

    assert resp.status_code == 400
    assert "no associated branch" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ticket_diff_repo_not_cloned(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)
    ticket = await _make_ticket(db_session, project, branch_name="feature/test")

    with patch("app.api.v1.git_ops._repo_path") as mock_path:
        mock_path.return_value = _fake_path(exists=False)

        resp = await async_client.get(
            f"/api/v1/tickets/{ticket.id}/git/diff",
            headers=headers,
        )

    assert resp.status_code == 400
    assert "not been cloned" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ticket_diff_git_error(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)
    ticket = await _make_ticket(db_session, project, branch_name="feature/err")

    with patch("app.api.v1.git_ops._repo_path") as mock_path, patch(
        "app.api.v1.git_ops.repo_manager.get_diff",
        new_callable=AsyncMock,
        side_effect=_git_error("diff failed"),
    ):
        mock_path.return_value = _fake_path(exists=True)

        resp = await async_client.get(
            f"/api/v1/tickets/{ticket.id}/git/diff",
            headers=headers,
        )

    assert resp.status_code == 500
    assert "Failed to generate diff" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ticket_diff_ticket_not_found(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await _make_user(db_session)
    fake_id = uuid.uuid4()
    resp = await async_client.get(
        f"/api/v1/tickets/{fake_id}/git/diff",
        headers=headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Ticket changed files endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ticket_changed_files_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)
    ticket = await _make_ticket(db_session, project, branch_name="feature/files")

    with patch("app.api.v1.git_ops._repo_path") as mock_path, patch(
        "app.api.v1.git_ops.repo_manager.get_changed_files",
        new_callable=AsyncMock,
        return_value=["foo.py", "bar.py"],
    ):
        mock_path.return_value = _fake_path(exists=True)

        resp = await async_client.get(
            f"/api/v1/tickets/{ticket.id}/git/files",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["files"] == ["foo.py", "bar.py"]


@pytest.mark.asyncio
async def test_ticket_changed_files_no_branch(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)
    ticket = await _make_ticket(db_session, project, branch_name=None)

    resp = await async_client.get(
        f"/api/v1/tickets/{ticket.id}/git/files",
        headers=headers,
    )

    assert resp.status_code == 400
    assert "no associated branch" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ticket_changed_files_repo_not_cloned(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)
    ticket = await _make_ticket(db_session, project, branch_name="feature/noclone")

    with patch("app.api.v1.git_ops._repo_path") as mock_path:
        mock_path.return_value = _fake_path(exists=False)

        resp = await async_client.get(
            f"/api/v1/tickets/{ticket.id}/git/files",
            headers=headers,
        )

    assert resp.status_code == 400
    assert "not been cloned" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ticket_changed_files_git_error(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await _make_user(db_session)
    project = await _make_project(db_session, user)
    ticket = await _make_ticket(db_session, project, branch_name="feature/git-err")

    with patch("app.api.v1.git_ops._repo_path") as mock_path, patch(
        "app.api.v1.git_ops.repo_manager.get_changed_files",
        new_callable=AsyncMock,
        side_effect=_git_error("list failed"),
    ):
        mock_path.return_value = _fake_path(exists=True)

        resp = await async_client.get(
            f"/api/v1/tickets/{ticket.id}/git/files",
            headers=headers,
        )

    assert resp.status_code == 500
    assert "Failed to list changed files" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ticket_changed_files_ticket_not_found(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await _make_user(db_session)
    fake_id = uuid.uuid4()
    resp = await async_client.get(
        f"/api/v1/tickets/{fake_id}/git/files",
        headers=headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


def test_repo_path_helper() -> None:
    from app.api.v1.git_ops import _repo_path

    pid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    result = _repo_path(pid)
    assert str(result).endswith("12345678-1234-5678-1234-567812345678")
