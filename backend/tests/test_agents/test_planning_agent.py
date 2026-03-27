"""Tests for app.agents.planning_agent — plan generation logic."""

from __future__ import annotations

import json

import pytest

from app.agents.planning_agent import (
    GeneratedPlan,
    PlanSubtask,
    _parse_plan_output,
)

# ── _parse_plan_output ───────────────────────────────────────────────


class TestParsePlanOutput:
    def test_valid_json(self) -> None:
        raw = json.dumps(
            {
                "plan_markdown": "# Plan\nDo the thing.",
                "subtasks": [
                    {
                        "title": "Add auth middleware",
                        "description": "Implement JWT validation",
                        "affected_files": ["src/middleware/auth.py"],
                        "agent_hint": "claude",
                        "estimated_complexity": "medium",
                        "dependencies": [],
                    }
                ],
                "file_list": ["src/middleware/auth.py"],
            }
        )
        result = _parse_plan_output(raw)
        assert result["plan_markdown"] == "# Plan\nDo the thing."
        assert len(result["subtasks"]) == 1
        assert result["subtasks"][0]["title"] == "Add auth middleware"

    def test_strips_json_code_fences(self) -> None:
        inner = json.dumps(
            {"plan_markdown": "plan", "subtasks": [], "file_list": []}
        )
        raw = f"```json\n{inner}\n```"
        result = _parse_plan_output(raw)
        assert result["plan_markdown"] == "plan"

    def test_strips_plain_code_fences(self) -> None:
        inner = json.dumps(
            {"plan_markdown": "plan2", "subtasks": [], "file_list": []}
        )
        raw = f"```\n{inner}\n```"
        result = _parse_plan_output(raw)
        assert result["plan_markdown"] == "plan2"

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid JSON"):
            _parse_plan_output("this is not json")

    def test_empty_plan(self) -> None:
        raw = json.dumps({"plan_markdown": "", "subtasks": [], "file_list": []})
        result = _parse_plan_output(raw)
        assert result["plan_markdown"] == ""
        assert result["subtasks"] == []

    def test_multiple_subtasks(self) -> None:
        raw = json.dumps(
            {
                "plan_markdown": "# Big plan",
                "subtasks": [
                    {"title": "Task 1", "description": "First"},
                    {"title": "Task 2", "description": "Second", "dependencies": [0]},
                    {"title": "Task 3", "description": "Third", "dependencies": [0, 1]},
                ],
                "file_list": ["a.py", "b.py", "c.py"],
            }
        )
        result = _parse_plan_output(raw)
        assert len(result["subtasks"]) == 3
        assert result["subtasks"][2]["dependencies"] == [0, 1]

    def test_whitespace_stripped(self) -> None:
        raw = "  \n" + json.dumps({"plan_markdown": "ok", "subtasks": [], "file_list": []}) + "\n  "
        result = _parse_plan_output(raw)
        assert result["plan_markdown"] == "ok"


# ── PlanSubtask dataclass ────────────────────────────────────────────


class TestPlanSubtask:
    def test_defaults(self) -> None:
        st = PlanSubtask(title="Test", description="Desc")
        assert st.affected_files == []
        assert st.agent_hint == "claude"
        assert st.estimated_complexity == "medium"
        assert st.dependencies == []

    def test_all_fields(self) -> None:
        st = PlanSubtask(
            title="Add logging",
            description="Add structured logging to all endpoints",
            affected_files=["api/v1/tickets.py"],
            agent_hint="codex",
            estimated_complexity="low",
            dependencies=[0, 1],
        )
        assert st.title == "Add logging"
        assert st.agent_hint == "codex"
        assert st.dependencies == [0, 1]


# ── GeneratedPlan dataclass ──────────────────────────────────────────


class TestGeneratedPlan:
    def test_creation(self) -> None:
        from app.agents.base import AgentResponse

        resp = AgentResponse(
            content="raw json",
            model_id="claude-opus-4-6",
            prompt_tokens=100,
            completion_tokens=200,
        )
        plan = GeneratedPlan(
            plan_markdown="# Plan",
            subtasks=[PlanSubtask(title="T1", description="D1")],
            file_list=["a.py"],
            agent_response=resp,
        )
        assert plan.plan_markdown == "# Plan"
        assert len(plan.subtasks) == 1
        assert plan.agent_response.model_id == "claude-opus-4-6"
