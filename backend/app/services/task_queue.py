"""Lightweight async background task queue for AI agent execution.

Uses asyncio.create_task() with a bounded semaphore to avoid spawning
too many concurrent agent calls.  In production this should be replaced
with Celery/RQ/ARQ, but for dev/staging this is sufficient.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskRecord:
    __slots__ = (
        "task_id",
        "name",
        "status",
        "created_at",
        "started_at",
        "completed_at",
        "result",
        "error",
        "ticket_id",
    )

    def __init__(self, task_id: str, name: str, ticket_id: str | None = None) -> None:
        self.task_id = task_id
        self.name = name
        self.status = TaskStatus.QUEUED
        self.created_at = datetime.now(UTC)
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.result: Any = None
        self.error: str | None = None
        self.ticket_id = ticket_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "ticket_id": self.ticket_id,
        }


class BackgroundTaskQueue:
    """Async background task queue with bounded concurrency."""

    def __init__(self, max_concurrency: int = 3) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._tasks: dict[str, TaskRecord] = {}
        self._running_asyncio_tasks: dict[str, asyncio.Task[None]] = {}

    def enqueue(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]],
        *,
        name: str = "task",
        ticket_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Enqueue a coroutine to run in the background.

        Returns the task_id for tracking.
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        record = TaskRecord(task_id=task_id, name=name, ticket_id=ticket_id)
        self._tasks[task_id] = record

        asyncio_task = asyncio.create_task(
            self._run(task_id, func, **kwargs),
            name=f"bg:{name}:{task_id}",
        )
        self._running_asyncio_tasks[task_id] = asyncio_task

        logger.info("Enqueued background task %s (%s) for ticket %s", task_id, name, ticket_id)
        return task_id

    async def _run(
        self,
        task_id: str,
        func: Callable[..., Coroutine[Any, Any, Any]],
        **kwargs: Any,
    ) -> None:
        record = self._tasks[task_id]

        async with self._semaphore:
            record.status = TaskStatus.RUNNING
            record.started_at = datetime.now(UTC)
            logger.info("Starting background task %s (%s)", task_id, record.name)

            try:
                record.result = await func(**kwargs)
                record.status = TaskStatus.COMPLETED
                logger.info("Background task %s completed successfully", task_id)
            except Exception as exc:
                record.status = TaskStatus.FAILED
                record.error = str(exc)
                logger.error(
                    "Background task %s failed: %s",
                    task_id,
                    exc,
                    exc_info=True,
                )
            finally:
                record.completed_at = datetime.now(UTC)
                self._running_asyncio_tasks.pop(task_id, None)

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def list_tasks(
        self,
        ticket_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[dict[str, Any]]:
        results = []
        for record in self._tasks.values():
            if ticket_id and record.ticket_id != ticket_id:
                continue
            if status and record.status != status:
                continue
            results.append(record.to_dict())
        return sorted(results, key=lambda r: r["created_at"], reverse=True)

    def cleanup_completed(self, max_age_hours: int = 24) -> int:
        """Remove completed/failed tasks older than max_age_hours."""
        now = datetime.now(UTC)
        to_remove = []
        for task_id, record in self._tasks.items():
            if record.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                if record.completed_at:
                    age = (now - record.completed_at).total_seconds() / 3600
                    if age > max_age_hours:
                        to_remove.append(task_id)
        for task_id in to_remove:
            del self._tasks[task_id]
        return len(to_remove)


# Singleton instance
task_queue = BackgroundTaskQueue(max_concurrency=3)
