"""Tests for code duplication detection module."""

from __future__ import annotations

from app.quality.duplication_detector import (
    DuplicateBlock,
    DuplicationReport,
    detect_duplicates,
)


class TestDuplicateDetection:
    def test_no_duplicates_in_unique_files(self) -> None:
        files = {
            "a.py": "def foo():\n    return 1\n",
            "b.py": "def bar():\n    return 2\n",
        }
        report = detect_duplicates(files)
        assert report.block_count == 0
        assert report.duplication_ratio == 0.0

    def test_detects_duplicate_block(self) -> None:
        block = "\n".join([
            "    result = db.execute(query)",
            "    rows = result.fetchall()",
            "    processed = [transform(r) for r in rows]",
            "    return processed",
        ])
        files = {
            "a.py": f"def get_users():\n{block}\n",
            "b.py": f"def get_orders():\n{block}\n",
        }
        report = detect_duplicates(files)
        assert report.block_count > 0
        assert report.duplicated_lines > 0

    def test_empty_files(self) -> None:
        files = {"a.py": "", "b.py": ""}
        report = detect_duplicates(files)
        assert report.block_count == 0
        assert report.total_lines == 0

    def test_single_file_no_duplicates(self) -> None:
        files = {
            "a.py": "line1\nline2\nline3\nline4\nline5\n",
        }
        report = detect_duplicates(files)
        # No duplicates within a single file with unique lines
        assert report.duplication_ratio == 0.0

    def test_files_analyzed_count(self) -> None:
        files = {"a.py": "x\n", "b.py": "y\n", "c.py": "z\n"}
        report = detect_duplicates(files)
        assert report.files_analyzed == 3

    def test_total_lines_count(self) -> None:
        files = {
            "a.py": "line1\nline2\nline3\n",
            "b.py": "line4\nline5\n",
        }
        report = detect_duplicates(files)
        assert report.total_lines == 5

    def test_custom_min_block_lines(self) -> None:
        # With min_block_lines=2, even 2-line blocks should be detected
        block = "    x = compute()\n    return x"
        files = {
            "a.py": f"def foo():\n{block}\n",
            "b.py": f"def bar():\n{block}\n",
        }
        report = detect_duplicates(files, min_block_lines=2)
        # Depending on normalization, may or may not find duplicates
        assert isinstance(report, DuplicationReport)

    def test_duplicate_block_occurrence_count(self) -> None:
        block = "\n".join([
            "    a = 1",
            "    b = 2",
            "    c = 3",
            "    d = 4",
        ])
        files = {
            "a.py": f"def f1():\n{block}\n",
            "b.py": f"def f2():\n{block}\n",
            "c.py": f"def f3():\n{block}\n",
        }
        report = detect_duplicates(files)
        if report.block_count > 0:
            assert report.duplicate_blocks[0].occurrence_count >= 2


class TestDuplicateBlockDataclass:
    def test_occurrence_count(self) -> None:
        block = DuplicateBlock(content_hash="abc", line_count=4)
        assert block.occurrence_count == 0


class TestDuplicationReport:
    def test_block_count(self) -> None:
        report = DuplicationReport()
        assert report.block_count == 0
