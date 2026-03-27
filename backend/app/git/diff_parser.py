"""Parse unified diff output into structured objects."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

__all__ = ["DiffLine", "DiffHunk", "FileDiff", "LineType", "parse_diff"]


class LineType(StrEnum):
    ADD = "add"
    REMOVE = "remove"
    CONTEXT = "context"


@dataclass
class DiffLine:
    """A single line within a diff hunk."""

    type: LineType
    content: str
    old_line_num: int | None = None
    new_line_num: int | None = None


@dataclass
class DiffHunk:
    """A contiguous region of changes within a file diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[DiffLine] = field(default_factory=list)

    @property
    def added_count(self) -> int:
        return sum(1 for ln in self.lines if ln.type == LineType.ADD)

    @property
    def removed_count(self) -> int:
        return sum(1 for ln in self.lines if ln.type == LineType.REMOVE)


@dataclass
class FileDiff:
    """Parsed diff for a single file."""

    file_path: str
    old_path: str
    hunks: list[DiffHunk] = field(default_factory=list)

    @property
    def added_lines(self) -> int:
        return sum(h.added_count for h in self.hunks)

    @property
    def removed_lines(self) -> int:
        return sum(h.removed_count for h in self.hunks)


# ── regex patterns ────────────────────────────────────────────────────

_DIFF_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+?)$")
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(diff_text: str) -> list[FileDiff]:
    """Parse a unified diff string into a list of :class:`FileDiff` objects.

    Handles standard ``git diff`` output including renames, additions, and
    deletions.
    """
    if not diff_text or not diff_text.strip():
        return []

    files: list[FileDiff] = []
    current_file: FileDiff | None = None
    current_hunk: DiffHunk | None = None
    old_line = 0
    new_line = 0

    for raw_line in diff_text.splitlines():
        # ── new file diff ────────────────────────────────────────
        header_match = _DIFF_HEADER.match(raw_line)
        if header_match:
            current_file = FileDiff(
                file_path=header_match.group(2),
                old_path=header_match.group(1),
            )
            files.append(current_file)
            current_hunk = None
            continue

        # Skip --- and +++ header lines
        if raw_line.startswith("--- ") or raw_line.startswith("+++ "):
            continue

        # ── hunk header ──────────────────────────────────────────
        hunk_match = _HUNK_HEADER.match(raw_line)
        if hunk_match and current_file is not None:
            old_start = int(hunk_match.group(1))
            old_count = int(hunk_match.group(2) or "1")
            new_start = int(hunk_match.group(3))
            new_count = int(hunk_match.group(4) or "1")

            current_hunk = DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
            )
            current_file.hunks.append(current_hunk)
            old_line = old_start
            new_line = new_start
            continue

        # ── diff content lines ───────────────────────────────────
        if current_hunk is None:
            continue

        if raw_line.startswith("+"):
            current_hunk.lines.append(
                DiffLine(
                    type=LineType.ADD,
                    content=raw_line[1:],
                    old_line_num=None,
                    new_line_num=new_line,
                )
            )
            new_line += 1
        elif raw_line.startswith("-"):
            current_hunk.lines.append(
                DiffLine(
                    type=LineType.REMOVE,
                    content=raw_line[1:],
                    old_line_num=old_line,
                    new_line_num=None,
                )
            )
            old_line += 1
        elif raw_line.startswith(" ") or raw_line == "":
            content = raw_line[1:] if raw_line.startswith(" ") else raw_line
            current_hunk.lines.append(
                DiffLine(
                    type=LineType.CONTEXT,
                    content=content,
                    old_line_num=old_line,
                    new_line_num=new_line,
                )
            )
            old_line += 1
            new_line += 1
        # Skip binary file notices, mode changes, etc.

    return files
