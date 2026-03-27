"""Context Engine API endpoints — indexing, search, and dependency lookup."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.context.engine import ContextEngine
from app.database import get_db
from app.models.project import Project
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

# Must match the repos directory used by git_ops
_REPOS_DIR = Path("/tmp/ai-coding-repos")  # noqa: S108


# ── Schemas ───────────────────────────────────────────────────────────


class IndexRequest(BaseModel):
    commit_sha: str | None = None


class IndexStatusResponse(BaseModel):
    indexed: bool
    files_scanned: int | None = None
    chunks_indexed: int | None = None
    commit_sha: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)


class SearchResultItem(BaseModel):
    file_path: str
    chunk_index: int
    chunk_text: str
    language: str
    symbol_name: str | None
    score: float
    commit_sha: str | None


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    query: str
    total: int


class DependencyResponse(BaseModel):
    file_path: str
    dependencies: list[str]
    message: str


# ── Helpers ───────────────────────────────────────────────────────────


async def _get_project(
    project_id: uuid.UUID,
    db: AsyncSession,
) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return project


def _repo_path(project_id: uuid.UUID) -> Path:
    return _REPOS_DIR / str(project_id)


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/context/index",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_index(
    project_id: uuid.UUID,
    body: IndexRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Trigger a full re-index of the project repository.

    The repository must already be cloned via the git/clone endpoint.
    """
    await _get_project(project_id, db)
    repo_path = _repo_path(project_id)

    if not repo_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository has not been cloned yet. Use POST /git/clone first.",
        )

    engine = ContextEngine(session=db)
    try:
        summary = await engine.index_repo(
            project_id=project_id,
            repo_path=repo_path,
            commit_sha=body.commit_sha,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Indexing failed for project %s", project_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Indexing failed: {exc}",
        ) from exc

    return {"status": "indexed", **summary}


@router.get(
    "/projects/{project_id}/context/status",
    response_model=IndexStatusResponse,
)
async def index_status(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IndexStatusResponse:
    """Check whether the project has been indexed and return basic stats."""
    from sqlalchemy import func as sqlfunc

    from app.models.code_embedding import CodeEmbedding

    await _get_project(project_id, db)

    # Count embeddings
    count_result = await db.execute(
        select(sqlfunc.count(CodeEmbedding.id)).where(CodeEmbedding.project_id == project_id)
    )
    total_chunks: int = count_result.scalar_one()

    if total_chunks == 0:
        return IndexStatusResponse(indexed=False)

    # Count distinct files
    files_result = await db.execute(
        select(sqlfunc.count(sqlfunc.distinct(CodeEmbedding.file_path))).where(
            CodeEmbedding.project_id == project_id
        )
    )
    file_count: int = files_result.scalar_one()

    # Get latest commit_sha
    sha_result = await db.execute(
        select(CodeEmbedding.commit_sha)
        .where(CodeEmbedding.project_id == project_id)
        .order_by(CodeEmbedding.created_at.desc())
        .limit(1)
    )
    latest_sha = sha_result.scalar_one_or_none()

    return IndexStatusResponse(
        indexed=True,
        files_scanned=file_count,
        chunks_indexed=total_chunks,
        commit_sha=latest_sha,
    )


@router.post(
    "/projects/{project_id}/context/search",
    response_model=SearchResponse,
)
async def semantic_search(
    project_id: uuid.UUID,
    body: SearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SearchResponse:
    """Perform semantic search over the indexed codebase."""
    await _get_project(project_id, db)

    engine = ContextEngine(session=db)
    results = await engine.search(
        project_id=project_id,
        query=body.query,
        top_k=body.top_k,
    )

    return SearchResponse(
        results=[
            SearchResultItem(
                file_path=r.file_path,
                chunk_index=r.chunk_index,
                chunk_text=r.chunk_text,
                language=r.language,
                symbol_name=r.symbol_name,
                score=r.score,
                commit_sha=r.commit_sha,
            )
            for r in results
        ],
        query=body.query,
        total=len(results),
    )


@router.get("/context/deps/{file_path:path}", response_model=DependencyResponse)
async def file_dependencies(
    file_path: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> DependencyResponse:
    """Return known dependencies for a file (placeholder implementation).

    A full dependency analysis (import graph traversal, call graph, etc.)
    is planned for a future iteration.  This endpoint currently returns
    an empty list with an informational message.
    """
    return DependencyResponse(
        file_path=file_path,
        dependencies=[],
        message="Dependency analysis is not yet implemented. "
        "This endpoint will be enhanced in a future iteration.",
    )
