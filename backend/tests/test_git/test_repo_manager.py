"""Tests for app.git.repo_manager — local git operations."""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.git.repo_manager import (
    GitCommandError,
    GitResult,
    MergeResult,
    _run_git,
    _run_git_checked,
    checkout_branch,
    clone_repo,
    commit_changes,
    create_branch,
    create_worktree,
    get_changed_files,
    get_diff,
    merge_branches,
    push_branch,
)

# Test-only repo path constant — not a real temp dir
_REPO = "/fake/test/repo"

# ── GitResult dataclass ──────────────────────────────────────────────


class TestGitResult:
    def test_ok_when_zero(self) -> None:
        r = GitResult(returncode=0, stdout="output", stderr="")
        assert r.ok is True

    def test_not_ok_when_nonzero(self) -> None:
        r = GitResult(returncode=1, stdout="", stderr="error")
        assert r.ok is False

    def test_not_ok_when_128(self) -> None:
        r = GitResult(returncode=128, stdout="", stderr="fatal")
        assert r.ok is False


# ── GitCommandError ──────────────────────────────────────────────────


class TestGitCommandError:
    def test_error_message(self) -> None:
        result = GitResult(returncode=1, stdout="", stderr="not a git repo")
        err = GitCommandError("status", result)
        assert "not a git repo" in str(err)
        assert err.command == "status"
        assert err.result is result

    def test_error_with_returncode(self) -> None:
        result = GitResult(returncode=128, stdout="", stderr="fatal error")
        err = GitCommandError("clone", result)
        assert "(128)" in str(err)


# ── _run_git ─────────────────────────────────────────────────────────


class TestRunGit:
    async def test_successful_command(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"output\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await _run_git("status")

        assert result.ok is True
        assert result.stdout == "output\n"

    async def test_failed_command(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error\n"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await _run_git("status")

        assert result.ok is False
        assert result.stderr == "error\n"

    async def test_timeout_kills_process(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.kill = MagicMock()
        mock_proc.returncode = -9

        async def fake_wait_for(coro, timeout):
            with contextlib.suppress(Exception):
                coro.close()
            raise TimeoutError()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", side_effect=fake_wait_for),
            pytest.raises(TimeoutError, match="timed out"),
        ):
            await _run_git("clone", "huge-repo", timeout=1.0)

    async def test_cwd_parameter(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await _run_git("status", cwd=_REPO)

        mock_exec.assert_called_once()
        assert mock_exec.call_args[1]["cwd"] == _REPO


# ── _run_git_checked ─────────────────────────────────────────────────


class TestRunGitChecked:
    async def test_returns_result_on_success(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await _run_git_checked("status")

        assert result.ok is True

    async def test_raises_on_failure(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"fatal"))
        mock_proc.returncode = 128

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc), pytest.raises(
            GitCommandError,
        ):
            await _run_git_checked("checkout", "nonexistent")


# ── clone_repo ───────────────────────────────────────────────────────


class TestCloneRepo:
    async def test_clone_success(self, tmp_path: Path) -> None:
        dest = tmp_path / "cloned"
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Cloning...", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await clone_repo("https://github.com/owner/repo.git", dest)

        assert result.ok is True

    async def test_clone_creates_parent_dir(self, tmp_path: Path) -> None:
        dest = tmp_path / "deep" / "nested" / "repo"
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await clone_repo("https://github.com/test/test.git", dest)

        assert dest.parent.exists()

    async def test_clone_failure_raises(self, tmp_path: Path) -> None:
        dest = tmp_path / "fail"
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"fatal: repo not found"))
        mock_proc.returncode = 128

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc), pytest.raises(
            GitCommandError,
        ):
            await clone_repo("https://github.com/invalid/repo.git", dest)


# ── create_branch ────────────────────────────────────────────────────


class TestCreateBranch:
    async def test_creates_branch(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await create_branch(_REPO, "feature/new")

        assert result.ok is True


# ── checkout_branch ──────────────────────────────────────────────────


class TestCheckoutBranch:
    async def test_checkout(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Switched to branch", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await checkout_branch(_REPO, "main")

        assert result.ok is True


# ── commit_changes ───────────────────────────────────────────────────


class TestCommitChanges:
    async def test_commit_specific_files(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await commit_changes(_REPO, "Fix bug", files=["a.py", "b.py"])

        assert result.ok is True
        # Should have called git add -- a.py b.py, then git commit
        assert mock_exec.call_count == 2

    async def test_commit_all_changes(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await commit_changes(_REPO, "Update all")

        assert result.ok is True
        assert mock_exec.call_count == 2


# ── push_branch ──────────────────────────────────────────────────────


class TestPushBranch:
    async def test_push_success(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"pushed", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await push_branch(_REPO, "feature/x")

        assert result.ok is True


# ── MergeResult dataclass ────────────────────────────────────────────


class TestMergeResult:
    def test_successful_merge(self) -> None:
        git_result = GitResult(returncode=0, stdout="ok", stderr="")
        mr = MergeResult(
            success=True, has_conflicts=False,
            conflicted_files=[], git_result=git_result,
        )
        assert mr.success is True
        assert mr.has_conflicts is False

    def test_conflict_merge(self) -> None:
        git_result = GitResult(returncode=1, stdout="", stderr="conflict")
        mr = MergeResult(
            success=False,
            has_conflicts=True,
            conflicted_files=["file.py"],
            git_result=git_result,
        )
        assert mr.success is False
        assert mr.conflicted_files == ["file.py"]


# ── merge_branches ───────────────────────────────────────────────────


class TestMergeBranches:
    async def test_successful_merge(self) -> None:
        call_count = 0

        async def mock_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"ok\n", b""))
            mock_proc.returncode = 0
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await merge_branches(_REPO, "feature", "main")

        assert result.success is True
        assert result.has_conflicts is False

    async def test_merge_with_conflicts(self) -> None:
        calls: list[tuple] = []

        async def mock_exec(*args, **kwargs):
            calls.append(args)
            mock_proc = AsyncMock()
            if len(calls) == 1:  # checkout
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_proc.returncode = 0
            elif len(calls) == 2:  # merge
                mock_proc.communicate = AsyncMock(return_value=(b"", b"CONFLICT"))
                mock_proc.returncode = 1
            elif len(calls) == 3:  # diff
                mock_proc.communicate = AsyncMock(return_value=(b"conflict_file.py\n", b""))
                mock_proc.returncode = 0
            else:  # merge --abort
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_proc.returncode = 0
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await merge_branches(_REPO, "feature", "main")

        assert result.success is False
        assert result.has_conflicts is True
        assert "conflict_file.py" in result.conflicted_files


# ── get_diff ─────────────────────────────────────────────────────────


class TestGetDiff:
    async def test_returns_diff(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"diff --git a/f.py b/f.py\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await get_diff(_REPO, "main", "feature")

        assert "diff --git" in result


# ── get_changed_files ────────────────────────────────────────────────


class TestGetChangedFiles:
    async def test_returns_changed_files(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"a.py\nb.py\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await get_changed_files(_REPO, "main", "feature")

        assert result == ["a.py", "b.py"]

    async def test_returns_changed_files_vs_head(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"c.py\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await get_changed_files(_REPO, "main")

        assert result == ["c.py"]

    async def test_empty_diff(self) -> None:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await get_changed_files(_REPO, "main", "main")

        assert result == []


# ── create_worktree ──────────────────────────────────────────────────


class TestCreateWorktree:
    async def test_creates_worktree(self, tmp_path: Path) -> None:
        wt_path = tmp_path / "worktrees" / "agent-1"
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Preparing worktree", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await create_worktree(_REPO, wt_path, "ai/coding-1")

        assert result.ok is True
        assert wt_path.parent.exists()
