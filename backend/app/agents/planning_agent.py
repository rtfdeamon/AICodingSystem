"""Planning Agent — generates structured implementation plans from tickets."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentResponse
from app.agents.router import execute_with_fallback, route_task
from app.context.engine import ContextEngine
from app.models.ai_plan import AiPlan, PlanStatus
from app.models.ticket import Ticket

logger = logging.getLogger(__name__)

# ── Prompt templates ─────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert software architect and technical lead.  Your job is to
produce a detailed, actionable implementation plan for a development ticket.

Your output MUST be valid JSON with exactly these top-level keys:
  - "plan_markdown": a Markdown string with the full plan description.
  - "subtasks": an ordered JSON array of subtask objects.
  - "file_list": a flat JSON array of all file paths that will be created or modified.

Each subtask object MUST have these keys:
  - "title": short imperative title (e.g. "Add user validation middleware").
  - "description": 2-4 sentence description of what to do and why.
  - "affected_files": list of file paths this subtask touches.
  - "agent_hint": one of "claude", "codex", "gemini" — which AI agent is best suited.
  - "estimated_complexity": one of "low", "medium", "high".
  - "dependencies": list of zero-based subtask indices this depends on (e.g. [0, 1]).

Respond ONLY with the JSON object.  No preamble, no code fences, no explanation.\
"""

_USER_PROMPT_TEMPLATE = """\
## Ticket
**Title:** {title}
**Description:** {description}

## Acceptance Criteria
{acceptance_criteria}

## Relevant Code Context
{code_context}

## Project Structure Hints
Repository language mix and key directories are provided in the context above.

---

Generate a comprehensive implementation plan.\
"""


@dataclass
class PlanSubtask:
    """A single subtask within an implementation plan."""

    title: str
    description: str
    affected_files: list[str] = field(default_factory=list)
    agent_hint: str = "claude"
    estimated_complexity: str = "medium"
    dependencies: list[int] = field(default_factory=list)


@dataclass
class GeneratedPlan:
    """Result of a planning agent run."""

    plan_markdown: str
    subtasks: list[PlanSubtask]
    file_list: list[str]
    agent_response: AgentResponse


# ── Core logic ───────────────────────────────────────────────────────────


def _parse_plan_output(raw_content: str) -> dict[str, Any]:
    """Parse the agent's JSON output, stripping code fences if present."""
    content = raw_content.strip()
    # Remove markdown code fences if the model wrapped the output.
    if content.startswith("```"):
        # Strip leading ```json or ``` and trailing ```
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    try:
        return json.loads(content)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse plan JSON: %s\nRaw content:\n%s", exc, content[:2000])
        raise ValueError(f"Agent returned invalid JSON: {exc}") from exc


async def generate_plan(
    ticket: Ticket,
    project_id: uuid.UUID,
    context_engine: ContextEngine,
    db: AsyncSession,
) -> AiPlan:
    """Generate an AI implementation plan for a ticket.

    Steps
    -----
    1. Retrieve relevant code context via the context engine.
    2. Build a rich prompt from the ticket details and code context.
    3. Call Claude (preferred for planning) with structured output instructions.
    4. Parse the JSON response into subtasks.
    5. Persist the plan in the ``ai_plans`` table.
    6. Return the saved :class:`AiPlan` row.
    """
    # 1. Gather code context
    code_context = await context_engine.get_context_for_ticket(
        project_id=project_id,
        ticket_description=ticket.description or ticket.title,
        acceptance_criteria=ticket.acceptance_criteria,
    )

    # 2. Build prompt
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        title=ticket.title,
        description=ticket.description or "(no description)",
        acceptance_criteria=ticket.acceptance_criteria or "(none specified)",
        code_context=code_context,
    )

    # 3. Call AI agent — prefer Claude Opus for planning quality
    agent = route_task("planning")
    response = await execute_with_fallback(
        agent,
        prompt=user_prompt,
        context="",
        system_prompt=_SYSTEM_PROMPT,
        model_id="claude-opus-4-6",
        temperature=0.3,
        max_tokens=8192,
        db=db,
        ticket_id=ticket.id,
        action_type="planning",
    )

    # 4. Parse structured output
    parsed = _parse_plan_output(response.content)

    plan_markdown = parsed.get("plan_markdown", "")
    raw_subtasks = parsed.get("subtasks", [])
    file_list = parsed.get("file_list", [])

    subtasks_json: list[dict[str, Any]] = []
    for st in raw_subtasks:
        subtasks_json.append(
            {
                "title": st.get("title", "Untitled subtask"),
                "description": st.get("description", ""),
                "affected_files": st.get("affected_files", []),
                "agent_hint": st.get("agent_hint", "claude"),
                "estimated_complexity": st.get("estimated_complexity", "medium"),
                "dependencies": st.get("dependencies", []),
            }
        )

    # 5. Determine the next version number for this ticket
    version_result = await db.execute(
        select(func.coalesce(func.max(AiPlan.version), 0)).where(
            AiPlan.ticket_id == ticket.id,
        )
    )
    current_max_version: int = version_result.scalar_one()

    # Mark any prior pending plans as superseded
    from sqlalchemy import update

    await db.execute(
        update(AiPlan)
        .where(AiPlan.ticket_id == ticket.id, AiPlan.status == PlanStatus.PENDING)
        .values(status=PlanStatus.SUPERSEDED)
    )

    plan = AiPlan(
        ticket_id=ticket.id,
        version=current_max_version + 1,
        agent_name=agent.name,
        plan_markdown=plan_markdown,
        subtasks=subtasks_json,
        file_list=file_list,
        status=PlanStatus.PENDING,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        cost_usd=response.cost_usd,
        latency_ms=response.latency_ms,
    )
    db.add(plan)
    await db.flush()
    await db.refresh(plan)

    logger.info(
        "Generated plan v%d for ticket %s — %d subtasks, %d files, $%.4f",
        plan.version,
        ticket.id,
        len(subtasks_json),
        len(file_list),
        plan.cost_usd,
    )
    return plan
