"""Pipeline Orchestrator — coordinates the full AI-driven coding pipeline."""

from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.coding_agent import CodeGenResult, generate_code
from app.agents.planning_agent import generate_plan
from app.agents.security_agent import SecurityReport, analyze_security
from app.agents.test_gen_agent import TestFile, generate_tests
from app.context.engine import ContextEngine
from app.git import repo_manager
from app.models.ai_code_generation import AiCodeGeneration, CodeGenStatus
from app.models.ai_plan import AiPlan, PlanStatus
from app.models.ticket import ColumnName, Ticket
from app.services.n8n_service import trigger_workflow

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Coordinates the end-to-end AI coding pipeline for a ticket.

    Each ``run_*_phase`` method encapsulates one stage of the pipeline,
    handles errors gracefully, and updates the ticket/board state.
    """

    def __init__(
        self,
        db: AsyncSession,
        context_engine: ContextEngine,
        repo_base_path: str | Path,
    ) -> None:
        self._db = db
        self._context = context_engine
        self._repo_base = Path(repo_base_path)

    # ── helpers ───────────────────────────────────────────────────────

    async def _get_ticket(self, ticket_id: uuid.UUID) -> Ticket:
        result = await self._db.execute(select(Ticket).where(Ticket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if ticket is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        return ticket

    async def _get_latest_plan(self, ticket_id: uuid.UUID) -> AiPlan:
        result = await self._db.execute(
            select(AiPlan)
            .where(AiPlan.ticket_id == ticket_id, AiPlan.status == PlanStatus.APPROVED)
            .order_by(AiPlan.version.desc())
            .limit(1)
        )
        plan = result.scalar_one_or_none()
        if plan is None:
            raise ValueError(f"No approved plan found for ticket {ticket_id}")
        return plan

    def _repo_path(self, project_id: uuid.UUID) -> Path:
        return self._repo_base / str(project_id)

    async def _update_ticket_column(
        self,
        ticket: Ticket,
        to_column: ColumnName,
    ) -> None:
        ticket.column_name = to_column
        ticket.position = 0
        await self._db.flush()

    async def _log_progress(
        self,
        ticket_id: uuid.UUID,
        phase: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Log pipeline progress and broadcast via WebSocket."""
        logger.info(
            "[Pipeline:%s] ticket=%s — %s %s",
            phase,
            ticket_id,
            message,
            data or "",
        )
        # Broadcast progress to connected clients via WebSocket
        from app.services.websocket_manager import ws_manager

        ticket = await self._get_ticket(ticket_id)
        event = {
            "type": f"pipeline.{phase}",
            "data": {
                "ticket_id": str(ticket_id),
                "project_id": str(ticket.project_id),
                "phase": phase,
                "message": message,
                **(data or {}),
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await ws_manager.broadcast_to_project(
            str(ticket.project_id),
            event,
        )

    # ── Phase 1: Planning ────────────────────────────────────────────

    async def run_planning_phase(self, ticket_id: uuid.UUID) -> AiPlan:
        """Generate an implementation plan and move ticket to ``plan_review``.

        Steps:
        1. Load the ticket.
        2. Call the planning agent to produce a structured plan.
        3. Persist the plan.
        4. Move the ticket to ``plan_review``.
        """
        await self._log_progress(ticket_id, "planning", "Starting planning phase")
        ticket = await self._get_ticket(ticket_id)

        plan = await generate_plan(
            ticket=ticket,
            project_id=ticket.project_id,
            context_engine=self._context,
            db=self._db,
        )

        await self._update_ticket_column(ticket, ColumnName.PLAN_REVIEW)
        await self._log_progress(
            ticket_id,
            "planning",
            f"Plan v{plan.version} generated with {len(plan.subtasks)} subtasks",
            {"plan_id": str(plan.id), "cost_usd": plan.cost_usd},
        )
        return plan

    # ── Phase 2: Coding ──────────────────────────────────────────────

    async def run_coding_phase(self, ticket_id: uuid.UUID) -> list[CodeGenResult]:
        """Generate code for each subtask in the approved plan.

        Steps:
        1. Load the ticket and its approved plan.
        2. Create a feature branch.
        3. For each subtask (in dependency order):
           a. Generate code via the coding agent.
           b. Lint, self-correct, and commit.
        4. Move the ticket to ``code_review``.
        """
        await self._log_progress(ticket_id, "coding", "Starting coding phase")
        ticket = await self._get_ticket(ticket_id)
        plan = await self._get_latest_plan(ticket_id)
        repo_path = self._repo_path(ticket.project_id)

        # Create feature branch
        branch_name = f"ai/{ticket.ticket_number}-{ticket.id.hex[:8]}"
        try:
            await repo_manager.create_branch(repo_path, branch_name)
            await repo_manager.checkout_branch(repo_path, branch_name)
        except Exception:
            # Branch may already exist from a previous attempt
            await repo_manager.checkout_branch(repo_path, branch_name)

        ticket.branch_name = branch_name

        results: list[CodeGenResult] = []
        subtasks = plan.subtasks or []

        for idx, subtask in enumerate(subtasks):
            await self._log_progress(
                ticket_id,
                "coding",
                f"Processing subtask {idx + 1}/{len(subtasks)}: {subtask.get('title', 'N/A')}",
            )

            try:
                result = await generate_code(
                    subtask=subtask,
                    subtask_index=idx,
                    plan=plan,
                    project_id=ticket.project_id,
                    context_engine=self._context,
                    repo_path=repo_path,
                    db=self._db,
                    ticket_id=ticket.id,
                    branch_name=branch_name,
                )
                results.append(result)
            except Exception as exc:
                logger.error(
                    "Subtask %d failed for ticket %s: %s",
                    idx,
                    ticket_id,
                    exc,
                )
                # Record the failure but continue with remaining subtasks
                failed_gen = AiCodeGeneration(
                    ticket_id=ticket.id,
                    plan_id=plan.id,
                    subtask_index=idx,
                    agent_name="unknown",
                    branch_name=branch_name,
                    status=CodeGenStatus.FAILED,
                )
                self._db.add(failed_gen)
                await self._db.flush()

        await self._update_ticket_column(ticket, ColumnName.CODE_REVIEW)
        await self._log_progress(
            ticket_id,
            "coding",
            f"Coding phase complete — {len(results)} subtask(s) processed",
            {"branch": branch_name},
        )
        return results

    # ── Phase 3: Review ──────────────────────────────────────────────

    async def run_review_phase(self, ticket_id: uuid.UUID) -> SecurityReport:
        """Run parallel AI reviews (security, quality) on the generated code.

        Steps:
        1. Get the diff between the feature branch and main.
        2. Run security analysis (AI + SAST).
        3. Log findings and return the security report.
        """
        await self._log_progress(ticket_id, "review", "Starting AI review phase")
        ticket = await self._get_ticket(ticket_id)
        repo_path = self._repo_path(ticket.project_id)

        if not ticket.branch_name:
            raise ValueError(f"Ticket {ticket_id} has no branch_name set")

        # Get diff
        diff = await repo_manager.get_diff(repo_path, "main", ticket.branch_name)
        changed_files = await repo_manager.get_changed_files(
            repo_path,
            "main",
            ticket.branch_name,
        )

        # Read changed file contents for security analysis
        file_contents: dict[str, str] = {}
        for rel_path in changed_files[:20]:  # Limit to 20 files
            full_path = repo_path / rel_path
            if full_path.is_file():
                with contextlib.suppress(OSError):
                    file_contents[rel_path] = full_path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )[:5_000]

        report = await analyze_security(
            diff=diff,
            file_contents=file_contents,
            repo_path=repo_path,
            changed_files=changed_files,
            db=self._db,
            ticket_id=ticket.id,
        )

        await self._log_progress(
            ticket_id,
            "review",
            f"Review complete — {report.total_findings} finding(s)",
            {"severity": report.severity_counts},
        )
        return report

    # ── Phase 4: Testing ─────────────────────────────────────────────

    async def run_testing_phase(self, ticket_id: uuid.UUID) -> dict[str, Any]:
        """Trigger CI/CD, generate AI tests, and collect results.

        Steps:
        1. Generate AI test files.
        2. Commit tests to the feature branch.
        3. Trigger the build+test workflow via n8n.
        """
        await self._log_progress(ticket_id, "testing", "Starting testing phase")
        ticket = await self._get_ticket(ticket_id)
        repo_path = self._repo_path(ticket.project_id)

        if not ticket.branch_name:
            raise ValueError(f"Ticket {ticket_id} has no branch_name set")

        # Get diff for test generation
        diff = await repo_manager.get_diff(repo_path, "main", ticket.branch_name)

        # Detect primary language from changed files
        changed = await repo_manager.get_changed_files(repo_path, "main", ticket.branch_name)
        language = _detect_language(changed)

        # Generate AI tests
        test_files: list[TestFile] = []
        try:
            test_files = await generate_tests(
                diff=diff,
                ticket_description=ticket.description or ticket.title,
                language=language,
                db=self._db,
                ticket_id=ticket.id,
            )
        except Exception as exc:
            logger.error("Test generation failed for ticket %s: %s", ticket_id, exc)

        # Write test files and commit
        if test_files:
            await repo_manager.checkout_branch(repo_path, ticket.branch_name)
            for tf in test_files:
                target = repo_path / tf.file_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(tf.content, encoding="utf-8")

            test_paths = [tf.file_path for tf in test_files]
            await repo_manager.commit_changes(
                repo_path=repo_path,
                message=f"test: add AI-generated tests for #{ticket.ticket_number}",
                files=test_paths,
            )

        # Trigger CI/CD
        ci_result = await trigger_workflow(
            "build_test",
            {
                "ticket_id": str(ticket.id),
                "project_id": str(ticket.project_id),
                "branch_name": ticket.branch_name,
            },
        )

        summary = {
            "test_files_generated": len(test_files),
            "test_types": list({tf.test_type for tf in test_files}),
            "ci_triggered": ci_result.get("status") != "error",
        }

        await self._log_progress(ticket_id, "testing", "Testing phase complete", summary)
        return summary

    # ── Phase 5: Deployment ──────────────────────────────────────────

    async def run_deploy_phase(
        self,
        ticket_id: uuid.UUID,
        environment: str = "staging",
    ) -> dict[str, Any]:
        """Deploy to staging or trigger canary production deploy.

        Parameters
        ----------
        environment:
            ``"staging"`` or ``"production"``.
        """
        await self._log_progress(ticket_id, "deploy", f"Starting deploy to {environment}")
        ticket = await self._get_ticket(ticket_id)

        if not ticket.branch_name:
            raise ValueError(f"Ticket {ticket_id} has no branch_name set")

        if environment == "production":
            # Canary deploy via n8n
            deploy_result = await trigger_workflow(
                "deploy_canary",
                {
                    "ticket_id": str(ticket.id),
                    "project_id": str(ticket.project_id),
                    "branch_name": ticket.branch_name,
                    "environment": "production",
                    "strategy": "canary",
                },
            )
            await self._update_ticket_column(ticket, ColumnName.PRODUCTION)
        else:
            # Staging deploy
            deploy_result = await trigger_workflow(
                "build_test",
                {
                    "ticket_id": str(ticket.id),
                    "project_id": str(ticket.project_id),
                    "branch_name": ticket.branch_name,
                    "environment": "staging",
                },
            )
            await self._update_ticket_column(ticket, ColumnName.STAGING)

        result = {
            "environment": environment,
            "branch": ticket.branch_name,
            "deploy_status": deploy_result.get("status", "unknown"),
        }

        await self._log_progress(ticket_id, "deploy", f"Deploy to {environment} initiated", result)
        return result


# ── Helpers ──────────────────────────────────────────────────────────────


def _detect_language(changed_files: list[str]) -> str:
    """Heuristically detect the primary language from file extensions."""
    ext_counts: dict[str, int] = {}
    for f in changed_files:
        suffix = Path(f).suffix.lower()
        if suffix:
            ext_counts[suffix] = ext_counts.get(suffix, 0) + 1

    ext_to_lang = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".rb": "ruby",
    }

    if not ext_counts:
        return "python"

    top_ext = max(ext_counts, key=ext_counts.get)  # type: ignore[arg-type]
    return ext_to_lang.get(top_ext, "python")
