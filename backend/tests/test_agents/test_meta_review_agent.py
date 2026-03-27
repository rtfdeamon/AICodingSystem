"""Tests for app.agents.meta_review_agent — Layer 2 three-layer review."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.base import AgentResponse
from app.agents.meta_review_agent import (
    MetaReviewOutput,
    MetaReviewResult,
    _build_layer1_context,
    _infer_verdict,
    _parse_meta_review,
    meta_review_result_to_json,
    run_meta_review,
)
from app.agents.review_agent import AgentReview, InlineComment, ReviewResult

# ---------------------------------------------------------------------------
# _build_layer1_context
# ---------------------------------------------------------------------------


def test_build_layer1_context_single_agent():
    review = ReviewResult(
        comments=[InlineComment("a.py", 10, "fix this", "warning")],
        summary="Overall okay",
        agent_reviews=[
            AgentReview(
                agent_name="claude",
                model_id="claude-sonnet-4-6",
                comments=[InlineComment("a.py", 10, "fix this", "warning")],
                summary="Minor issues",
            )
        ],
    )
    ctx = _build_layer1_context(review)
    assert "claude" in ctx
    assert "a.py:10" in ctx
    assert "fix this" in ctx
    assert "Minor issues" in ctx


def test_build_layer1_context_multiple_agents():
    review = ReviewResult(
        agent_reviews=[
            AgentReview(
                agent_name="claude",
                model_id="claude-sonnet-4-6",
                comments=[InlineComment("a.py", 1, "issue1", "critical")],
                summary="Bad code",
            ),
            AgentReview(
                agent_name="codex",
                model_id="gpt-4o",
                comments=[],
                summary="Looks fine",
            ),
        ],
    )
    ctx = _build_layer1_context(review)
    assert "claude" in ctx
    assert "codex" in ctx
    assert "No findings" in ctx


def test_build_layer1_context_empty_reviews():
    review = ReviewResult(agent_reviews=[])
    ctx = _build_layer1_context(review)
    assert ctx == ""


# ---------------------------------------------------------------------------
# _parse_meta_review
# ---------------------------------------------------------------------------


def test_parse_meta_review_valid_json():
    payload = json.dumps({
        "verdict": "approve",
        "confidence": 0.9,
        "consolidated_findings": [
            {
                "file": "a.py",
                "line": 10,
                "comment": "real issue",
                "severity": "warning",
                "original_agents": ["claude"],
                "false_positive": False,
            }
        ],
        "filtered_out": [
            {"original_comment": "noise", "reason": "false positive"}
        ],
        "summary": "Code is good",
        "missed_issues": ["Missing error handling in function X"],
    })
    result = _parse_meta_review(payload)
    assert result.verdict == "approve"
    assert result.confidence == 0.9
    assert len(result.consolidated_findings) == 1
    assert len(result.filtered_out) == 1
    assert result.summary == "Code is good"
    assert len(result.missed_issues) == 1


def test_parse_meta_review_with_code_fences():
    inner = json.dumps({
        "verdict": "request_changes",
        "confidence": 0.7,
        "consolidated_findings": [],
        "filtered_out": [],
        "summary": "Changes needed",
        "missed_issues": [],
    })
    payload = f"```json\n{inner}\n```"
    result = _parse_meta_review(payload)
    assert result.verdict == "request_changes"
    assert result.confidence == 0.7


def test_parse_meta_review_invalid_json():
    result = _parse_meta_review("This is not JSON")
    assert result.verdict == "needs_discussion"
    assert result.confidence == 0.0
    assert "This is not JSON" in result.summary


def test_parse_meta_review_partial_fields():
    payload = json.dumps({"verdict": "approve", "summary": "All good"})
    result = _parse_meta_review(payload)
    assert result.verdict == "approve"
    assert result.summary == "All good"
    assert result.consolidated_findings == []


# ---------------------------------------------------------------------------
# _infer_verdict
# ---------------------------------------------------------------------------


def test_infer_verdict_no_issues():
    review = ReviewResult(comments=[])
    assert _infer_verdict(review) == "approve"


def test_infer_verdict_critical():
    review = ReviewResult(
        comments=[InlineComment("a.py", 1, "sql injection", "critical")]
    )
    assert _infer_verdict(review) == "request_changes"


def test_infer_verdict_many_warnings():
    review = ReviewResult(
        comments=[
            InlineComment("a.py", 1, "w1", "warning"),
            InlineComment("a.py", 2, "w2", "warning"),
            InlineComment("a.py", 3, "w3", "warning"),
            InlineComment("a.py", 4, "w4", "warning"),
        ]
    )
    assert _infer_verdict(review) == "request_changes"


def test_infer_verdict_few_warnings_approves():
    review = ReviewResult(
        comments=[
            InlineComment("a.py", 1, "w1", "warning"),
            InlineComment("a.py", 2, "w2", "warning"),
            InlineComment("a.py", 3, "s1", "suggestion"),
        ]
    )
    assert _infer_verdict(review) == "approve"


# ---------------------------------------------------------------------------
# run_meta_review
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_meta_review_success():
    layer1_result = ReviewResult(
        comments=[InlineComment("a.py", 10, "fix this", "warning")],
        summary="Minor issues",
        agent_reviews=[
            AgentReview(
                agent_name="claude",
                model_id="claude-sonnet-4-6",
                comments=[InlineComment("a.py", 10, "fix this", "warning")],
                summary="Minor issues",
            )
        ],
    )

    mock_response = AgentResponse(
        content=json.dumps({
            "verdict": "approve",
            "confidence": 0.85,
            "consolidated_findings": [
                {
                    "file": "a.py",
                    "line": 10,
                    "comment": "Consider fixing this",
                    "severity": "suggestion",
                    "original_agents": ["claude"],
                    "false_positive": False,
                }
            ],
            "filtered_out": [],
            "summary": "Code quality is acceptable",
            "missed_issues": [],
        }),
        model_id="claude-sonnet-4-6",
        cost_usd=0.01,
        latency_ms=500,
    )

    with patch(
        "app.agents.meta_review_agent.ClaudeAgent"
    ) as mock_claude:
        instance = mock_claude.return_value
        instance.invoke = AsyncMock(return_value=mock_response)

        result = await run_meta_review(
            diff="--- a.py\n+++ a.py\n@@ ...",
            layer1_result=layer1_result,
        )

    assert result.verdict == "approve"
    assert result.confidence == 0.85
    assert len(result.consolidated_comments) == 1
    assert result.cost_usd == 0.01


@pytest.mark.asyncio
async def test_run_meta_review_agent_unavailable():
    layer1_result = ReviewResult(
        comments=[InlineComment("a.py", 1, "issue", "critical")],
        summary="Critical issue found",
        agent_reviews=[],
    )

    with patch(
        "app.agents.meta_review_agent.ClaudeAgent",
        side_effect=ValueError("No API key"),
    ):
        result = await run_meta_review(
            diff="diff",
            layer1_result=layer1_result,
        )

    assert result.verdict == "request_changes"
    assert result.confidence == 0.5
    assert len(result.consolidated_comments) == 1
    assert "unavailable" in result.summary


@pytest.mark.asyncio
async def test_run_meta_review_agent_error():
    layer1_result = ReviewResult(
        comments=[InlineComment("a.py", 1, "issue", "warning")],
        agent_reviews=[],
    )

    with patch(
        "app.agents.meta_review_agent.ClaudeAgent"
    ) as mock_claude:
        instance = mock_claude.return_value
        instance.invoke = AsyncMock(side_effect=RuntimeError("API error"))

        result = await run_meta_review(
            diff="diff",
            layer1_result=layer1_result,
        )

    assert result.confidence == 0.3
    assert "error" in result.summary.lower()


@pytest.mark.asyncio
async def test_run_meta_review_filters_false_positives():
    layer1_result = ReviewResult(
        comments=[
            InlineComment("a.py", 1, "real issue", "warning"),
            InlineComment("b.py", 5, "false alarm", "suggestion"),
        ],
        agent_reviews=[],
    )

    mock_response = AgentResponse(
        content=json.dumps({
            "verdict": "approve",
            "confidence": 0.95,
            "consolidated_findings": [
                {
                    "file": "a.py",
                    "line": 1,
                    "comment": "real issue",
                    "severity": "warning",
                    "original_agents": ["claude"],
                    "false_positive": False,
                },
                {
                    "file": "b.py",
                    "line": 5,
                    "comment": "false alarm",
                    "severity": "suggestion",
                    "original_agents": ["claude"],
                    "false_positive": True,
                },
            ],
            "filtered_out": [
                {"original_comment": "false alarm", "reason": "Not a real issue"}
            ],
            "summary": "One real issue, one false positive filtered",
            "missed_issues": [],
        }),
        model_id="claude-sonnet-4-6",
        cost_usd=0.01,
    )

    with patch(
        "app.agents.meta_review_agent.ClaudeAgent"
    ) as mock_claude:
        instance = mock_claude.return_value
        instance.invoke = AsyncMock(return_value=mock_response)

        result = await run_meta_review(
            diff="diff",
            layer1_result=layer1_result,
        )

    # False positive should be filtered out
    assert len(result.consolidated_comments) == 1
    assert result.consolidated_comments[0].comment == "real issue"
    assert result.filtered_count == 1


# ---------------------------------------------------------------------------
# meta_review_result_to_json
# ---------------------------------------------------------------------------


def test_meta_review_result_to_json():
    result = MetaReviewResult(
        verdict="approve",
        confidence=0.85,
        consolidated_comments=[
            InlineComment("a.py", 10, "issue", "warning"),
        ],
        filtered_count=2,
        missed_issues=["Missing null check"],
        summary="Acceptable code",
        cost_usd=0.015,
        latency_ms=1200,
    )
    data = meta_review_result_to_json(result)
    assert data["verdict"] == "approve"
    assert data["confidence"] == 0.85
    assert len(data["consolidated_comments"]) == 1
    assert data["filtered_count"] == 2
    assert data["missed_issues"] == ["Missing null check"]
    assert data["cost_usd"] == 0.015


def test_meta_review_result_to_json_empty():
    result = MetaReviewResult(verdict="needs_discussion", confidence=0.0)
    data = meta_review_result_to_json(result)
    assert data["verdict"] == "needs_discussion"
    assert data["consolidated_comments"] == []
    assert data["missed_issues"] == []


# ---------------------------------------------------------------------------
# MetaReviewOutput Pydantic model validation
# ---------------------------------------------------------------------------


def test_meta_review_output_defaults():
    output = MetaReviewOutput()
    assert output.verdict == "needs_discussion"
    assert output.confidence == 0.5
    assert output.consolidated_findings == []
    assert output.filtered_out == []


def test_meta_review_output_clamps_confidence():
    data = {"verdict": "approve", "confidence": 1.0}
    output = MetaReviewOutput.model_validate(data)
    assert output.confidence == 1.0
