"""Meta-review agent — Layer 2 of the three-layer review architecture.

Three-layer review:
  Layer 1: Specialist AI agents (review_agent, security_agent) produce findings
  Layer 2: Meta-review agent consolidates, de-noises, and prioritises findings
  Layer 3: Human reviewer makes final decision

The meta-review agent acts as an AI-on-AI reviewer:
  - Takes raw findings from Layer 1 agents
  - Filters false positives and low-signal noise
  - Cross-references findings for consistency
  - Produces a consolidated verdict with confidence score
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentResponse, validate_output
from app.agents.claude_agent import ClaudeAgent
from app.agents.review_agent import InlineComment, ReviewResult

logger = logging.getLogger(__name__)

META_REVIEW_SYSTEM_PROMPT = """\
You are a senior staff engineer acting as a meta-reviewer. Your job is to review \
the output of other AI code review agents and produce a consolidated, high-quality \
review verdict.

You will receive:
1. The original code diff
2. Findings from multiple AI review agents (Layer 1)

Your responsibilities:
- **Filter false positives**: Remove findings that are incorrect or irrelevant
- **Consolidate duplicates**: Merge overlapping findings into single items
- **Validate severity**: Adjust severity ratings based on actual impact
- **Add context**: Note if findings miss important issues
- **Produce verdict**: Recommend approve, request_changes, or needs_discussion

Respond ONLY with valid JSON:
{
  "verdict": "approve" | "request_changes" | "needs_discussion",
  "confidence": 0.0 to 1.0,
  "consolidated_findings": [
    {
      "file": "...",
      "line": 1,
      "comment": "...",
      "severity": "critical|warning|suggestion|style",
      "original_agents": ["agent1", "agent2"],
      "false_positive": false
    }
  ],
  "filtered_out": [
    {"original_comment": "...", "reason": "false positive because..."}
  ],
  "summary": "Overall assessment...",
  "missed_issues": ["Any issues the original reviewers missed..."]
}
"""


# ── Pydantic output schema ────────────────────────────────────────────


class ConsolidatedFinding(BaseModel):
    file: str = ""
    line: int = 0
    comment: str = ""
    severity: str = Field(default="suggestion", pattern=r"^(critical|warning|suggestion|style)$")
    original_agents: list[str] = Field(default_factory=list)
    false_positive: bool = False


class FilteredFinding(BaseModel):
    original_comment: str = ""
    reason: str = ""


class MetaReviewOutput(BaseModel):
    verdict: str = Field(
        default="needs_discussion",
        pattern=r"^(approve|request_changes|needs_discussion)$",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    consolidated_findings: list[ConsolidatedFinding] = Field(default_factory=list)
    filtered_out: list[FilteredFinding] = Field(default_factory=list)
    summary: str = ""
    missed_issues: list[str] = Field(default_factory=list)


@dataclass
class MetaReviewResult:
    """Result from the meta-review (Layer 2)."""

    verdict: str  # approve | request_changes | needs_discussion
    confidence: float
    consolidated_comments: list[InlineComment] = field(default_factory=list)
    filtered_count: int = 0
    missed_issues: list[str] = field(default_factory=list)
    summary: str = ""
    cost_usd: float = 0.0
    latency_ms: int = 0


def _build_layer1_context(layer1_result: ReviewResult) -> str:
    """Format Layer 1 findings for the meta-reviewer."""
    sections = []

    for agent_review in layer1_result.agent_reviews:
        agent_section = f"## Agent: {agent_review.agent_name} (model: {agent_review.model_id})\n"
        agent_section += f"Summary: {agent_review.summary}\n\n"

        if agent_review.comments:
            agent_section += "Findings:\n"
            for c in agent_review.comments:
                agent_section += (
                    f"- [{c.severity}] {c.file}:{c.line} — {c.comment}\n"
                )
        else:
            agent_section += "No findings.\n"

        sections.append(agent_section)

    return "\n\n".join(sections)


def _parse_meta_review(content: str) -> MetaReviewOutput:
    """Parse meta-review JSON response."""
    try:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.index("\n")
            last_fence = cleaned.rfind("```")
            if last_fence > first_newline:
                cleaned = cleaned[first_newline + 1 : last_fence].strip()

        data = json.loads(cleaned)
        validated = validate_output(data, MetaReviewOutput)
        return MetaReviewOutput.model_validate(validated)
    except (json.JSONDecodeError, ValueError, Exception) as exc:
        logger.warning("Failed to parse meta-review JSON: %s", exc)
        return MetaReviewOutput(
            verdict="needs_discussion",
            confidence=0.0,
            summary=content.strip()[:500],
        )


async def run_meta_review(
    diff: str,
    layer1_result: ReviewResult,
    *,
    db: AsyncSession | None = None,
    ticket_id: uuid.UUID | None = None,
) -> MetaReviewResult:
    """Run Layer 2 meta-review on Layer 1 findings.

    Parameters
    ----------
    diff:
        The original code diff.
    layer1_result:
        The merged ReviewResult from Layer 1 agents.
    db:
        Optional database session for logging.
    ticket_id:
        Optional ticket ID for linking logs.

    Returns
    -------
    MetaReviewResult with consolidated verdict and findings.
    """
    layer1_context = _build_layer1_context(layer1_result)

    prompt = (
        f"Review the following Layer 1 AI review findings and produce "
        f"a consolidated meta-review.\n\n"
        f"## Original Diff\n```\n{diff[:30_000]}\n```\n\n"
        f"## Layer 1 Agent Findings\n{layer1_context}"
    )

    # Use Claude for meta-review (highest capability for reasoning)
    try:
        agent = ClaudeAgent()
    except (ValueError, Exception) as exc:
        logger.error("Claude agent unavailable for meta-review: %s", exc)
        # Fallback: pass through Layer 1 results without meta-review
        return MetaReviewResult(
            verdict=_infer_verdict(layer1_result),
            confidence=0.5,
            consolidated_comments=layer1_result.comments,
            summary=f"Meta-review unavailable ({exc}). Using Layer 1 results directly.",
            cost_usd=0.0,
        )

    try:
        response: AgentResponse = await agent.invoke(
            prompt=prompt,
            context="",
            system_prompt=META_REVIEW_SYSTEM_PROMPT,
            db=db,
            ticket_id=ticket_id,
            action_type="meta_review",
            temperature=0.1,
            max_tokens=8192,
        )

        output = _parse_meta_review(response.content)

        # Convert consolidated findings to InlineComment list
        consolidated = [
            InlineComment(
                file=f.file,
                line=f.line,
                comment=f.comment,
                severity=f.severity,
            )
            for f in output.consolidated_findings
            if not f.false_positive
        ]

        return MetaReviewResult(
            verdict=output.verdict,
            confidence=output.confidence,
            consolidated_comments=consolidated,
            filtered_count=len(output.filtered_out),
            missed_issues=output.missed_issues,
            summary=output.summary,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
        )

    except Exception as exc:
        logger.error("Meta-review failed: %s", exc)
        return MetaReviewResult(
            verdict=_infer_verdict(layer1_result),
            confidence=0.3,
            consolidated_comments=layer1_result.comments,
            summary=f"Meta-review error ({exc}). Using Layer 1 results directly.",
            cost_usd=0.0,
        )


def _infer_verdict(layer1_result: ReviewResult) -> str:
    """Infer a verdict from Layer 1 findings when meta-review is unavailable."""
    critical_count = sum(1 for c in layer1_result.comments if c.severity == "critical")
    warning_count = sum(1 for c in layer1_result.comments if c.severity == "warning")

    if critical_count > 0 or warning_count > 3:
        return "request_changes"
    return "approve"


def meta_review_result_to_json(result: MetaReviewResult) -> dict[str, Any]:
    """Serialize a MetaReviewResult to a JSON-compatible dict."""
    return {
        "verdict": result.verdict,
        "confidence": result.confidence,
        "consolidated_comments": [
            {
                "file": c.file,
                "line": c.line,
                "comment": c.comment,
                "severity": c.severity,
            }
            for c in result.consolidated_comments
        ],
        "filtered_count": result.filtered_count,
        "missed_issues": result.missed_issues,
        "summary": result.summary,
        "cost_usd": result.cost_usd,
        "latency_ms": result.latency_ms,
    }
