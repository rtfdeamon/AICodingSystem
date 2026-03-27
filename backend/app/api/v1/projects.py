"""Project CRUD endpoints."""

from __future__ import annotations

import logging
import math
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _slugify(name: str) -> str:
    """Convert a project name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "project"


def _project_to_response(project: Project) -> ProjectResponse:
    """Map a Project ORM instance to the API response schema."""
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        repo_url=project.github_repo_url,
        default_branch=project.default_branch,
        creator_id=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=201,
)
async def create_project(
    data: ProjectCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectResponse:
    """Create a new project."""
    slug = _slugify(data.name)

    # Ensure slug uniqueness by appending a short suffix if needed
    existing = await db.execute(select(Project).where(Project.slug == slug))
    if existing.scalar_one_or_none() is not None:
        slug = f"{slug}-{uuid.uuid4().hex[:8]}"

    project = Project(
        name=data.name,
        slug=slug,
        description=data.description,
        github_repo_url=data.repo_url,
        default_branch=data.default_branch,
        created_by=current_user.id,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return _project_to_response(project)


@router.get(
    "",
    response_model=ProjectListResponse,
)
async def list_projects(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> ProjectListResponse:
    """List all projects with pagination."""
    # Total count
    count_result = await db.execute(select(func.count(Project.id)))
    total = count_result.scalar_one()

    # Fetch page
    offset = (page - 1) * per_page
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc()).offset(offset).limit(per_page)
    )
    projects = result.scalars().all()

    return ProjectListResponse(
        items=[_project_to_response(p) for p in projects],
        total=total,
        page=page,
        page_size=per_page,
        pages=max(1, math.ceil(total / per_page)),
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def get_project(
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectResponse:
    """Get a single project by id."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return _project_to_response(project)


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> ProjectResponse:
    """Update project fields."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Map schema field names to model field names
    field_map = {"repo_url": "github_repo_url"}

    for field, value in update_data.items():
        model_field = field_map.get(field, field)
        setattr(project, model_field, value)

    # Regenerate slug if name changed
    if "name" in update_data and update_data["name"] is not None:
        new_slug = _slugify(update_data["name"])
        existing = await db.execute(
            select(Project).where(Project.slug == new_slug, Project.id != project_id)
        )
        if existing.scalar_one_or_none() is not None:
            new_slug = f"{new_slug}-{uuid.uuid4().hex[:8]}"
        project.slug = new_slug

    await db.flush()
    await db.refresh(project)
    return _project_to_response(project)


@router.delete(
    "/{project_id}",
    status_code=204,
)
async def delete_project(
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("owner", "pm_lead"))],
) -> None:
    """Delete a project. Restricted to owner and pm_lead roles."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    await db.delete(project)
    await db.flush()
