"""Tests for app.agents.planning_agent — plan generation logic."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import AgentResponse
from app.agents.planning_agent import (
    GeneratedPlan,
    PlanSubtask,
    _parse_plan_output,
    generate_plan,
)
from app.models.ai_plan import PlanStatus

# Patch targets
_P_ROUTE = "app.agents.planning_agent.route_task"
_P_EXEC = "app.agents.planning_agent.execute_with_fallback"
_P_CTX = "app.agents.planning_agent.ContextEngine"


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

    def test_code_fence_without_trailing_fence(self) -> None:
        """Code fence at the start but no trailing ``` — still strips leading fence."""
        inner = json.dumps({"plan_markdown": "x", "subtasks": [], "file_list": []})
        raw = f"```json\n{inner}"
        result = _parse_plan_output(raw)
        assert result["plan_markdown"] == "x"

    def test_nested_json_in_code_fences(self) -> None:
        """JSON with nested objects inside code fences."""
        inner = json.dumps({
            "plan_markdown": "# Nested",
            "subtasks": [{"title": "T", "description": "D", "affected_files": ["a.py"]}],
            "file_list": ["a.py"],
        })
        raw = f"```\n{inner}\n```"
        result = _parse_plan_output(raw)
        assert result["subtasks"][0]["title"] == "T"


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


# ── Helper factories for generate_plan tests ─────────────────────────


def _make_ticket(
    *,
    title: str = "Implement auth",
    description: str | None = "Add JWT authentication",
    acceptance_criteria: str | None = "Users can log in",
) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.title = title
    t.description = description
    t.acceptance_criteria = acceptance_criteria
    return t


def _make_agent_response(
    plan_markdown: str = "# Plan",
    subtasks: list | None = None,
    file_list: list | None = None,
) -> AgentResponse:
    if subtasks is None:
        subtasks = [
            {
                "title": "Setup",
                "description": "Initial setup",
                "affected_files": ["src/setup.py"],
                "agent_hint": "claude",
                "estimated_complexity": "low",
                "dependencies": [],
            }
        ]
    if file_list is None:
        file_list = ["src/setup.py"]
    content = json.dumps({
        "plan_markdown": plan_markdown,
        "subtasks": subtasks,
        "file_list": file_list,
    })
    return AgentResponse(
        content=content,
        model_id="claude-opus-4-6",
        prompt_tokens=500,
        completion_tokens=1000,
        cost_usd=0.0825,
        latency_ms=3000,
    )


def _make_db(current_max_version: int = 0) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()

    # Mock for the version query: db.execute(...).scalar_one()
    version_result = MagicMock()
    version_result.scalar_one.return_value = current_max_version

    # Mock for the update query (supersede) — returns a generic result
    update_result = MagicMock()

    db.execute = AsyncMock(side_effect=[version_result, update_result])
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    return db


def _make_context_engine() -> AsyncMock:
    ce = AsyncMock()
    ce.get_context_for_ticket = AsyncMock(return_value="relevant code context")
    return ce


# ── generate_plan tests ──────────────────────────────────────────────


class TestGeneratePlan:
    """Tests for the main generate_plan orchestrator."""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        """Full success: context retrieval, AI call, parse, persist."""
        ticket = _make_ticket()
        project_id = uuid.uuid4()
        context_engine = _make_context_engine()
        db = _make_db(current_max_version=0)
        agent_resp = _make_agent_response()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp),
        ):
            await generate_plan(ticket, project_id, context_engine, db)

        # Verify context engine was called
        context_engine.get_context_for_ticket.assert_awaited_once_with(
            project_id=project_id,
            ticket_description=ticket.description,
            acceptance_criteria=ticket.acceptance_criteria,
        )

        # Verify plan was persisted
        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once()

        # Verify returned plan attributes
        added_plan = db.add.call_args[0][0]
        assert added_plan.ticket_id == ticket.id
        assert added_plan.version == 1
        assert added_plan.agent_name == "claude"
        assert added_plan.plan_markdown == "# Plan"
        assert added_plan.status == PlanStatus.PENDING
        assert len(added_plan.subtasks) == 1
        assert added_plan.subtasks[0]["title"] == "Setup"
        assert added_plan.file_list == ["src/setup.py"]
        assert added_plan.prompt_tokens == 500
        assert added_plan.completion_tokens == 1000
        assert added_plan.cost_usd == 0.0825
        assert added_plan.latency_ms == 3000

    @pytest.mark.asyncio
    async def test_version_increments(self) -> None:
        """Plan version is max(existing) + 1."""
        ticket = _make_ticket()
        db = _make_db(current_max_version=3)
        agent_resp = _make_agent_response()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp),
        ):
            await generate_plan(ticket, uuid.uuid4(), _make_context_engine(), db)

        added_plan = db.add.call_args[0][0]
        assert added_plan.version == 4

    @pytest.mark.asyncio
    async def test_ticket_no_description_uses_title(self) -> None:
        """When ticket.description is None, falls back to ticket.title."""
        ticket = _make_ticket(description=None)
        context_engine = _make_context_engine()
        db = _make_db()
        agent_resp = _make_agent_response()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp),
        ):
            await generate_plan(ticket, uuid.uuid4(), context_engine, db)

        context_engine.get_context_for_ticket.assert_awaited_once()
        call_kwargs = context_engine.get_context_for_ticket.call_args[1]
        assert call_kwargs["ticket_description"] == ticket.title

    @pytest.mark.asyncio
    async def test_ticket_no_acceptance_criteria(self) -> None:
        """When acceptance_criteria is None, prompt uses '(none specified)'."""
        ticket = _make_ticket(acceptance_criteria=None)
        db = _make_db()
        agent_resp = _make_agent_response()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp) as mock_exec,
        ):
            await generate_plan(ticket, uuid.uuid4(), _make_context_engine(), db)

        prompt_used = mock_exec.call_args[1]["prompt"]
        assert "(none specified)" in prompt_used

    @pytest.mark.asyncio
    async def test_ticket_no_description_prompt(self) -> None:
        """When description is None, prompt uses '(no description)'."""
        ticket = _make_ticket(description=None)
        db = _make_db()
        agent_resp = _make_agent_response()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp) as mock_exec,
        ):
            await generate_plan(ticket, uuid.uuid4(), _make_context_engine(), db)

        prompt_used = mock_exec.call_args[1]["prompt"]
        assert "(no description)" in prompt_used

    @pytest.mark.asyncio
    async def test_execute_with_fallback_called_correctly(self) -> None:
        """Verify the AI agent is invoked with the right parameters."""
        ticket = _make_ticket()
        db = _make_db()
        agent_resp = _make_agent_response()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent) as mock_route,
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp) as mock_exec,
        ):
            await generate_plan(ticket, uuid.uuid4(), _make_context_engine(), db)

        mock_route.assert_called_once_with("planning")
        mock_exec.assert_awaited_once()
        call_kwargs = mock_exec.call_args[1]
        assert call_kwargs["model_id"] == "claude-opus-4-6"
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["max_tokens"] == 8192
        assert call_kwargs["action_type"] == "planning"
        assert call_kwargs["ticket_id"] == ticket.id

    @pytest.mark.asyncio
    async def test_multiple_subtasks_parsed(self) -> None:
        """Multiple subtasks from AI response are all persisted."""
        subtasks = [
            {
                "title": "Task A",
                "description": "Do A",
                "affected_files": ["a.py"],
                "agent_hint": "claude",
                "estimated_complexity": "low",
                "dependencies": [],
            },
            {
                "title": "Task B",
                "description": "Do B",
                "affected_files": ["b.py"],
                "agent_hint": "gemini",
                "estimated_complexity": "high",
                "dependencies": [0],
            },
        ]
        agent_resp = _make_agent_response(
            subtasks=subtasks, file_list=["a.py", "b.py"]
        )
        db = _make_db()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp),
        ):
            await generate_plan(_make_ticket(), uuid.uuid4(), _make_context_engine(), db)

        added_plan = db.add.call_args[0][0]
        assert len(added_plan.subtasks) == 2
        assert added_plan.subtasks[0]["title"] == "Task A"
        assert added_plan.subtasks[1]["agent_hint"] == "gemini"
        assert added_plan.subtasks[1]["dependencies"] == [0]
        assert added_plan.file_list == ["a.py", "b.py"]

    @pytest.mark.asyncio
    async def test_subtask_missing_fields_get_defaults(self) -> None:
        """Subtasks missing optional fields get sensible defaults."""
        subtasks = [{"title": "Minimal"}]  # missing all optional keys
        agent_resp = _make_agent_response(subtasks=subtasks, file_list=[])
        db = _make_db()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp),
        ):
            await generate_plan(_make_ticket(), uuid.uuid4(), _make_context_engine(), db)

        added_plan = db.add.call_args[0][0]
        st = added_plan.subtasks[0]
        assert st["title"] == "Minimal"
        assert st["description"] == ""
        assert st["affected_files"] == []
        assert st["agent_hint"] == "claude"
        assert st["estimated_complexity"] == "medium"
        assert st["dependencies"] == []

    @pytest.mark.asyncio
    async def test_subtask_missing_title_gets_default(self) -> None:
        """Subtask without a title key gets 'Untitled subtask'."""
        subtasks = [{"description": "Just a description"}]
        agent_resp = _make_agent_response(subtasks=subtasks, file_list=[])
        db = _make_db()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp),
        ):
            await generate_plan(_make_ticket(), uuid.uuid4(), _make_context_engine(), db)

        added_plan = db.add.call_args[0][0]
        assert added_plan.subtasks[0]["title"] == "Untitled subtask"

    @pytest.mark.asyncio
    async def test_empty_subtasks_and_file_list(self) -> None:
        """Response with empty subtasks and file_list is handled."""
        agent_resp = _make_agent_response(
            plan_markdown="Empty plan", subtasks=[], file_list=[]
        )
        db = _make_db()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp),
        ):
            await generate_plan(_make_ticket(), uuid.uuid4(), _make_context_engine(), db)

        added_plan = db.add.call_args[0][0]
        assert added_plan.subtasks == []
        assert added_plan.file_list == []
        assert added_plan.plan_markdown == "Empty plan"

    @pytest.mark.asyncio
    async def test_missing_keys_in_parsed_output(self) -> None:
        """When parsed JSON is missing plan_markdown/subtasks/file_list, defaults apply."""
        # Agent returns valid JSON but with none of the expected keys
        agent_resp = AgentResponse(
            content=json.dumps({"unexpected_key": "value"}),
            model_id="claude-opus-4-6",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.01,
            latency_ms=1000,
        )
        db = _make_db()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp),
        ):
            await generate_plan(_make_ticket(), uuid.uuid4(), _make_context_engine(), db)

        added_plan = db.add.call_args[0][0]
        assert added_plan.plan_markdown == ""
        assert added_plan.subtasks == []
        assert added_plan.file_list == []

    @pytest.mark.asyncio
    async def test_invalid_json_from_agent_raises(self) -> None:
        """Invalid JSON from the agent raises ValueError."""
        agent_resp = AgentResponse(
            content="not valid json at all",
            model_id="claude-opus-4-6",
            prompt_tokens=100,
            completion_tokens=50,
        )
        db = _make_db()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp),
            pytest.raises(ValueError, match="invalid JSON"),
        ):
                await generate_plan(
                    _make_ticket(), uuid.uuid4(), _make_context_engine(), db
                )

    @pytest.mark.asyncio
    async def test_supersedes_prior_pending_plans(self) -> None:
        """Prior PENDING plans are marked SUPERSEDED."""
        db = _make_db(current_max_version=2)
        agent_resp = _make_agent_response()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp),
        ):
            await generate_plan(_make_ticket(), uuid.uuid4(), _make_context_engine(), db)

        # db.execute is called twice: once for version query, once for update
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_prompt_contains_ticket_details(self) -> None:
        """The user prompt includes ticket title, description, and criteria."""
        ticket = _make_ticket(
            title="Build API",
            description="REST endpoints for users",
            acceptance_criteria="GET /users returns 200",
        )
        db = _make_db()
        agent_resp = _make_agent_response()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp) as mock_exec,
        ):
            await generate_plan(ticket, uuid.uuid4(), _make_context_engine(), db)

        prompt_used = mock_exec.call_args[1]["prompt"]
        assert "Build API" in prompt_used
        assert "REST endpoints for users" in prompt_used
        assert "GET /users returns 200" in prompt_used

    @pytest.mark.asyncio
    async def test_prompt_includes_code_context(self) -> None:
        """The user prompt includes the code context from the context engine."""
        context_engine = _make_context_engine()
        context_engine.get_context_for_ticket.return_value = "def foo(): pass"
        db = _make_db()
        agent_resp = _make_agent_response()
        mock_agent = MagicMock()
        mock_agent.name = "claude"

        with (
            patch(_P_ROUTE, return_value=mock_agent),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=agent_resp) as mock_exec,
        ):
            await generate_plan(_make_ticket(), uuid.uuid4(), context_engine, db)

        prompt_used = mock_exec.call_args[1]["prompt"]
        assert "def foo(): pass" in prompt_used
