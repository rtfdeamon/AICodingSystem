"""Tests for pipeline_orchestrator — AI-driven coding pipeline coordination."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import ColumnName
from app.workflows.pipeline_orchestrator import PipelineOrchestrator, _detect_language

# ---------------------------------------------------------------------------
# _detect_language helper
# ---------------------------------------------------------------------------


def test_detect_language_python():
    """Detects Python from .py files."""
    assert _detect_language(["src/main.py", "src/utils.py"]) == "python"


def test_detect_language_typescript():
    """Detects TypeScript from .ts/.tsx files."""
    assert _detect_language(["App.tsx", "utils.ts", "main.ts"]) == "typescript"


def test_detect_language_javascript():
    """Detects JavaScript from .js files."""
    assert _detect_language(["app.js", "utils.jsx"]) == "javascript"


def test_detect_language_mixed_majority_wins():
    """Returns the language with the most file extensions."""
    files = ["a.py", "b.py", "c.py", "d.ts"]
    assert _detect_language(files) == "python"


def test_detect_language_empty():
    """Falls back to Python for empty file list."""
    assert _detect_language([]) == "python"


def test_detect_language_unknown_ext():
    """Falls back to Python for unknown extensions."""
    assert _detect_language(["data.csv", "config.yaml"]) == "python"


def test_detect_language_go():
    """Detects Go from .go files."""
    assert _detect_language(["main.go", "handler.go"]) == "go"


def test_detect_language_rust():
    """Detects Rust from .rs files."""
    assert _detect_language(["main.rs"]) == "rust"


def test_detect_language_java():
    """Detects Java from .java files."""
    assert _detect_language(["App.java", "Main.java"]) == "java"


def test_detect_language_ruby():
    """Detects Ruby from .rb files."""
    assert _detect_language(["app.rb"]) == "ruby"


def test_detect_language_no_suffix():
    """Falls back to Python for files without extensions."""
    assert _detect_language(["Makefile", "Dockerfile"]) == "python"


# ---------------------------------------------------------------------------
# PipelineOrchestrator._get_ticket
# ---------------------------------------------------------------------------


async def test_get_ticket_found(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Returns ticket when it exists."""
    ticket = await create_test_ticket()
    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    result = await orchestrator._get_ticket(ticket.id)
    assert result.id == ticket.id


async def test_get_ticket_not_found(db_session: AsyncSession):
    """Raises ValueError when ticket doesn't exist."""
    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    with pytest.raises(ValueError, match="not found"):
        await orchestrator._get_ticket(uuid.uuid4())


# ---------------------------------------------------------------------------
# PipelineOrchestrator._repo_path
# ---------------------------------------------------------------------------


def test_repo_path():
    """Returns correct repo path from project ID."""
    orchestrator = PipelineOrchestrator(
        db=MagicMock(),
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )
    project_id = uuid.uuid4()
    assert orchestrator._repo_path(project_id) == Path(f"/var/data/repos/{project_id}")


# ---------------------------------------------------------------------------
# PipelineOrchestrator._update_ticket_column
# ---------------------------------------------------------------------------


async def test_update_ticket_column(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Updates ticket column and resets position."""
    ticket = await create_test_ticket(column="backlog")
    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    await orchestrator._update_ticket_column(ticket, ColumnName.AI_PLANNING)

    assert ticket.column_name == ColumnName.AI_PLANNING
    assert ticket.position == 0


# ---------------------------------------------------------------------------
# PipelineOrchestrator._log_progress
# ---------------------------------------------------------------------------


async def test_log_progress_broadcasts_ws(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Broadcasts pipeline progress via WebSocket."""
    ticket = await create_test_ticket()
    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    with patch("app.services.websocket_manager.ws_manager") as mock_ws:
        mock_ws.broadcast_to_project = AsyncMock()

        await orchestrator._log_progress(
            ticket.id,
            "planning",
            "Starting planning",
            {"key": "value"},
        )

    mock_ws.broadcast_to_project.assert_awaited_once()
    call_args = mock_ws.broadcast_to_project.call_args
    event = call_args[0][1]
    assert event["type"] == "pipeline.planning"
    assert event["data"]["phase"] == "planning"


async def test_log_progress_without_data(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Broadcasts pipeline progress with no extra data dict."""
    ticket = await create_test_ticket()
    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    with patch("app.services.websocket_manager.ws_manager") as mock_ws:
        mock_ws.broadcast_to_project = AsyncMock()

        await orchestrator._log_progress(
            ticket.id,
            "coding",
            "Processing subtask",
        )

    mock_ws.broadcast_to_project.assert_awaited_once()
    event = mock_ws.broadcast_to_project.call_args[0][1]
    assert event["type"] == "pipeline.coding"
    assert "timestamp" in event


# ---------------------------------------------------------------------------
# PipelineOrchestrator._get_latest_plan
# ---------------------------------------------------------------------------


async def test_get_latest_plan_not_found(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Raises ValueError when no approved plan exists."""
    ticket = await create_test_ticket()
    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    with pytest.raises(ValueError, match="No approved plan found"):
        await orchestrator._get_latest_plan(ticket.id)


# ---------------------------------------------------------------------------
# PipelineOrchestrator.run_planning_phase
# ---------------------------------------------------------------------------


async def test_run_planning_phase(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Planning phase generates a plan and moves ticket to plan_review."""
    ticket = await create_test_ticket(column="backlog")
    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    mock_plan = MagicMock()
    mock_plan.version = 1
    mock_plan.subtasks = [{"title": "sub1"}]
    mock_plan.id = uuid.uuid4()
    mock_plan.cost_usd = 0.05

    with (
        patch(
            "app.workflows.pipeline_orchestrator.generate_plan",
            new_callable=AsyncMock,
            return_value=mock_plan,
        ),
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_ws.broadcast_to_project = AsyncMock()

        result = await orchestrator.run_planning_phase(ticket.id)

    assert result == mock_plan
    assert ticket.column_name == ColumnName.PLAN_REVIEW


# ---------------------------------------------------------------------------
# PipelineOrchestrator.run_coding_phase
# ---------------------------------------------------------------------------


async def test_run_coding_phase_success(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Coding phase generates code for subtasks and moves ticket to code_review."""
    ticket = await create_test_ticket(column="backlog")
    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    mock_plan = MagicMock()
    mock_plan.subtasks = [
        {"title": "Implement endpoint"},
        {"title": "Add validation"},
    ]
    mock_plan.id = uuid.uuid4()

    mock_code_result = MagicMock()

    with (
        patch.object(
            orchestrator,
            "_get_latest_plan",
            new_callable=AsyncMock,
            return_value=mock_plan,
        ),
        patch(
            "app.workflows.pipeline_orchestrator.repo_manager",
        ) as mock_repo,
        patch(
            "app.workflows.pipeline_orchestrator.generate_code",
            new_callable=AsyncMock,
            return_value=mock_code_result,
        ),
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_repo.create_branch = AsyncMock()
        mock_repo.checkout_branch = AsyncMock()
        mock_ws.broadcast_to_project = AsyncMock()

        results = await orchestrator.run_coding_phase(ticket.id)

    assert len(results) == 2
    assert all(r == mock_code_result for r in results)
    assert ticket.column_name == ColumnName.CODE_REVIEW
    assert ticket.branch_name is not None
    assert ticket.branch_name.startswith("ai/")


async def test_run_coding_phase_branch_already_exists(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Coding phase falls back to checkout when branch creation fails."""
    ticket = await create_test_ticket(column="backlog")
    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    mock_plan = MagicMock()
    mock_plan.subtasks = [{"title": "task1"}]
    mock_plan.id = uuid.uuid4()

    mock_code_result = MagicMock()

    with (
        patch.object(
            orchestrator,
            "_get_latest_plan",
            new_callable=AsyncMock,
            return_value=mock_plan,
        ),
        patch(
            "app.workflows.pipeline_orchestrator.repo_manager",
        ) as mock_repo,
        patch(
            "app.workflows.pipeline_orchestrator.generate_code",
            new_callable=AsyncMock,
            return_value=mock_code_result,
        ),
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_repo.create_branch = AsyncMock(
            side_effect=RuntimeError("branch already exists")
        )
        mock_repo.checkout_branch = AsyncMock()
        mock_ws.broadcast_to_project = AsyncMock()

        results = await orchestrator.run_coding_phase(ticket.id)

    assert len(results) == 1
    # checkout_branch is called in the except block, then again for the first time
    # create_branch fails -> except calls checkout_branch (1 call)
    # loop does not call checkout again, so total = 1
    assert mock_repo.checkout_branch.await_count >= 1


async def test_run_coding_phase_subtask_failure_continues(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Coding phase continues when a subtask fails and records the failure."""
    ticket = await create_test_ticket(column="backlog")
    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    mock_plan = MagicMock()
    mock_plan.subtasks = [
        {"title": "will fail"},
        {"title": "will succeed"},
    ]
    mock_plan.id = uuid.uuid4()

    mock_code_result = MagicMock()
    call_count = 0

    async def _generate_code_side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("LLM timeout")
        return mock_code_result

    with (
        patch.object(
            orchestrator,
            "_get_latest_plan",
            new_callable=AsyncMock,
            return_value=mock_plan,
        ),
        patch(
            "app.workflows.pipeline_orchestrator.repo_manager",
        ) as mock_repo,
        patch(
            "app.workflows.pipeline_orchestrator.generate_code",
            new_callable=AsyncMock,
            side_effect=_generate_code_side_effect,
        ),
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_repo.create_branch = AsyncMock()
        mock_repo.checkout_branch = AsyncMock()
        mock_ws.broadcast_to_project = AsyncMock()

        results = await orchestrator.run_coding_phase(ticket.id)

    # Only the successful subtask is in results
    assert len(results) == 1
    assert ticket.column_name == ColumnName.CODE_REVIEW


async def test_run_coding_phase_empty_subtasks(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Coding phase handles plan with no subtasks gracefully."""
    ticket = await create_test_ticket(column="backlog")
    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    mock_plan = MagicMock()
    mock_plan.subtasks = None
    mock_plan.id = uuid.uuid4()

    with (
        patch.object(
            orchestrator,
            "_get_latest_plan",
            new_callable=AsyncMock,
            return_value=mock_plan,
        ),
        patch(
            "app.workflows.pipeline_orchestrator.repo_manager",
        ) as mock_repo,
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_repo.create_branch = AsyncMock()
        mock_repo.checkout_branch = AsyncMock()
        mock_ws.broadcast_to_project = AsyncMock()

        results = await orchestrator.run_coding_phase(ticket.id)

    assert results == []
    assert ticket.column_name == ColumnName.CODE_REVIEW


# ---------------------------------------------------------------------------
# PipelineOrchestrator.run_review_phase
# ---------------------------------------------------------------------------


async def test_run_review_phase_success(
    db_session: AsyncSession,
    create_test_ticket,
    tmp_path: Path,
):
    """Review phase runs security analysis and returns report."""
    ticket = await create_test_ticket(column="code_review")
    ticket.branch_name = "ai/TEST-abc123"
    await db_session.flush()

    # Create a fake changed file on disk
    project_dir = tmp_path / str(ticket.project_id)
    project_dir.mkdir(parents=True)
    changed_file = project_dir / "src" / "main.py"
    changed_file.parent.mkdir(parents=True)
    changed_file.write_text("print('hello')", encoding="utf-8")

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path=str(tmp_path),
    )

    mock_report = MagicMock()
    mock_report.total_findings = 2
    mock_report.severity_counts = {"high": 1, "low": 1}

    with (
        patch(
            "app.workflows.pipeline_orchestrator.repo_manager",
        ) as mock_repo,
        patch(
            "app.workflows.pipeline_orchestrator.analyze_security",
            new_callable=AsyncMock,
            return_value=mock_report,
        ) as mock_analyze,
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_repo.get_diff = AsyncMock(return_value="diff content")
        mock_repo.get_changed_files = AsyncMock(
            return_value=["src/main.py"]
        )
        mock_ws.broadcast_to_project = AsyncMock()

        result = await orchestrator.run_review_phase(ticket.id)

    assert result == mock_report
    mock_analyze.assert_awaited_once()
    # Verify file_contents were read and passed to analyze_security
    call_kwargs = mock_analyze.call_args[1]
    assert "src/main.py" in call_kwargs["file_contents"]


async def test_run_review_phase_no_branch_raises(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Review phase raises ValueError when ticket has no branch."""
    ticket = await create_test_ticket()
    ticket.branch_name = None
    await db_session.flush()

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    with (
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_ws.broadcast_to_project = AsyncMock()

        with pytest.raises(ValueError, match="no branch_name"):
            await orchestrator.run_review_phase(ticket.id)


async def test_run_review_phase_limits_files_to_twenty(
    db_session: AsyncSession,
    create_test_ticket,
    tmp_path: Path,
):
    """Review phase reads at most 20 changed files."""
    ticket = await create_test_ticket(column="code_review")
    ticket.branch_name = "ai/TEST-abc123"
    await db_session.flush()

    project_dir = tmp_path / str(ticket.project_id)
    project_dir.mkdir(parents=True)

    # Create 25 files on disk
    changed_names = []
    for i in range(25):
        fname = f"file_{i}.py"
        changed_names.append(fname)
        fpath = project_dir / fname
        fpath.write_text(f"# file {i}", encoding="utf-8")

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path=str(tmp_path),
    )

    mock_report = MagicMock()
    mock_report.total_findings = 0
    mock_report.severity_counts = {}

    with (
        patch(
            "app.workflows.pipeline_orchestrator.repo_manager",
        ) as mock_repo,
        patch(
            "app.workflows.pipeline_orchestrator.analyze_security",
            new_callable=AsyncMock,
            return_value=mock_report,
        ) as mock_analyze,
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_repo.get_diff = AsyncMock(return_value="diff")
        mock_repo.get_changed_files = AsyncMock(return_value=changed_names)
        mock_ws.broadcast_to_project = AsyncMock()

        await orchestrator.run_review_phase(ticket.id)

    call_kwargs = mock_analyze.call_args[1]
    assert len(call_kwargs["file_contents"]) <= 20


async def test_run_review_phase_skips_unreadable_files(
    db_session: AsyncSession,
    create_test_ticket,
    tmp_path: Path,
):
    """Review phase suppresses OSError for unreadable files."""
    ticket = await create_test_ticket(column="code_review")
    ticket.branch_name = "ai/TEST-abc123"
    await db_session.flush()

    project_dir = tmp_path / str(ticket.project_id)
    project_dir.mkdir(parents=True)
    # Don't create the file so is_file() returns False

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path=str(tmp_path),
    )

    mock_report = MagicMock()
    mock_report.total_findings = 0
    mock_report.severity_counts = {}

    with (
        patch(
            "app.workflows.pipeline_orchestrator.repo_manager",
        ) as mock_repo,
        patch(
            "app.workflows.pipeline_orchestrator.analyze_security",
            new_callable=AsyncMock,
            return_value=mock_report,
        ) as mock_analyze,
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_repo.get_diff = AsyncMock(return_value="diff")
        mock_repo.get_changed_files = AsyncMock(
            return_value=["nonexistent.py"]
        )
        mock_ws.broadcast_to_project = AsyncMock()

        result = await orchestrator.run_review_phase(ticket.id)

    assert result == mock_report
    call_kwargs = mock_analyze.call_args[1]
    assert call_kwargs["file_contents"] == {}


# ---------------------------------------------------------------------------
# PipelineOrchestrator.run_testing_phase
# ---------------------------------------------------------------------------


@dataclass
class _FakeTestFile:
    file_path: str
    content: str
    test_type: str


async def test_run_testing_phase_success(
    db_session: AsyncSession,
    create_test_ticket,
    tmp_path: Path,
):
    """Testing phase generates tests, commits, and triggers CI."""
    ticket = await create_test_ticket(column="code_review")
    ticket.branch_name = "ai/TEST-abc123"
    await db_session.flush()

    # Create project directory so test files can be written
    project_dir = tmp_path / str(ticket.project_id)
    project_dir.mkdir(parents=True)

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path=str(tmp_path),
    )

    fake_tests = [
        _FakeTestFile(
            file_path="tests/test_main.py",
            content="def test_ok(): assert True",
            test_type="unit",
        ),
        _FakeTestFile(
            file_path="tests/test_integration.py",
            content="def test_int(): pass",
            test_type="integration",
        ),
    ]

    with (
        patch(
            "app.workflows.pipeline_orchestrator.repo_manager",
        ) as mock_repo,
        patch(
            "app.workflows.pipeline_orchestrator.generate_tests",
            new_callable=AsyncMock,
            return_value=fake_tests,
        ),
        patch(
            "app.workflows.pipeline_orchestrator.trigger_workflow",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as mock_trigger,
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_repo.get_diff = AsyncMock(return_value="diff content")
        mock_repo.get_changed_files = AsyncMock(return_value=["src/main.py"])
        mock_repo.checkout_branch = AsyncMock()
        mock_repo.commit_changes = AsyncMock()
        mock_ws.broadcast_to_project = AsyncMock()

        result = await orchestrator.run_testing_phase(ticket.id)

    assert result["test_files_generated"] == 2
    assert set(result["test_types"]) == {"unit", "integration"}
    assert result["ci_triggered"] is True

    mock_trigger.assert_awaited_once_with(
        "build_test",
        {
            "ticket_id": str(ticket.id),
            "project_id": str(ticket.project_id),
            "branch_name": "ai/TEST-abc123",
        },
    )
    mock_repo.commit_changes.assert_awaited_once()

    # Verify test files were actually written
    assert (project_dir / "tests" / "test_main.py").exists()
    assert (project_dir / "tests" / "test_integration.py").exists()


async def test_run_testing_phase_no_branch_raises(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Testing phase raises ValueError when ticket has no branch."""
    ticket = await create_test_ticket()
    ticket.branch_name = None
    await db_session.flush()

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    with patch("app.services.websocket_manager.ws_manager") as mock_ws:
        mock_ws.broadcast_to_project = AsyncMock()

        with pytest.raises(ValueError, match="no branch_name"):
            await orchestrator.run_testing_phase(ticket.id)


async def test_run_testing_phase_test_gen_failure(
    db_session: AsyncSession,
    create_test_ticket,
    tmp_path: Path,
):
    """Testing phase continues even when test generation fails."""
    ticket = await create_test_ticket(column="code_review")
    ticket.branch_name = "ai/TEST-abc123"
    await db_session.flush()

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path=str(tmp_path),
    )

    with (
        patch(
            "app.workflows.pipeline_orchestrator.repo_manager",
        ) as mock_repo,
        patch(
            "app.workflows.pipeline_orchestrator.generate_tests",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM unavailable"),
        ),
        patch(
            "app.workflows.pipeline_orchestrator.trigger_workflow",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ),
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_repo.get_diff = AsyncMock(return_value="diff")
        mock_repo.get_changed_files = AsyncMock(return_value=["main.py"])
        mock_ws.broadcast_to_project = AsyncMock()

        result = await orchestrator.run_testing_phase(ticket.id)

    assert result["test_files_generated"] == 0
    assert result["test_types"] == []
    assert result["ci_triggered"] is True
    # commit_changes should NOT be called when there are no test files
    mock_repo.commit_changes.assert_not_called()


async def test_run_testing_phase_ci_error_status(
    db_session: AsyncSession,
    create_test_ticket,
    tmp_path: Path,
):
    """Testing phase reports ci_triggered=False when n8n returns error."""
    ticket = await create_test_ticket(column="code_review")
    ticket.branch_name = "ai/TEST-abc123"
    await db_session.flush()

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path=str(tmp_path),
    )

    with (
        patch(
            "app.workflows.pipeline_orchestrator.repo_manager",
        ) as mock_repo,
        patch(
            "app.workflows.pipeline_orchestrator.generate_tests",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.workflows.pipeline_orchestrator.trigger_workflow",
            new_callable=AsyncMock,
            return_value={"status": "error", "detail": "n8n is down"},
        ),
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_repo.get_diff = AsyncMock(return_value="diff")
        mock_repo.get_changed_files = AsyncMock(return_value=["main.py"])
        mock_ws.broadcast_to_project = AsyncMock()

        result = await orchestrator.run_testing_phase(ticket.id)

    assert result["ci_triggered"] is False


async def test_run_testing_phase_detects_language(
    db_session: AsyncSession,
    create_test_ticket,
    tmp_path: Path,
):
    """Testing phase detects language from changed files."""
    ticket = await create_test_ticket(column="code_review")
    ticket.branch_name = "ai/TEST-abc123"
    await db_session.flush()

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path=str(tmp_path),
    )

    with (
        patch(
            "app.workflows.pipeline_orchestrator.repo_manager",
        ) as mock_repo,
        patch(
            "app.workflows.pipeline_orchestrator.generate_tests",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_gen_tests,
        patch(
            "app.workflows.pipeline_orchestrator.trigger_workflow",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ),
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_repo.get_diff = AsyncMock(return_value="diff")
        mock_repo.get_changed_files = AsyncMock(
            return_value=["app.ts", "utils.ts", "index.tsx"]
        )
        mock_ws.broadcast_to_project = AsyncMock()

        await orchestrator.run_testing_phase(ticket.id)

    # Verify generate_tests was called with language="typescript"
    call_kwargs = mock_gen_tests.call_args[1]
    assert call_kwargs["language"] == "typescript"


# ---------------------------------------------------------------------------
# PipelineOrchestrator.run_deploy_phase
# ---------------------------------------------------------------------------


async def test_run_deploy_phase_staging(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Staging deploy triggers build_test workflow."""
    ticket = await create_test_ticket(column="code_review")
    ticket.branch_name = "ai/TEST-abc123"
    await db_session.flush()

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    with (
        patch(
            "app.workflows.pipeline_orchestrator.trigger_workflow",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ),
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_ws.broadcast_to_project = AsyncMock()

        result = await orchestrator.run_deploy_phase(ticket.id, "staging")

    assert result["environment"] == "staging"
    assert ticket.column_name == ColumnName.STAGING


async def test_run_deploy_phase_production(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Production deploy triggers canary workflow."""
    ticket = await create_test_ticket(column="staging_verification")
    ticket.branch_name = "ai/TEST-abc123"
    await db_session.flush()

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    with (
        patch(
            "app.workflows.pipeline_orchestrator.trigger_workflow",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ),
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_ws.broadcast_to_project = AsyncMock()

        result = await orchestrator.run_deploy_phase(ticket.id, "production")

    assert result["environment"] == "production"
    assert ticket.column_name == ColumnName.PRODUCTION


async def test_run_deploy_phase_no_branch(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Raises ValueError when ticket has no branch_name."""
    ticket = await create_test_ticket()
    ticket.branch_name = None
    await db_session.flush()

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    with patch("app.services.websocket_manager.ws_manager") as mock_ws:
        mock_ws.broadcast_to_project = AsyncMock()

        with pytest.raises(ValueError, match="no branch_name"):
            await orchestrator.run_deploy_phase(ticket.id)


async def test_run_deploy_phase_returns_deploy_status(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Deploy phase includes deploy_status from workflow response."""
    ticket = await create_test_ticket(column="code_review")
    ticket.branch_name = "ai/TEST-abc123"
    await db_session.flush()

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    with (
        patch(
            "app.workflows.pipeline_orchestrator.trigger_workflow",
            new_callable=AsyncMock,
            return_value={"status": "pending"},
        ),
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_ws.broadcast_to_project = AsyncMock()

        result = await orchestrator.run_deploy_phase(ticket.id, "staging")

    assert result["deploy_status"] == "pending"
    assert result["branch"] == "ai/TEST-abc123"


async def test_run_deploy_phase_unknown_status(
    db_session: AsyncSession,
    create_test_ticket,
):
    """Deploy phase defaults deploy_status to 'unknown' if key missing."""
    ticket = await create_test_ticket(column="code_review")
    ticket.branch_name = "ai/TEST-abc123"
    await db_session.flush()

    orchestrator = PipelineOrchestrator(
        db=db_session,
        context_engine=MagicMock(),
        repo_base_path="/var/data/repos",
    )

    with (
        patch(
            "app.workflows.pipeline_orchestrator.trigger_workflow",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch("app.services.websocket_manager.ws_manager") as mock_ws,
    ):
        mock_ws.broadcast_to_project = AsyncMock()

        result = await orchestrator.run_deploy_phase(ticket.id, "staging")

    assert result["deploy_status"] == "unknown"
