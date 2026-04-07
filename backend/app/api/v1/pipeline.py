"""Pipeline status and background task monitoring endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models.user import User
from app.services.task_queue import TaskStatus, task_queue

router = APIRouter()


@router.get("/pipeline/tasks")
async def list_pipeline_tasks(
    ticket_id: str | None = None,
    task_status: str | None = None,
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List background pipeline tasks, optionally filtered by ticket_id or status."""
    parsed_status = None
    if task_status:
        try:
            parsed_status = TaskStatus(task_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {task_status}. Must be one of: {[s.value for s in TaskStatus]}",
            )
    return task_queue.list_tasks(ticket_id=ticket_id, status=parsed_status)


@router.get("/pipeline/tasks/{task_id}")
async def get_pipeline_task(
    task_id: str,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get details of a specific background task."""
    record = task_queue.get_task(task_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    return record.to_dict()


@router.post("/pipeline/trigger/{ticket_id}/{phase}")
async def trigger_pipeline_phase(
    ticket_id: uuid.UUID,
    phase: str,
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Manually trigger a pipeline phase for a ticket.

    Phases: ``planning``, ``coding``, ``review``, ``testing``, ``deploy_staging``, ``deploy_production``
    """
    from app.services.pipeline_trigger import (
        _dispatch_coding,
        _dispatch_deploy,
        _dispatch_planning,
        _dispatch_review,
        _dispatch_testing,
    )

    # Placeholder project_id — the dispatch functions fetch it from the ticket
    project_id = uuid.UUID(int=0)

    dispatch_map = {
        "planning": lambda: _dispatch_planning(ticket_id, project_id),
        "coding": lambda: _dispatch_coding(ticket_id, project_id),
        "review": lambda: _dispatch_review(ticket_id, project_id),
        "testing": lambda: _dispatch_testing(ticket_id, project_id),
        "deploy_staging": lambda: _dispatch_deploy(ticket_id, project_id, "staging"),
        "deploy_production": lambda: _dispatch_deploy(ticket_id, project_id, "production"),
    }

    if phase not in dispatch_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown phase: {phase}. Available: {list(dispatch_map.keys())}",
        )

    bg_task_id = dispatch_map[phase]()
    return {"task_id": bg_task_id, "phase": phase, "ticket_id": str(ticket_id)}
