"""Pipeline trigger — fires AI agent tasks when tickets move between columns.

This module is the critical glue between the Kanban state machine and the
AI pipeline orchestrator.  It listens for column transitions and dispatches
the appropriate background tasks.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.context.engine import ContextEngine
from app.models.ticket import ColumnName
from app.services.task_queue import task_queue
from app.workflows.pipeline_orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)

# Default repo base path (configurable via REPO_BASE_PATH env var)
REPO_BASE_PATH = Path(getattr(settings, "REPO_BASE_PATH", "./repos"))


async def on_ticket_moved(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    from_column: str,
    to_column: str,
    project_id: uuid.UUID,
) -> str | None:
    """React to a ticket column transition by dispatching the appropriate AI task.

    Returns the background task_id if a task was dispatched, or None.
    """

    # ── backlog → ai_planning: trigger planning agent ────────────────
    if to_column == ColumnName.AI_PLANNING.value:
        return _dispatch_planning(ticket_id, project_id)

    # ── plan_review → ai_coding: trigger coding agent ────────────────
    if (
        from_column == ColumnName.PLAN_REVIEW.value
        and to_column == ColumnName.AI_CODING.value
    ):
        return _dispatch_coding(ticket_id, project_id)

    # ── code_review/staging_verification → ai_coding: retry coding ───
    if (
        from_column in (ColumnName.CODE_REVIEW.value, ColumnName.STAGING_VERIFICATION.value)
        and to_column == ColumnName.AI_CODING.value
    ):
        return _dispatch_coding(ticket_id, project_id)

    # ── ai_coding → code_review: trigger AI review ───────────────────
    if to_column == ColumnName.CODE_REVIEW.value:
        return _dispatch_review(ticket_id, project_id)

    # ── code_review → staging: trigger testing + staging deploy ──────
    if to_column == ColumnName.STAGING.value:
        return _dispatch_testing(ticket_id, project_id)

    # ── staging_verification → production: trigger production deploy ──
    if to_column == ColumnName.PRODUCTION.value:
        return _dispatch_deploy(ticket_id, project_id, environment="production")

    return None


def _dispatch_planning(ticket_id: uuid.UUID, project_id: uuid.UUID) -> str:
    """Dispatch the planning agent as a background task."""

    async def _run_planning(
        ticket_id: uuid.UUID = ticket_id,
        project_id: uuid.UUID = project_id,
    ) -> dict:
        from app.database import async_session_factory

        async with async_session_factory() as db:
            context_engine = ContextEngine(db)
            orchestrator = PipelineOrchestrator(
                db=db,
                context_engine=context_engine,
                repo_base_path=REPO_BASE_PATH,
            )
            plan = await orchestrator.run_planning_phase(ticket_id)
            await db.commit()
            return {
                "plan_id": str(plan.id),
                "subtasks": len(plan.subtasks or []),
                "cost_usd": plan.cost_usd,
            }

    return task_queue.enqueue(
        _run_planning,
        name="planning",
        ticket_id=str(ticket_id),
    )


def _dispatch_coding(ticket_id: uuid.UUID, project_id: uuid.UUID) -> str:
    """Dispatch the coding agent as a background task."""

    async def _run_coding(
        ticket_id: uuid.UUID = ticket_id,
        project_id: uuid.UUID = project_id,
    ) -> dict:
        from app.database import async_session_factory

        async with async_session_factory() as db:
            context_engine = ContextEngine(db)
            orchestrator = PipelineOrchestrator(
                db=db,
                context_engine=context_engine,
                repo_base_path=REPO_BASE_PATH,
            )
            results = await orchestrator.run_coding_phase(ticket_id)
            await db.commit()
            return {
                "subtasks_processed": len(results),
                "total_cost_usd": sum(r.cost_usd for r in results),
            }

    return task_queue.enqueue(
        _run_coding,
        name="coding",
        ticket_id=str(ticket_id),
    )


def _dispatch_review(ticket_id: uuid.UUID, project_id: uuid.UUID) -> str:
    """Dispatch the three-layer AI review as a background task."""

    async def _run_review(
        ticket_id: uuid.UUID = ticket_id,
        project_id: uuid.UUID = project_id,
    ) -> dict:
        from app.database import async_session_factory

        async with async_session_factory() as db:
            context_engine = ContextEngine(db)
            orchestrator = PipelineOrchestrator(
                db=db,
                context_engine=context_engine,
                repo_base_path=REPO_BASE_PATH,
            )
            result = await orchestrator.run_review_phase(ticket_id)
            await db.commit()
            return result

    return task_queue.enqueue(
        _run_review,
        name="ai_review",
        ticket_id=str(ticket_id),
    )


def _dispatch_testing(ticket_id: uuid.UUID, project_id: uuid.UUID) -> str:
    """Dispatch testing + staging deploy as a background task."""

    async def _run_testing(
        ticket_id: uuid.UUID = ticket_id,
        project_id: uuid.UUID = project_id,
    ) -> dict:
        from app.database import async_session_factory

        async with async_session_factory() as db:
            context_engine = ContextEngine(db)
            orchestrator = PipelineOrchestrator(
                db=db,
                context_engine=context_engine,
                repo_base_path=REPO_BASE_PATH,
            )
            result = await orchestrator.run_testing_phase(ticket_id)
            await db.commit()
            return result

    return task_queue.enqueue(
        _run_testing,
        name="testing",
        ticket_id=str(ticket_id),
    )


def _dispatch_deploy(
    ticket_id: uuid.UUID,
    project_id: uuid.UUID,
    environment: str,
) -> str:
    """Dispatch a deployment as a background task."""

    async def _run_deploy(
        ticket_id: uuid.UUID = ticket_id,
        project_id: uuid.UUID = project_id,
        environment: str = environment,
    ) -> dict:
        from app.database import async_session_factory

        async with async_session_factory() as db:
            context_engine = ContextEngine(db)
            orchestrator = PipelineOrchestrator(
                db=db,
                context_engine=context_engine,
                repo_base_path=REPO_BASE_PATH,
            )
            result = await orchestrator.run_deploy_phase(ticket_id, environment)
            await db.commit()
            return result

    return task_queue.enqueue(
        _run_deploy,
        name=f"deploy:{environment}",
        ticket_id=str(ticket_id),
    )
