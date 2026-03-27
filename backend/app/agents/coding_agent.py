"""Coding Agent — generates code for individual subtasks within a plan."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.router import execute_with_fallback, route_task
from app.context.engine import ContextEngine
from app.git import repo_manager
from app.models.ai_code_generation import AiCodeGeneration, CodeGenStatus
from app.models.ai_plan import AiPlan

logger = logging.getLogger(__name__)

_MAX_LINT_RETRIES = 3

# ── Prompt templates ─────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert software engineer.  Generate production-quality code changes
to implement the described subtask.

Your output MUST be valid JSON with exactly these keys:
  - "files": an array of file-change objects.

Each file-change object MUST have:
  - "path": relative file path from the repository root.
  - "action": one of "create", "modify", "delete".
  - "content": the complete file content (for "create" or "modify").
    For "delete", set content to null.
  - "diff_summary": a one-line description of the change.

Rules:
  - Write clean, well-documented, production-ready code.
  - Follow existing project conventions and style.
  - Include proper error handling, type hints, and docstrings.
  - Do NOT include explanations outside the JSON.
  - Respond ONLY with the JSON object.\
"""

_USER_PROMPT_TEMPLATE = """\
## Plan Overview
{plan_markdown}

## Current Subtask ({subtask_index}/{total_subtasks})
**Title:** {subtask_title}
**Description:** {subtask_description}
**Affected Files:** {affected_files}

## Dependencies Completed
{completed_context}

## Relevant Code
{code_context}

---

Generate the code changes for this subtask.\
"""

_LINT_FIX_PROMPT = """\
The code you generated has lint errors.  Fix the following issues and return
the corrected file changes in the same JSON format.

## Lint Errors
{lint_errors}

## Original File Changes
{original_files_json}

Respond ONLY with the corrected JSON object.\
"""


@dataclass
class FileChange:
    """A single file change produced by the coding agent."""

    path: str
    action: str  # "create" | "modify" | "delete"
    content: str | None = None
    diff_summary: str = ""


@dataclass
class CodeGenResult:
    """Outcome of a single subtask code-generation run."""

    files_changed: list[FileChange] = field(default_factory=list)
    commit_sha: str | None = None
    lint_passed: bool = False
    retry_count: int = 0
    agent_used: str = ""


# ── Lint runner ──────────────────────────────────────────────────────────


async def _run_lint(file_path: str, repo_path: Path) -> tuple[bool, str]:
    """Run the appropriate linter for *file_path* and return (passed, errors)."""
    full_path = repo_path / file_path
    suffix = full_path.suffix.lower()

    if suffix == ".py":
        cmd = ["ruff", "check", "--fix", str(full_path)]
    elif suffix in {".js", ".jsx", ".ts", ".tsx"}:
        cmd = ["npx", "eslint", "--fix", str(full_path)]
    else:
        return True, ""

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
        output = (stdout or b"").decode("utf-8", errors="replace")
        err_output = (stderr or b"").decode("utf-8", errors="replace")
        combined = f"{output}\n{err_output}".strip()

        if proc.returncode == 0:
            return True, ""
        return False, combined

    except FileNotFoundError:
        logger.warning("Linter not found for %s — skipping lint check", file_path)
        return True, ""
    except TimeoutError:
        logger.warning("Lint timed out for %s", file_path)
        return False, "Lint command timed out"


# ── File application ─────────────────────────────────────────────────────


def _apply_file_changes(changes: list[FileChange], repo_path: Path) -> list[str]:
    """Write file changes to the working tree.  Returns list of affected paths."""
    paths: list[str] = []
    for change in changes:
        target = repo_path / change.path
        if change.action == "delete":
            if target.exists():
                target.unlink()
                logger.info("Deleted %s", change.path)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content or "", encoding="utf-8")
            logger.info("%s %s", change.action.capitalize(), change.path)
        paths.append(change.path)
    return paths


def _parse_code_output(raw: str) -> list[FileChange]:
    """Parse JSON output from the coding agent into FileChange objects."""
    content = raw.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent returned invalid JSON: {exc}") from exc

    files_raw = data.get("files", [])
    changes: list[FileChange] = []
    for f in files_raw:
        changes.append(
            FileChange(
                path=f["path"],
                action=f.get("action", "modify"),
                content=f.get("content"),
                diff_summary=f.get("diff_summary", ""),
            )
        )
    return changes


# ── Core logic ───────────────────────────────────────────────────────────


async def generate_code(
    subtask: dict[str, Any],
    subtask_index: int,
    plan: AiPlan,
    project_id: uuid.UUID,
    context_engine: ContextEngine,
    repo_path: str | Path,
    db: AsyncSession,
    ticket_id: uuid.UUID,
    branch_name: str,
) -> CodeGenResult:
    """Generate code for a single subtask.

    Steps
    -----
    1. Gather relevant code context from the vector store.
    2. Build a prompt including plan overview, subtask details, and code context.
    3. Route to the appropriate agent (using agent_hint from the plan).
    4. Parse JSON output into file changes.
    5. Apply changes to the working tree.
    6. Lint the changed files; if lint fails, feed errors back and retry (up to 3 times).
    7. Commit changes and record the result.
    """
    repo = Path(repo_path)
    result = CodeGenResult(agent_used="")

    # 1. Gather context
    search_query = f"{subtask.get('title', '')} {subtask.get('description', '')}"
    code_context = await context_engine.get_context_for_ticket(
        project_id=project_id,
        ticket_description=search_query,
    )

    # Build info about completed dependencies
    completed_context = "No prior subtasks completed yet."
    deps = subtask.get("dependencies", [])
    if deps:
        completed_parts = []
        for dep_idx in deps:
            if dep_idx < len(plan.subtasks):
                dep = plan.subtasks[dep_idx]
                completed_parts.append(f"- Subtask {dep_idx}: {dep.get('title', 'N/A')}")
        if completed_parts:
            completed_context = "\n".join(completed_parts)

    # 2. Build prompt
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        plan_markdown=plan.plan_markdown[:4000],
        subtask_index=subtask_index + 1,
        total_subtasks=len(plan.subtasks),
        subtask_title=subtask.get("title", "Untitled"),
        subtask_description=subtask.get("description", ""),
        affected_files=", ".join(subtask.get("affected_files", [])),
        completed_context=completed_context,
        code_context=code_context,
    )

    # 3. Route to agent (respect agent_hint if available)
    agent_hint = subtask.get("agent_hint")
    agent = route_task("coding")
    model_override: str | None = None
    if agent_hint and agent_hint != agent.name:
        # Try to use the hinted agent
        try:
            from app.agents.router import _get_agent

            agent = _get_agent(agent_hint)
        except (ValueError, Exception):
            logger.info(
                "Hint agent '%s' unavailable; using routed agent '%s'",
                agent_hint,
                agent.name,
            )

    result.agent_used = agent.name

    # 4. Generate code
    response = await execute_with_fallback(
        agent,
        prompt=user_prompt,
        context="",
        system_prompt=_SYSTEM_PROMPT,
        model_id=model_override,
        temperature=0.15,
        max_tokens=8192,
        db=db,
        ticket_id=ticket_id,
        action_type="coding",
    )

    changes = _parse_code_output(response.content)

    # 5. Apply changes
    _apply_file_changes(changes, repo)

    # 6. Lint loop with self-correction
    all_lint_passed = True
    for retry in range(_MAX_LINT_RETRIES):
        lint_errors: list[str] = []
        for change in changes:
            if change.action == "delete":
                continue
            passed, errors = await _run_lint(change.path, repo)
            if not passed:
                lint_errors.append(f"File: {change.path}\n{errors}")

        if not lint_errors:
            all_lint_passed = True
            break

        all_lint_passed = False
        result.retry_count = retry + 1
        logger.warning(
            "Lint failed for subtask %d (attempt %d/%d): %d file(s) with errors",
            subtask_index,
            retry + 1,
            _MAX_LINT_RETRIES,
            len(lint_errors),
        )

        if retry + 1 >= _MAX_LINT_RETRIES:
            break

        # Self-correction: feed lint errors back to the agent
        fix_prompt = _LINT_FIX_PROMPT.format(
            lint_errors="\n---\n".join(lint_errors),
            original_files_json=json.dumps(
                [
                    {
                        "path": c.path,
                        "action": c.action,
                        "content": c.content,
                        "diff_summary": c.diff_summary,
                    }
                    for c in changes
                ],
                indent=2,
            ),
        )

        fix_response = await execute_with_fallback(
            agent,
            prompt=fix_prompt,
            context="",
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=8192,
            db=db,
            ticket_id=ticket_id,
            action_type="coding_lint_fix",
        )

        changes = _parse_code_output(fix_response.content)
        _apply_file_changes(changes, repo)

    result.lint_passed = all_lint_passed

    # 7. Commit changes
    changed_paths = [c.path for c in changes]
    commit_msg = f"ai({subtask_index}): {subtask.get('title', 'implement subtask')}"
    try:
        git_result = await repo_manager.commit_changes(
            repo_path=repo,
            message=commit_msg,
            files=changed_paths,
        )
        # Extract commit SHA from git output
        sha_line = git_result.stdout.strip().splitlines()[0] if git_result.stdout else ""
        # Typical format: "[branch abc1234] commit message"
        if " " in sha_line:
            sha_part = sha_line.split("]")[0].split()[-1] if "]" in sha_line else ""
            result.commit_sha = sha_part or None
    except Exception as exc:
        logger.error("Failed to commit subtask %d changes: %s", subtask_index, exc)

    result.files_changed = changes

    # 8. Persist code generation record
    code_gen = AiCodeGeneration(
        ticket_id=ticket_id,
        plan_id=plan.id,
        subtask_index=subtask_index,
        agent_name=result.agent_used,
        branch_name=branch_name,
        files_changed=[
            {"path": c.path, "action": c.action, "diff_summary": c.diff_summary} for c in changes
        ],
        commit_sha=result.commit_sha,
        status=CodeGenStatus.COMPLETED if all_lint_passed else CodeGenStatus.RETRY,
        retry_count=result.retry_count,
        lint_passed=result.lint_passed,
        test_passed=False,  # Tests run separately
    )
    db.add(code_gen)
    await db.flush()

    logger.info(
        "Code generation for subtask %d complete — %d files, lint=%s, retries=%d, agent=%s",
        subtask_index,
        len(changes),
        result.lint_passed,
        result.retry_count,
        result.agent_used,
    )
    return result
