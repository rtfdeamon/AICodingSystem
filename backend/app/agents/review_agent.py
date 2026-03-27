"""AI Code Review agent — runs Claude and Codex in parallel for code review."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentResponse
from app.agents.claude_agent import ClaudeAgent
from app.agents.codex_agent import CodexAgent

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """\
You are an expert code reviewer. Analyze the provided diff and produce a structured \
JSON review. For each issue found, include:
- "file": the file path
- "line": the line number in the diff (integer)
- "comment": a clear explanation of the issue and how to fix it
- "severity": one of "critical", "warning", "suggestion", "style"

Also produce a short "summary" of the overall code quality.

Respond ONLY with valid JSON in this format:
{
  "comments": [{"file": "...", "line": 1, "comment": "...", "severity": "..."}],
  "summary": "Overall assessment..."
}
"""


@dataclass
class InlineComment:
    """A single inline review comment."""

    file: str
    line: int
    comment: str
    severity: str  # critical | warning | suggestion | style


@dataclass
class AgentReview:
    """Review output from a single AI agent."""

    agent_name: str
    model_id: str
    comments: list[InlineComment] = field(default_factory=list)
    summary: str = ""
    cost_usd: float = 0.0
    latency_ms: int = 0
    log_id: uuid.UUID | None = None


@dataclass
class ReviewResult:
    """Merged review result from all AI agents."""

    comments: list[InlineComment] = field(default_factory=list)
    summary: str = ""
    agent_reviews: list[AgentReview] = field(default_factory=list)
    total_cost_usd: float = 0.0


def _parse_review_response(content: str) -> tuple[list[InlineComment], str]:
    """Parse an agent's JSON response into inline comments and summary."""
    try:
        # Strip markdown code fences if present
        cleaned = content.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.index("\n")
            last_fence = cleaned.rfind("```")
            if last_fence > first_newline:
                cleaned = cleaned[first_newline + 1 : last_fence].strip()

        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse review JSON; treating response as plain text summary")
        return [], content.strip()[:500]

    comments: list[InlineComment] = []
    raw_comments = data.get("comments", [])
    for raw in raw_comments:
        if isinstance(raw, dict) and all(k in raw for k in ("file", "line", "comment", "severity")):
            severity = raw["severity"]
            if severity not in ("critical", "warning", "suggestion", "style"):
                severity = "suggestion"
            comments.append(
                InlineComment(
                    file=str(raw["file"]),
                    line=int(raw.get("line", 0)),
                    comment=str(raw["comment"]),
                    severity=severity,
                )
            )
    summary = data.get("summary", "")
    return comments, summary


def _deduplicate_comments(comments: list[InlineComment]) -> list[InlineComment]:
    """Remove duplicate comments targeting the same file+line with similar text."""
    seen: dict[tuple[str, int], InlineComment] = {}
    result: list[InlineComment] = []

    for c in comments:
        key = (c.file, c.line)
        if key in seen:
            existing = seen[key]
            # Keep the higher severity comment
            severity_rank = {"critical": 0, "warning": 1, "suggestion": 2, "style": 3}
            if severity_rank.get(c.severity, 99) < severity_rank.get(existing.severity, 99):
                seen[key] = c
                result = [r for r in result if (r.file, r.line) != key]
                result.append(c)
            # Check for near-duplicate text (>70% overlap by words)
            existing_words = set(existing.comment.lower().split())
            new_words = set(c.comment.lower().split())
            if existing_words and new_words:
                overlap = len(existing_words & new_words) / max(len(existing_words), len(new_words))
                if overlap < 0.7:
                    # Different enough to keep both — append with unique key
                    result.append(c)
        else:
            seen[key] = c
            result.append(c)

    return result


async def _run_single_agent(
    agent: ClaudeAgent | CodexAgent,
    prompt: str,
    context: str,
    db: AsyncSession | None,
    ticket_id: uuid.UUID | None,
) -> AgentReview:
    """Run a single agent review and return structured result."""
    try:
        response: AgentResponse = await agent.invoke(
            prompt=prompt,
            context=context,
            system_prompt=REVIEW_SYSTEM_PROMPT,
            db=db,
            ticket_id=ticket_id,
            action_type="code_review",
            temperature=0.1,
            max_tokens=8192,
        )
        comments, summary = _parse_review_response(response.content)
        return AgentReview(
            agent_name=agent.name,
            model_id=response.model_id,
            comments=comments,
            summary=summary,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
        )
    except Exception as exc:
        logger.error("Agent '%s' failed during code review: %s", agent.name, exc)
        return AgentReview(
            agent_name=agent.name,
            model_id="unknown",
            summary=f"Agent failed: {exc}",
        )


async def review_code(
    diff: str,
    ticket_description: str,
    project_context: str = "",
    *,
    db: AsyncSession | None = None,
    ticket_id: uuid.UUID | None = None,
) -> ReviewResult:
    """Run AI code review using Claude and Codex in parallel.

    Parameters
    ----------
    diff:
        The git diff to review.
    ticket_description:
        The ticket description and acceptance criteria for context.
    project_context:
        Additional project-level context (coding standards, architecture notes).
    db:
        Optional database session for logging AI calls.
    ticket_id:
        Optional ticket ID for linking logs.

    Returns
    -------
    ReviewResult with merged, deduplicated comments and per-agent detail.
    """
    prompt = (
        f"Review the following code diff for a ticket described as:\n"
        f"{ticket_description}\n\n"
        f"Diff:\n```\n{diff[:50_000]}\n```"
    )
    context = project_context[:10_000] if project_context else ""

    # Initialize agents — gracefully handle missing API keys
    agents: list[ClaudeAgent | CodexAgent] = []
    try:
        agents.append(ClaudeAgent())
    except (ValueError, Exception) as exc:
        logger.warning("Claude agent unavailable for review: %s", exc)
    try:
        agents.append(CodexAgent())
    except (ValueError, Exception) as exc:
        logger.warning("Codex agent unavailable for review: %s", exc)

    if not agents:
        logger.error("No AI agents available for code review")
        return ReviewResult(summary="No AI agents available. Configure API keys.")

    # Run all agents in parallel
    tasks = [_run_single_agent(agent, prompt, context, db, ticket_id) for agent in agents]
    agent_reviews: list[AgentReview] = await asyncio.gather(*tasks)

    # Merge all comments and deduplicate
    all_comments: list[InlineComment] = []
    summaries: list[str] = []
    total_cost = 0.0

    for review in agent_reviews:
        all_comments.extend(review.comments)
        if review.summary:
            summaries.append(f"[{review.agent_name}] {review.summary}")
        total_cost += review.cost_usd

    deduplicated = _deduplicate_comments(all_comments)

    # Sort by severity (critical first) then by file and line
    severity_order = {"critical": 0, "warning": 1, "suggestion": 2, "style": 3}
    deduplicated.sort(key=lambda c: (severity_order.get(c.severity, 99), c.file, c.line))

    merged_summary = "\n\n".join(summaries) if summaries else "No summary available."

    return ReviewResult(
        comments=deduplicated,
        summary=merged_summary,
        agent_reviews=agent_reviews,
        total_cost_usd=total_cost,
    )


def review_result_to_json(result: ReviewResult) -> dict[str, Any]:
    """Serialize a ReviewResult to a JSON-compatible dict for API responses."""
    return {
        "comments": [
            {
                "file": c.file,
                "line": c.line,
                "comment": c.comment,
                "severity": c.severity,
            }
            for c in result.comments
        ],
        "summary": result.summary,
        "total_cost_usd": result.total_cost_usd,
        "agent_reviews": [
            {
                "agent_name": ar.agent_name,
                "model_id": ar.model_id,
                "summary": ar.summary,
                "comment_count": len(ar.comments),
                "cost_usd": ar.cost_usd,
                "latency_ms": ar.latency_ms,
            }
            for ar in result.agent_reviews
        ],
    }
