"""Local git repository operations using async subprocess."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitResult:
    """Captures the result of a git subprocess invocation."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class GitCommandError(Exception):
    """Raised when a git command exits with a non-zero status."""

    def __init__(self, command: str, result: GitResult) -> None:
        self.command = command
        self.result = result
        super().__init__(
            f"git command failed ({result.returncode}): {command}\nstderr: {result.stderr.strip()}"
        )


async def _run_git(
    *args: str,
    cwd: str | Path | None = None,
    timeout: float = 120.0,
) -> GitResult:
    """Run a git command as an async subprocess and return the result."""
    cmd = ["git", *args]
    logger.debug("Running: %s (cwd=%s)", " ".join(cmd), cwd)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
    except TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"git command timed out after {timeout}s: {' '.join(cmd)}") from exc

    result = GitResult(
        returncode=proc.returncode or 0,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )
    if not result.ok:
        logger.warning(
            "git command returned %d: %s\nstderr: %s",
            result.returncode,
            " ".join(cmd),
            result.stderr.strip(),
        )
    return result


async def _run_git_checked(
    *args: str,
    cwd: str | Path | None = None,
    timeout: float = 120.0,
) -> GitResult:
    """Run a git command and raise :class:`GitCommandError` on failure."""
    result = await _run_git(*args, cwd=cwd, timeout=timeout)
    if not result.ok:
        raise GitCommandError(" ".join(args), result)
    return result


# ── Public API ────────────────────────────────────────────────────────


async def clone_repo(
    repo_url: str,
    dest_path: str | Path,
    branch: str = "main",
) -> GitResult:
    """Clone a remote repository to *dest_path*.

    Uses ``--depth 1`` for faster clones by default.
    """
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Cloning %s (branch=%s) -> %s", repo_url, branch, dest)
    return await _run_git_checked(
        "clone",
        "--branch",
        branch,
        "--single-branch",
        "--depth",
        "1",
        repo_url,
        str(dest),
        timeout=300.0,
    )


async def create_branch(repo_path: str | Path, branch_name: str) -> GitResult:
    """Create a new local branch at the current HEAD."""
    logger.info("Creating branch %s in %s", branch_name, repo_path)
    return await _run_git_checked("branch", branch_name, cwd=repo_path)


async def checkout_branch(repo_path: str | Path, branch_name: str) -> GitResult:
    """Switch to an existing local branch."""
    logger.info("Checking out branch %s in %s", branch_name, repo_path)
    return await _run_git_checked("checkout", branch_name, cwd=repo_path)


async def commit_changes(
    repo_path: str | Path,
    message: str,
    files: list[str] | None = None,
) -> GitResult:
    """Stage *files* (or all changes) and create a commit.

    Parameters
    ----------
    files:
        Specific file paths to stage.  If *None*, stages all changes
        (``git add -A``).
    """
    if files:
        await _run_git_checked("add", "--", *files, cwd=repo_path)
    else:
        await _run_git_checked("add", "-A", cwd=repo_path)

    return await _run_git_checked("commit", "-m", message, cwd=repo_path)


async def push_branch(
    repo_path: str | Path,
    branch_name: str,
    remote: str = "origin",
) -> GitResult:
    """Push a local branch to *remote*."""
    logger.info("Pushing %s to %s/%s", branch_name, remote, branch_name)
    return await _run_git_checked(
        "push",
        "--set-upstream",
        remote,
        branch_name,
        cwd=repo_path,
    )


@dataclass(frozen=True)
class MergeResult:
    """Outcome of a merge attempt."""

    success: bool
    has_conflicts: bool
    conflicted_files: list[str]
    git_result: GitResult


async def merge_branches(
    repo_path: str | Path,
    source: str,
    target: str,
) -> MergeResult:
    """Merge *source* into *target* with conflict detection.

    Checks out *target* first, then attempts ``git merge --no-ff source``.
    """
    await _run_git_checked("checkout", target, cwd=repo_path)
    result = await _run_git("merge", "--no-ff", source, cwd=repo_path)

    if result.ok:
        logger.info("Merged %s into %s successfully", source, target)
        return MergeResult(
            success=True,
            has_conflicts=False,
            conflicted_files=[],
            git_result=result,
        )

    # Check for conflicts
    diff_result = await _run_git("diff", "--name-only", "--diff-filter=U", cwd=repo_path)
    conflicted = [f.strip() for f in diff_result.stdout.splitlines() if f.strip()]

    if conflicted:
        logger.warning(
            "Merge %s -> %s has conflicts in %d file(s): %s",
            source,
            target,
            len(conflicted),
            ", ".join(conflicted),
        )
        # Abort the merge so the worktree is clean
        await _run_git("merge", "--abort", cwd=repo_path)
        return MergeResult(
            success=False,
            has_conflicts=True,
            conflicted_files=conflicted,
            git_result=result,
        )

    raise GitCommandError(f"merge {source} into {target}", result)


async def get_diff(
    repo_path: str | Path,
    base_branch: str,
    head_branch: str,
) -> str:
    """Return the unified diff between two branches."""
    result = await _run_git_checked(
        "diff",
        f"{base_branch}...{head_branch}",
        cwd=repo_path,
    )
    return result.stdout


async def get_changed_files(
    repo_path: str | Path,
    base_branch: str,
    head_branch: str | None = None,
) -> list[str]:
    """Return the list of files changed between *base_branch* and HEAD (or *head_branch*)."""
    ref_spec = f"{base_branch}...{head_branch}" if head_branch else f"{base_branch}...HEAD"
    result = await _run_git_checked(
        "diff",
        "--name-only",
        ref_spec,
        cwd=repo_path,
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


async def create_worktree(
    repo_path: str | Path,
    worktree_path: str | Path,
    branch_name: str,
) -> GitResult:
    """Create a git worktree for parallel agent work.

    Creates a new worktree at *worktree_path* on branch *branch_name*.
    If the branch does not exist, it is created automatically (``-b``).
    """
    wt = Path(worktree_path)
    wt.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Creating worktree at %s on branch %s (repo=%s)",
        wt,
        branch_name,
        repo_path,
    )
    return await _run_git_checked(
        "worktree",
        "add",
        "-b",
        branch_name,
        str(wt),
        cwd=repo_path,
    )
