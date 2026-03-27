"""Duplication detection — monitors code duplication in AI-generated code.

AI-generated code can exhibit 8x higher duplication than human-written code.
This module detects duplicated blocks across generated code artifacts
and reports metrics for the quality dashboard.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Minimum number of consecutive non-blank lines to consider a "block"
MIN_BLOCK_LINES = 4

# Minimum number of characters in a block to consider it meaningful
MIN_BLOCK_CHARS = 80


@dataclass
class DuplicateBlock:
    """A block of code that appears in multiple locations."""

    content_hash: str
    line_count: int
    locations: list[DuplicateLocation] = field(default_factory=list)

    @property
    def occurrence_count(self) -> int:
        return len(self.locations)


@dataclass
class DuplicateLocation:
    """Where a duplicate block was found."""

    file_path: str
    start_line: int
    end_line: int


@dataclass
class DuplicationReport:
    """Aggregated duplication analysis report."""

    total_lines: int = 0
    duplicated_lines: int = 0
    duplicate_blocks: list[DuplicateBlock] = field(default_factory=list)
    duplication_ratio: float = 0.0
    files_analyzed: int = 0

    @property
    def block_count(self) -> int:
        return len(self.duplicate_blocks)


def _normalize_line(line: str) -> str:
    """Normalize a line for comparison (strip whitespace, lowercase)."""
    return line.strip().lower()


def _extract_blocks(
    lines: list[str],
    min_lines: int = MIN_BLOCK_LINES,
) -> list[tuple[int, int, str]]:
    """Extract consecutive non-blank code blocks from a list of lines.

    Returns list of (start_line, end_line, normalized_content) tuples.
    Sliding window approach: for each starting position, extract blocks
    of min_lines through max available length.
    """
    blocks: list[tuple[int, int, str]] = []
    n = len(lines)

    i = 0
    while i < n:
        # Skip blank lines
        if not lines[i].strip():
            i += 1
            continue

        # Find the end of the non-blank sequence
        j = i
        while j < n and lines[j].strip():
            j += 1

        seq_len = j - i
        if seq_len >= min_lines:
            # Use fixed-size windows from this sequence
            for start in range(i, j - min_lines + 1):
                end = start + min_lines
                content = "\n".join(_normalize_line(lines[k]) for k in range(start, end))
                if len(content) >= MIN_BLOCK_CHARS:
                    blocks.append((start + 1, end, content))  # 1-indexed

        i = j

    return blocks


def detect_duplicates(
    files: dict[str, str],
    *,
    min_block_lines: int = MIN_BLOCK_LINES,
) -> DuplicationReport:
    """Detect code duplication across multiple files.

    Parameters
    ----------
    files:
        Mapping of ``{file_path: file_content}``.
    min_block_lines:
        Minimum consecutive lines to consider a duplicate block.

    Returns
    -------
    DuplicationReport with duplicate blocks and metrics.
    """
    # Hash -> list of locations
    block_map: dict[str, list[DuplicateLocation]] = defaultdict(list)
    # Hash -> block info
    block_content: dict[str, tuple[int, str]] = {}  # hash -> (line_count, content_preview)

    total_lines = 0

    for file_path, content in files.items():
        lines = content.splitlines()
        total_lines += len(lines)

        blocks = _extract_blocks(lines, min_lines=min_block_lines)
        for start_line, end_line, normalized in blocks:
            content_hash = hashlib.md5(normalized.encode()).hexdigest()  # noqa: S324
            block_map[content_hash].append(
                DuplicateLocation(
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                )
            )
            if content_hash not in block_content:
                block_content[content_hash] = (end_line - start_line + 1, normalized[:200])

    # Filter to only blocks that appear more than once
    duplicate_blocks: list[DuplicateBlock] = []
    duplicated_lines = 0

    for content_hash, locations in block_map.items():
        if len(locations) > 1:
            line_count = block_content[content_hash][0]
            block = DuplicateBlock(
                content_hash=content_hash,
                line_count=line_count,
                locations=locations,
            )
            duplicate_blocks.append(block)
            # Count duplicated lines (each extra occurrence beyond the first)
            duplicated_lines += line_count * (len(locations) - 1)

    # Sort by occurrence count (most duplicated first)
    duplicate_blocks.sort(key=lambda b: b.occurrence_count, reverse=True)

    duplication_ratio = (duplicated_lines / total_lines * 100) if total_lines > 0 else 0.0

    if duplicate_blocks:
        logger.info(
            "Duplication analysis: %d blocks duplicated, %.1f%% duplication ratio across %d files",
            len(duplicate_blocks),
            duplication_ratio,
            len(files),
        )

    return DuplicationReport(
        total_lines=total_lines,
        duplicated_lines=duplicated_lines,
        duplicate_blocks=duplicate_blocks,
        duplication_ratio=round(duplication_ratio, 2),
        files_analyzed=len(files),
    )
