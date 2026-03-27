"""Tests for app.agents.review_agent — parsing, deduplication, review orchestration."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.base import AgentResponse
from app.agents.review_agent import (
    AgentReview,
    InlineComment,
    ReviewResult,
    _deduplicate_comments,
    _parse_review_response,
    review_code,
    review_result_to_json,
)

# ---------------------------------------------------------------------------
# _parse_review_response
# ---------------------------------------------------------------------------


def test_parse_review_response_valid_json():
    payload = json.dumps(
        {
            "comments": [
                {"file": "a.py", "line": 10, "comment": "fix this", "severity": "warning"}
            ],
            "summary": "Looks okay.",
        }
    )
    comments, summary = _parse_review_response(payload)
    assert len(comments) == 1
    assert comments[0].file == "a.py"
    assert comments[0].line == 10
    assert comments[0].severity == "warning"
    assert summary == "Looks okay."


def test_parse_review_response_markdown_fences():
    payload = (
        "```json\n"
        + json.dumps(
            {
                "comments": [
                    {"file": "b.py", "line": 5, "comment": "issue", "severity": "critical"}
                ],
                "summary": "Bad.",
            }
        )
        + "\n```"
    )
    comments, summary = _parse_review_response(payload)
    assert len(comments) == 1
    assert comments[0].severity == "critical"
    assert summary == "Bad."


def test_parse_review_response_invalid_json():
    comments, summary = _parse_review_response("This is not JSON at all")
    assert comments == []
    assert summary == "This is not JSON at all"


def test_parse_review_response_invalid_severity_normalized():
    payload = json.dumps(
        {
            "comments": [{"file": "c.py", "line": 1, "comment": "hmm", "severity": "blocker"}],
            "summary": "",
        }
    )
    comments, _ = _parse_review_response(payload)
    assert len(comments) == 1
    assert comments[0].severity == "suggestion"  # normalised from unknown


# ---------------------------------------------------------------------------
# _deduplicate_comments
# ---------------------------------------------------------------------------


def test_deduplicate_same_file_line_keeps_higher_severity():
    c1 = InlineComment(file="x.py", line=5, comment="some issue here", severity="warning")
    c2 = InlineComment(file="x.py", line=5, comment="some issue here", severity="critical")
    result = _deduplicate_comments([c1, c2])
    # The critical one should survive
    severities = [c.severity for c in result if c.file == "x.py" and c.line == 5]
    assert "critical" in severities


def test_deduplicate_different_comments_kept():
    c1 = InlineComment(file="a.py", line=1, comment="alpha issue", severity="warning")
    c2 = InlineComment(file="b.py", line=2, comment="beta issue", severity="style")
    result = _deduplicate_comments([c1, c2])
    assert len(result) == 2


# ---------------------------------------------------------------------------
# review_code
# ---------------------------------------------------------------------------


def _fake_agent_response(content: str) -> AgentResponse:
    return AgentResponse(
        content=content,
        model_id="fake-model",
        prompt_tokens=100,
        completion_tokens=50,
        cost_usd=0.01,
        latency_ms=500,
        metadata={},
    )


@pytest.mark.asyncio
@patch("app.agents.review_agent.CodexAgent", side_effect=ValueError("no key"))
@patch("app.agents.review_agent.ClaudeAgent", side_effect=ValueError("no key"))
async def test_review_code_no_agents_available(mock_claude, mock_codex):
    result = await review_code(diff="diff", ticket_description="desc")
    assert "No AI agents available" in result.summary
    assert result.comments == []


@pytest.mark.asyncio
@patch("app.agents.review_agent.CodexAgent", side_effect=ValueError("no key"))
@patch("app.agents.review_agent.ClaudeAgent")
async def test_review_code_single_agent(mock_claude_cls, mock_codex_cls):
    review_json = json.dumps(
        {
            "comments": [{"file": "f.py", "line": 3, "comment": "nit", "severity": "style"}],
            "summary": "Fine.",
        }
    )
    mock_instance = mock_claude_cls.return_value
    mock_instance.name = "claude"
    mock_instance.invoke = AsyncMock(return_value=_fake_agent_response(review_json))

    result = await review_code(diff="some diff", ticket_description="ticket")
    assert len(result.comments) == 1
    assert result.comments[0].severity == "style"
    assert result.total_cost_usd > 0
    assert len(result.agent_reviews) == 1


# ---------------------------------------------------------------------------
# review_result_to_json
# ---------------------------------------------------------------------------


def test_review_result_to_json():
    comment = InlineComment(file="z.py", line=42, comment="fix", severity="warning")
    agent_review = AgentReview(
        agent_name="claude",
        model_id="claude-sonnet-4-6",
        comments=[comment],
        summary="ok",
        cost_usd=0.02,
        latency_ms=300,
    )
    result = ReviewResult(
        comments=[comment],
        summary="overall",
        agent_reviews=[agent_review],
        total_cost_usd=0.02,
    )
    data = review_result_to_json(result)
    assert data["summary"] == "overall"
    assert data["total_cost_usd"] == 0.02
    assert len(data["comments"]) == 1
    assert data["comments"][0]["file"] == "z.py"
    assert len(data["agent_reviews"]) == 1
    assert data["agent_reviews"][0]["comment_count"] == 1
