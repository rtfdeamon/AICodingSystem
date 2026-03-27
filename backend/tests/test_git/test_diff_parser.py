"""Tests for the git diff parser module."""

from __future__ import annotations

from app.git.diff_parser import DiffHunk, DiffLine, FileDiff, LineType, parse_diff

# ── Empty / blank input ───────────────────────────────────────────────


def test_parse_empty_string() -> None:
    assert parse_diff("") == []


def test_parse_whitespace_only() -> None:
    assert parse_diff("   \n  \n") == []


def test_parse_none_like() -> None:
    assert parse_diff("") == []


# ── Single file diff ──────────────────────────────────────────────────

SIMPLE_DIFF = """\
diff --git a/src/main.py b/src/main.py
--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,4 @@
 import os
+import sys

 def main():
"""


def test_parse_simple_diff() -> None:
    files = parse_diff(SIMPLE_DIFF)
    assert len(files) == 1
    assert files[0].file_path == "src/main.py"
    assert files[0].old_path == "src/main.py"
    assert len(files[0].hunks) == 1
    hunk = files[0].hunks[0]
    assert hunk.old_start == 1
    assert hunk.new_start == 1
    assert hunk.added_count == 1
    assert hunk.removed_count == 0


def test_file_diff_added_lines() -> None:
    files = parse_diff(SIMPLE_DIFF)
    assert files[0].added_lines == 1
    assert files[0].removed_lines == 0


# ── Multi-file diff ──────────────────────────────────────────────────

MULTI_FILE_DIFF = """\
diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -1,2 +1,3 @@
 line1
+new_line
 line2
diff --git a/src/b.py b/src/b.py
--- a/src/b.py
+++ b/src/b.py
@@ -1,3 +1,2 @@
 line1
-removed_line
 line3
"""


def test_parse_multi_file_diff() -> None:
    files = parse_diff(MULTI_FILE_DIFF)
    assert len(files) == 2
    assert files[0].file_path == "src/a.py"
    assert files[0].added_lines == 1
    assert files[1].file_path == "src/b.py"
    assert files[1].removed_lines == 1


# ── Rename diff ───────────────────────────────────────────────────────

RENAME_DIFF = """\
diff --git a/old_name.py b/new_name.py
--- a/old_name.py
+++ b/new_name.py
@@ -1,2 +1,2 @@
-old_content
+new_content
 common_line
"""


def test_parse_rename_diff() -> None:
    files = parse_diff(RENAME_DIFF)
    assert len(files) == 1
    assert files[0].file_path == "new_name.py"
    assert files[0].old_path == "old_name.py"
    assert files[0].added_lines == 1
    assert files[0].removed_lines == 1


# ── Multiple hunks ────────────────────────────────────────────────────

MULTI_HUNK_DIFF = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 import os
+import sys

 def main():
@@ -10,3 +11,4 @@

 def helper():
+    pass
     return None
"""


def test_parse_multi_hunk_diff() -> None:
    files = parse_diff(MULTI_HUNK_DIFF)
    assert len(files) == 1
    assert len(files[0].hunks) == 2
    assert files[0].hunks[0].added_count == 1
    assert files[0].hunks[1].added_count == 1
    assert files[0].added_lines == 2


# ── Line types ────────────────────────────────────────────────────────


def test_line_types() -> None:
    assert LineType.ADD == "add"
    assert LineType.REMOVE == "remove"
    assert LineType.CONTEXT == "context"


def test_diff_line_numbers() -> None:
    files = parse_diff(SIMPLE_DIFF)
    hunk = files[0].hunks[0]
    # First line is context: "import os"
    assert hunk.lines[0].type == LineType.CONTEXT
    assert hunk.lines[0].old_line_num == 1
    assert hunk.lines[0].new_line_num == 1
    # Second line is addition: "import sys"
    assert hunk.lines[1].type == LineType.ADD
    assert hunk.lines[1].old_line_num is None
    assert hunk.lines[1].new_line_num == 2


# ── DiffHunk properties ──────────────────────────────────────────────


def test_diff_hunk_counts() -> None:
    hunk = DiffHunk(old_start=1, old_count=3, new_start=1, new_count=3)
    hunk.lines = [
        DiffLine(type=LineType.ADD, content="a"),
        DiffLine(type=LineType.ADD, content="b"),
        DiffLine(type=LineType.REMOVE, content="c"),
        DiffLine(type=LineType.CONTEXT, content="d"),
    ]
    assert hunk.added_count == 2
    assert hunk.removed_count == 1


def test_file_diff_empty_hunks() -> None:
    fd = FileDiff(file_path="test.py", old_path="test.py")
    assert fd.added_lines == 0
    assert fd.removed_lines == 0
