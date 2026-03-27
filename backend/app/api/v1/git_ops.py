"""Git integration API endpoints — OAuth, cloning, diffs, and file listings."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.git import repo_manager
from app.git.diff_parser import parse_diff
from app.git.github_client import GitHubClient
from app.models.project import Project
from app.models.ticket import Ticket
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

# Base directory for cloned repositories
_REPOS_DIR = Path("/tmp/ai-coding-repos")  # noqa: S108


# ── Schemas ───────────────────────────────────────────────────────────


class OAuthUrlResponse(BaseModel):
    url: str


class OAuthCallbackResponse(BaseModel):
    access_token: str


class CloneRequest(BaseModel):
    repo_url: str
    branch: str = "main"


class CloneStatusResponse(BaseModel):
    cloned: bool
    repo_path: str | None = None
    branch: str | None = None


class DiffFileResponse(BaseModel):
    file_path: str
    old_path: str
    added_lines: int
    removed_lines: int


class DiffResponse(BaseModel):
    base_branch: str
    head_branch: str
    files: list[DiffFileResponse]
    raw_diff: str


class ChangedFileResponse(BaseModel):
    files: list[str]


# ── Helpers ───────────────────────────────────────────────────────────


def _repo_path(project_id: uuid.UUID) -> Path:
    return _REPOS_DIR / str(project_id)


async def _get_project(
    project_id: uuid.UUID,
    db: AsyncSession,
) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


async def _get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession,
) -> Ticket:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    return ticket


# ── OAuth ─────────────────────────────────────────────────────────────


@router.get("/git/oauth-url", response_model=OAuthUrlResponse)
async def get_oauth_url(
    _current_user: Annotated[User, Depends(get_current_user)],
    state: str | None = Query(default=None),
) -> OAuthUrlResponse:
    """Return the GitHub OAuth authorization URL."""
    try:
        url = GitHubClient.get_oauth_url(state=state)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return OAuthUrlResponse(url=url)


@router.get("/git/callback", response_model=OAuthCallbackResponse)
async def oauth_callback(
    code: str = Query(...),
) -> OAuthCallbackResponse:
    """Handle the GitHub OAuth callback and exchange the code for a token."""
    try:
        access_token = await GitHubClient.exchange_code(code)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return OAuthCallbackResponse(access_token=access_token)


# ── Clone ─────────────────────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/git/clone",
    status_code=status.HTTP_202_ACCEPTED,
)
async def clone_project_repo(
    project_id: uuid.UUID,
    body: CloneRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Clone (or re-clone) the repository for a project."""
    project = await _get_project(project_id, db)

    dest = _repo_path(project_id)

    if dest.exists():
        logger.info("Repository already cloned at %s; pulling latest.", dest)
        # Fetch latest instead of re-cloning
        try:
            await repo_manager._run_git_checked("fetch", "--all", cwd=dest)
            await repo_manager._run_git_checked(
                "reset",
                "--hard",
                f"origin/{body.branch}",
                cwd=dest,
            )
        except repo_manager.GitCommandError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update repository: {exc}",
            ) from exc
        return {"status": "updated", "repo_path": str(dest)}

    try:
        await repo_manager.clone_repo(body.repo_url, dest, branch=body.branch)
    except (repo_manager.GitCommandError, TimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Clone failed: {exc}",
        ) from exc

    # Persist the repo URL on the project if not already set
    if not project.github_repo_url:
        project.github_repo_url = body.repo_url
        project.default_branch = body.branch

    logger.info("Cloned %s for project %s", body.repo_url, project_id)
    return {"status": "cloned", "repo_path": str(dest)}


@router.get("/projects/{project_id}/git/status", response_model=CloneStatusResponse)
async def clone_status(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CloneStatusResponse:
    """Check whether the project repository has been cloned locally."""
    project = await _get_project(project_id, db)
    dest = _repo_path(project_id)

    if dest.exists() and (dest / ".git").exists():
        return CloneStatusResponse(
            cloned=True,
            repo_path=str(dest),
            branch=project.default_branch,
        )
    return CloneStatusResponse(cloned=False)


# ── Diff / Changed Files ─────────────────────────────────────────────


@router.get("/tickets/{ticket_id}/git/diff", response_model=DiffResponse)
async def ticket_diff(
    ticket_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DiffResponse:
    """Return the diff between the ticket branch and the project default branch."""
    ticket = await _get_ticket(ticket_id, db)
    if not ticket.branch_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticket has no associated branch.",
        )

    project = await _get_project(ticket.project_id, db)
    repo_path = _repo_path(project.id)

    if not repo_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository has not been cloned yet.",
        )

    try:
        raw_diff = await repo_manager.get_diff(
            repo_path,
            project.default_branch,
            ticket.branch_name,
        )
    except repo_manager.GitCommandError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate diff: {exc}",
        ) from exc

    parsed = parse_diff(raw_diff)

    return DiffResponse(
        base_branch=project.default_branch,
        head_branch=ticket.branch_name,
        files=[
            DiffFileResponse(
                file_path=fd.file_path,
                old_path=fd.old_path,
                added_lines=fd.added_lines,
                removed_lines=fd.removed_lines,
            )
            for fd in parsed
        ],
        raw_diff=raw_diff,
    )


@router.get("/tickets/{ticket_id}/git/files", response_model=ChangedFileResponse)
async def ticket_changed_files(
    ticket_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangedFileResponse:
    """List files changed on the ticket branch vs. the default branch."""
    ticket = await _get_ticket(ticket_id, db)
    if not ticket.branch_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ticket has no associated branch.",
        )

    project = await _get_project(ticket.project_id, db)
    repo_path = _repo_path(project.id)

    if not repo_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository has not been cloned yet.",
        )

    try:
        files = await repo_manager.get_changed_files(
            repo_path,
            project.default_branch,
            ticket.branch_name,
        )
    except repo_manager.GitCommandError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list changed files: {exc}",
        ) from exc

    return ChangedFileResponse(files=files)
