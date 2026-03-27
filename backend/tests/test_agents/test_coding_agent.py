"""Tests for app.agents.coding_agent — code generation logic."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import AgentResponse
from app.agents.coding_agent import (
    CodeGenResult,
    FileChange,
    _apply_file_changes,
    _parse_code_output,
    _run_lint,
    generate_code,
)

# Short aliases for frequently-patched targets
_P_ROUTE = "app.agents.coding_agent.route_task"
_P_EXEC = "app.agents.coding_agent.execute_with_fallback"
_P_LINT = "app.agents.coding_agent._run_lint"
_P_COMMIT = "app.agents.coding_agent.repo_manager.commit_changes"
_P_GET_AGENT = "app.agents.router._get_agent"

# ── _parse_code_output ───────────────────────────────────────────────


class TestParseCodeOutput:
    def test_valid_json(self) -> None:
        raw = json.dumps(
            {
                "files": [
                    {
                        "path": "src/main.py",
                        "action": "create",
                        "content": "print('hello')",
                        "diff_summary": "add main",
                    }
                ]
            }
        )
        changes = _parse_code_output(raw)
        assert len(changes) == 1
        assert changes[0].path == "src/main.py"
        assert changes[0].action == "create"
        assert changes[0].content == "print('hello')"
        assert changes[0].diff_summary == "add main"

    def test_strips_markdown_fences(self) -> None:
        raw = (
            '```json\n'
            '{"files": [{"path": "a.py", '
            '"action": "modify", "content": "x=1"}]}\n```'
        )
        changes = _parse_code_output(raw)
        assert len(changes) == 1
        assert changes[0].path == "a.py"

    def test_strips_plain_fences(self) -> None:
        raw = (
            '```\n{"files": [{"path": "b.py", '
            '"action": "delete", "content": null}]}\n```'
        )
        changes = _parse_code_output(raw)
        assert len(changes) == 1
        assert changes[0].action == "delete"
        assert changes[0].content is None

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid JSON"):
            _parse_code_output("not json at all")

    def test_missing_action_defaults_to_modify(self) -> None:
        raw = json.dumps({"files": [{"path": "c.py", "content": "code"}]})
        changes = _parse_code_output(raw)
        assert changes[0].action == "modify"

    def test_missing_diff_summary_defaults_to_empty(self) -> None:
        raw = json.dumps(
            {"files": [{"path": "d.py", "action": "create", "content": "code"}]}
        )
        changes = _parse_code_output(raw)
        assert changes[0].diff_summary == ""

    def test_multiple_files(self) -> None:
        raw = json.dumps(
            {
                "files": [
                    {"path": "a.py", "action": "create", "content": "a"},
                    {"path": "b.py", "action": "modify", "content": "b"},
                    {"path": "c.py", "action": "delete", "content": None},
                ]
            }
        )
        changes = _parse_code_output(raw)
        assert len(changes) == 3

    def test_empty_files_array(self) -> None:
        raw = json.dumps({"files": []})
        changes = _parse_code_output(raw)
        assert changes == []

    def test_no_files_key(self) -> None:
        raw = json.dumps({"other": "data"})
        changes = _parse_code_output(raw)
        assert changes == []

    def test_whitespace_around_json(self) -> None:
        raw = json.dumps(
            {"files": [{"path": "x.py", "action": "create", "content": "y"}]}
        )
        padded = f"  \n {raw} \n "
        changes = _parse_code_output(padded)
        assert len(changes) == 1
        assert changes[0].path == "x.py"


# ── _apply_file_changes ──────────────────────────────────────────────


class TestApplyFileChanges:
    def test_create_file(self, tmp_path: Path) -> None:
        changes = [
            FileChange(path="new_file.py", action="create", content="print('new')")
        ]
        paths = _apply_file_changes(changes, tmp_path)
        assert paths == ["new_file.py"]
        assert (tmp_path / "new_file.py").read_text() == "print('new')"

    def test_create_nested_file(self, tmp_path: Path) -> None:
        changes = [
            FileChange(
                path="src/utils/helper.py",
                action="create",
                content="# helper",
            )
        ]
        _apply_file_changes(changes, tmp_path)
        assert (tmp_path / "src" / "utils" / "helper.py").exists()

    def test_modify_file(self, tmp_path: Path) -> None:
        existing = tmp_path / "existing.py"
        existing.write_text("old content")
        changes = [
            FileChange(path="existing.py", action="modify", content="new content")
        ]
        _apply_file_changes(changes, tmp_path)
        assert existing.read_text() == "new content"

    def test_delete_file(self, tmp_path: Path) -> None:
        target = tmp_path / "to_delete.py"
        target.write_text("bye")
        changes = [FileChange(path="to_delete.py", action="delete")]
        _apply_file_changes(changes, tmp_path)
        assert not target.exists()

    def test_delete_nonexistent_file_no_error(self, tmp_path: Path) -> None:
        changes = [FileChange(path="ghost.py", action="delete")]
        paths = _apply_file_changes(changes, tmp_path)
        assert "ghost.py" in paths

    def test_content_none_writes_empty(self, tmp_path: Path) -> None:
        changes = [FileChange(path="empty.py", action="create", content=None)]
        _apply_file_changes(changes, tmp_path)
        assert (tmp_path / "empty.py").read_text() == ""

    def test_returns_all_paths(self, tmp_path: Path) -> None:
        changes = [
            FileChange(path="a.py", action="create", content="a"),
            FileChange(path="b.py", action="create", content="b"),
        ]
        paths = _apply_file_changes(changes, tmp_path)
        assert paths == ["a.py", "b.py"]


# ── _run_lint ────────────────────────────────────────────────────────


class TestRunLint:
    async def test_non_lintable_extension_passes(
        self, tmp_path: Path
    ) -> None:
        passed, errors = await _run_lint("data.csv", tmp_path)
        assert passed is True
        assert errors == ""

    async def test_python_file_linter_not_found(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "test.py").write_text("x = 1\n")
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError,
        ):
            passed, errors = await _run_lint("test.py", tmp_path)
        assert passed is True  # Linter not found -> skip

    async def test_python_file_lint_success(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "ok.py").write_text("x = 1\n")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ):
            passed, errors = await _run_lint("ok.py", tmp_path)
        assert passed is True
        assert errors == ""

    async def test_python_file_lint_failure(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "bad.py").write_text("x = 1\n")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"E001: some error", b"")
        )
        mock_proc.returncode = 1

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ):
            passed, errors = await _run_lint("bad.py", tmp_path)
        assert passed is False
        assert "E001" in errors

    async def test_js_file_uses_eslint(self, tmp_path: Path) -> None:
        (tmp_path / "app.js").write_text("var x = 1;\n")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            passed, _ = await _run_lint("app.js", tmp_path)
        assert passed is True
        call_args = mock_exec.call_args[0]
        assert "npx" in call_args[0]

    async def test_lint_timeout(self, tmp_path: Path) -> None:
        (tmp_path / "slow.py").write_text("x = 1\n")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ):
            passed, errors = await _run_lint("slow.py", tmp_path)
        assert passed is False
        assert "timed out" in errors

    async def test_tsx_file_uses_eslint(self, tmp_path: Path) -> None:
        (tmp_path / "comp.tsx").write_text("const x = 1;\n")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            passed, _ = await _run_lint("comp.tsx", tmp_path)
        assert passed is True
        call_args = mock_exec.call_args[0]
        assert "npx" in call_args[0]
        assert "eslint" in call_args[1]

    async def test_jsx_file_uses_eslint(self, tmp_path: Path) -> None:
        (tmp_path / "comp.jsx").write_text("const x = 1;\n")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            passed, _ = await _run_lint("comp.jsx", tmp_path)
        assert passed is True
        call_args = mock_exec.call_args[0]
        assert "npx" in call_args[0]

    async def test_ts_file_uses_eslint(self, tmp_path: Path) -> None:
        (tmp_path / "index.ts").write_text("const x: number = 1;\n")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            passed, _ = await _run_lint("index.ts", tmp_path)
        assert passed is True
        call_args = mock_exec.call_args[0]
        assert "npx" in call_args[0]

    async def test_lint_combines_stdout_and_stderr(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "warn.py").write_text("x = 1\n")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"stdout msg", b"stderr msg")
        )
        mock_proc.returncode = 1

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ):
            passed, errors = await _run_lint("warn.py", tmp_path)
        assert passed is False
        assert "stdout msg" in errors
        assert "stderr msg" in errors


# ── FileChange dataclass ─────────────────────────────────────────────


class TestFileChange:
    def test_defaults(self) -> None:
        fc = FileChange(path="a.py", action="create")
        assert fc.content is None
        assert fc.diff_summary == ""

    def test_all_fields(self) -> None:
        fc = FileChange(
            path="b.py",
            action="modify",
            content="new code",
            diff_summary="updated logic",
        )
        assert fc.path == "b.py"
        assert fc.content == "new code"


# ── CodeGenResult dataclass ──────────────────────────────────────────


class TestCodeGenResult:
    def test_defaults(self) -> None:
        r = CodeGenResult()
        assert r.files_changed == []
        assert r.commit_sha is None
        assert r.lint_passed is False
        assert r.retry_count == 0
        assert r.agent_used == ""


# ── Helper factories for generate_code tests ─────────────────────────


def _resp(files_json: list[dict]) -> AgentResponse:
    """Create an AgentResponse whose content is valid coding-agent JSON."""
    return AgentResponse(
        content=json.dumps({"files": files_json}),
        model_id="test-model",
        prompt_tokens=100,
        completion_tokens=200,
    )


def _agent(name: str = "claude") -> MagicMock:
    """Create a mock agent with the given name."""
    a = MagicMock()
    a.name = name
    return a


def _plan() -> MagicMock:
    """Create a mock AiPlan with required attributes."""
    p = MagicMock()
    p.id = uuid.uuid4()
    p.plan_markdown = "# Test Plan\nDo the thing."
    p.subtasks = [
        {"title": "Setup", "description": "Initial setup"},
        {"title": "Implement feature", "description": "Build the feature"},
    ]
    return p


def _db() -> AsyncMock:
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _ctx() -> AsyncMock:
    """Create a mock ContextEngine."""
    ce = AsyncMock()
    ce.get_context_for_ticket = AsyncMock(
        return_value="relevant code context here"
    )
    return ce


def _git(
    stdout: str = "[main abc1234] ai(0): implement subtask",
) -> MagicMock:
    """Create a mock GitResult."""
    r = MagicMock()
    r.stdout = stdout
    r.ok = True
    return r


async def _run_gen(
    subtask: dict,
    tmp_path: Path,
    *,
    plan: MagicMock | None = None,
    db: AsyncMock | None = None,
    context_engine: AsyncMock | None = None,
    subtask_index: int = 0,
    branch_name: str = "feature/test",
) -> CodeGenResult:
    """Shorthand to call generate_code with sensible defaults."""
    return await generate_code(
        subtask=subtask,
        subtask_index=subtask_index,
        plan=plan or _plan(),
        project_id=uuid.uuid4(),
        context_engine=context_engine or _ctx(),
        repo_path=tmp_path,
        db=db or _db(),
        ticket_id=uuid.uuid4(),
        branch_name=branch_name,
    )


# ── generate_code tests ─────────────────────────────────────────────


class TestGenerateCode:
    """Tests for the main generate_code orchestrator."""

    async def test_happy_path(self, tmp_path: Path) -> None:
        """Full success: generate, apply, lint passes, commit."""
        ar = _resp([{
            "path": "src/utils.py",
            "action": "create",
            "content": "# utils",
            "diff_summary": "add utils",
        }])
        ma = _agent()
        gr = _git()
        mock_db = _db()

        with (
            patch(_P_ROUTE, return_value=ma),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=ar),
            patch(_P_LINT, new_callable=AsyncMock, return_value=(True, "")),
            patch(_P_COMMIT, new_callable=AsyncMock, return_value=gr),
        ):
            result = await _run_gen(
                {"title": "Add utils", "description": "helpers",
                 "affected_files": ["src/utils.py"], "dependencies": []},
                tmp_path,
                db=mock_db,
            )

        assert result.agent_used == "claude"
        assert result.lint_passed is True
        assert result.retry_count == 0
        assert len(result.files_changed) == 1
        assert result.files_changed[0].path == "src/utils.py"
        assert result.commit_sha == "abc1234"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    async def test_lint_fails_then_fixes(self, tmp_path: Path) -> None:
        """Lint fails on first attempt, self-correction succeeds."""
        initial = _resp([{
            "path": "src/utils.py", "action": "create", "content": "bad",
        }])
        fixed = _resp([{
            "path": "src/utils.py", "action": "create",
            "content": "good", "diff_summary": "fixed",
        }])
        lint_results = [(False, "E001: error"), (True, "")]
        call_idx = 0

        async def _mock_lint(_fp, _rp):
            nonlocal call_idx
            r = lint_results[min(call_idx, len(lint_results) - 1)]
            call_idx += 1
            return r

        with (
            patch(_P_ROUTE, return_value=_agent()),
            patch(_P_EXEC, new_callable=AsyncMock,
                  side_effect=[initial, fixed]),
            patch(_P_LINT, side_effect=_mock_lint),
            patch(_P_COMMIT, new_callable=AsyncMock, return_value=_git()),
        ):
            result = await _run_gen(
                {"title": "T", "description": "d",
                 "affected_files": ["src/utils.py"], "dependencies": []},
                tmp_path,
            )

        assert result.lint_passed is True
        assert result.retry_count == 1

    async def test_lint_fails_all_retries(self, tmp_path: Path) -> None:
        """Lint fails on all retries; result records failure."""
        init = _resp([{
            "path": "src/utils.py", "action": "create", "content": "bad",
        }])
        fix = _resp([{
            "path": "src/utils.py", "action": "create",
            "content": "still bad",
        }])

        with (
            patch(_P_ROUTE, return_value=_agent()),
            patch(_P_EXEC, new_callable=AsyncMock,
                  side_effect=[init, fix, fix]),
            patch(_P_LINT, new_callable=AsyncMock,
                  return_value=(False, "E999: persistent")),
            patch(_P_COMMIT, new_callable=AsyncMock, return_value=_git()),
        ):
            result = await _run_gen(
                {"title": "T", "description": "d",
                 "affected_files": ["src/utils.py"], "dependencies": []},
                tmp_path,
            )

        assert result.lint_passed is False
        assert result.retry_count == 3

    async def test_commit_failure_graceful(self, tmp_path: Path) -> None:
        """Commit failure is handled; commit_sha stays None."""
        ar = _resp([{
            "path": "src/utils.py", "action": "create", "content": "# ok",
        }])

        with (
            patch(_P_ROUTE, return_value=_agent()),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=ar),
            patch(_P_LINT, new_callable=AsyncMock, return_value=(True, "")),
            patch(_P_COMMIT, new_callable=AsyncMock,
                  side_effect=RuntimeError("git error")),
        ):
            result = await _run_gen(
                {"title": "T", "description": "d",
                 "affected_files": ["src/utils.py"], "dependencies": []},
                tmp_path,
            )

        assert result.commit_sha is None
        assert result.lint_passed is True

    async def test_with_dependencies(self, tmp_path: Path) -> None:
        """Dependencies build completed_context from plan subtasks."""
        subtask = {
            "title": "Build on setup",
            "description": "Extend setup from subtask 0",
            "affected_files": ["src/feature.py"],
            "dependencies": [0],
        }
        ar = _resp([{
            "path": "src/feature.py", "action": "create",
            "content": "# feature",
        }])

        with (
            patch(_P_ROUTE, return_value=_agent()),
            patch(_P_EXEC, new_callable=AsyncMock,
                  return_value=ar) as mock_exec,
            patch(_P_LINT, new_callable=AsyncMock, return_value=(True, "")),
            patch(_P_COMMIT, new_callable=AsyncMock, return_value=_git()),
        ):
            result = await _run_gen(
                subtask, tmp_path, subtask_index=1,
            )

        prompt_used = mock_exec.call_args[1]["prompt"]
        assert "Setup" in prompt_used
        assert result.agent_used == "claude"

    async def test_agent_hint_used(self, tmp_path: Path) -> None:
        """When subtask has agent_hint, tries the hinted agent."""
        subtask = {
            "title": "T", "description": "d",
            "affected_files": ["src/utils.py"],
            "dependencies": [], "agent_hint": "gemini",
        }
        ar = _resp([{
            "path": "src/utils.py", "action": "create", "content": "#",
        }])
        hinted = _agent("gemini")

        with (
            patch(_P_ROUTE, return_value=_agent("claude")),
            patch(_P_GET_AGENT, return_value=hinted),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=ar),
            patch(_P_LINT, new_callable=AsyncMock, return_value=(True, "")),
            patch(_P_COMMIT, new_callable=AsyncMock, return_value=_git()),
        ):
            result = await _run_gen(subtask, tmp_path)

        assert result.agent_used == "gemini"

    async def test_agent_hint_unavailable_fallback(
        self, tmp_path: Path,
    ) -> None:
        """Unavailable hinted agent falls back to routed agent."""
        subtask = {
            "title": "T", "description": "d",
            "affected_files": ["src/utils.py"],
            "dependencies": [], "agent_hint": "nonexistent",
        }
        ar = _resp([{
            "path": "src/utils.py", "action": "create", "content": "#",
        }])

        with (
            patch(_P_ROUTE, return_value=_agent("claude")),
            patch(_P_GET_AGENT, side_effect=ValueError("nope")),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=ar),
            patch(_P_LINT, new_callable=AsyncMock, return_value=(True, "")),
            patch(_P_COMMIT, new_callable=AsyncMock, return_value=_git()),
        ):
            result = await _run_gen(subtask, tmp_path)

        assert result.agent_used == "claude"

    async def test_agent_hint_same_as_routed(
        self, tmp_path: Path,
    ) -> None:
        """agent_hint matching routed agent doesn't trigger override."""
        subtask = {
            "title": "T", "description": "d",
            "affected_files": ["src/utils.py"],
            "dependencies": [], "agent_hint": "claude",
        }
        ar = _resp([{
            "path": "src/utils.py", "action": "create", "content": "#",
        }])

        with (
            patch(_P_ROUTE, return_value=_agent("claude")),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=ar),
            patch(_P_LINT, new_callable=AsyncMock, return_value=(True, "")),
            patch(_P_COMMIT, new_callable=AsyncMock, return_value=_git()),
        ):
            result = await _run_gen(subtask, tmp_path)

        assert result.agent_used == "claude"

    async def test_delete_action_skips_lint(
        self, tmp_path: Path,
    ) -> None:
        """Delete-only file changes skip linting."""
        ar = _resp([{
            "path": "src/old.py", "action": "delete", "content": None,
        }])

        with (
            patch(_P_ROUTE, return_value=_agent()),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=ar),
            patch(_P_LINT, new_callable=AsyncMock) as mock_lint,
            patch(_P_COMMIT, new_callable=AsyncMock, return_value=_git()),
        ):
            result = await _run_gen(
                {"title": "T", "description": "d",
                 "affected_files": [], "dependencies": []},
                tmp_path,
            )

        mock_lint.assert_not_awaited()
        assert result.lint_passed is True

    async def test_commit_sha_parsed(self, tmp_path: Path) -> None:
        """Commit SHA extracted from git output."""
        ar = _resp([{
            "path": "src/utils.py", "action": "create", "content": "#",
        }])
        gr = _git(stdout="[feature/test deadbeef] ai(0): msg\n")

        with (
            patch(_P_ROUTE, return_value=_agent()),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=ar),
            patch(_P_LINT, new_callable=AsyncMock, return_value=(True, "")),
            patch(_P_COMMIT, new_callable=AsyncMock, return_value=gr),
        ):
            result = await _run_gen(
                {"title": "T", "description": "d",
                 "affected_files": ["src/utils.py"], "dependencies": []},
                tmp_path,
            )

        assert result.commit_sha == "deadbeef"

    async def test_empty_git_stdout(self, tmp_path: Path) -> None:
        """Empty git stdout yields no commit SHA."""
        ar = _resp([{
            "path": "src/utils.py", "action": "create", "content": "#",
        }])

        with (
            patch(_P_ROUTE, return_value=_agent()),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=ar),
            patch(_P_LINT, new_callable=AsyncMock, return_value=(True, "")),
            patch(_P_COMMIT, new_callable=AsyncMock,
                  return_value=_git(stdout="")),
        ):
            result = await _run_gen(
                {"title": "T", "description": "d",
                 "affected_files": ["src/utils.py"], "dependencies": []},
                tmp_path,
            )

        assert result.commit_sha is None

    async def test_no_affected_files_key(self, tmp_path: Path) -> None:
        """Subtask without affected_files key works fine."""
        ar = _resp([{
            "path": "src/r.py", "action": "create", "content": "# new",
        }])

        with (
            patch(_P_ROUTE, return_value=_agent()),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=ar),
            patch(_P_LINT, new_callable=AsyncMock, return_value=(True, "")),
            patch(_P_COMMIT, new_callable=AsyncMock, return_value=_git()),
        ):
            result = await _run_gen(
                {"title": "Refactor", "description": "Refactor things"},
                tmp_path,
            )

        assert len(result.files_changed) == 1

    async def test_dependency_out_of_range(self, tmp_path: Path) -> None:
        """Dependency index beyond subtasks list is silently skipped."""
        subtask = {
            "title": "Feature", "description": "Build it",
            "affected_files": [], "dependencies": [99],
        }
        ar = _resp([{
            "path": "src/f.py", "action": "create", "content": "# f",
        }])

        with (
            patch(_P_ROUTE, return_value=_agent()),
            patch(_P_EXEC, new_callable=AsyncMock,
                  return_value=ar) as mock_exec,
            patch(_P_LINT, new_callable=AsyncMock, return_value=(True, "")),
            patch(_P_COMMIT, new_callable=AsyncMock, return_value=_git()),
        ):
            result = await _run_gen(subtask, tmp_path)

        prompt_used = mock_exec.call_args[1]["prompt"]
        assert "No prior subtasks completed yet." in prompt_used
        assert result.lint_passed is True

    async def test_git_stdout_no_bracket(self, tmp_path: Path) -> None:
        """Git output without brackets yields no commit SHA."""
        ar = _resp([{
            "path": "src/utils.py", "action": "create", "content": "#",
        }])

        with (
            patch(_P_ROUTE, return_value=_agent()),
            patch(_P_EXEC, new_callable=AsyncMock, return_value=ar),
            patch(_P_LINT, new_callable=AsyncMock, return_value=(True, "")),
            patch(_P_COMMIT, new_callable=AsyncMock,
                  return_value=_git(stdout="unexpected output")),
        ):
            result = await _run_gen(
                {"title": "T", "description": "d",
                 "affected_files": ["src/utils.py"], "dependencies": []},
                tmp_path,
            )

        assert result.commit_sha is None
