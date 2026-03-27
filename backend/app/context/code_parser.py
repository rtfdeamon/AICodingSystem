"""Parse source code into semantic chunks for embedding."""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["ChunkType", "CodeChunk", "parse_file"]


class ChunkType(StrEnum):
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"


@dataclass
class CodeChunk:
    """A semantic chunk of source code."""

    file_path: str
    start_line: int
    end_line: int
    chunk_type: ChunkType
    symbol_name: str
    content: str
    language: str


# ── language detection ────────────────────────────────────────────────

_EXTENSION_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".php": "php",
    ".sh": "shell",
    ".bash": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".sql": "sql",
}


def _detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return _EXTENSION_LANGUAGE.get(ext, "unknown")


# ── Python parser (AST-based) ────────────────────────────────────────


def _parse_python(file_path: str, content: str) -> list[CodeChunk]:
    """Extract functions and classes from Python source using the ast module."""
    lines = content.splitlines(keepends=True)
    chunks: list[CodeChunk] = []

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        logger.warning("SyntaxError parsing %s; falling back to sliding window", file_path)
        return []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = node.end_lineno or start
            chunk_content = "".join(lines[start - 1 : end])
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    start_line=start,
                    end_line=end,
                    chunk_type=ChunkType.FUNCTION,
                    symbol_name=node.name,
                    content=chunk_content,
                    language="python",
                )
            )
        elif isinstance(node, ast.ClassDef):
            start = node.lineno
            end = node.end_lineno or start
            chunk_content = "".join(lines[start - 1 : end])
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    start_line=start,
                    end_line=end,
                    chunk_type=ChunkType.CLASS,
                    symbol_name=node.name,
                    content=chunk_content,
                    language="python",
                )
            )

    return chunks


# ── JavaScript / TypeScript parser (regex heuristic) ─────────────────

_JS_FUNCTION_RE = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)",
    re.MULTILINE,
)
_JS_ARROW_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",
    re.MULTILINE,
)
_JS_CLASS_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?class\s+(\w+)",
    re.MULTILINE,
)


def _find_block_end(lines: list[str], start_index: int) -> int:
    """Find the end of a brace-delimited block starting at *start_index*."""
    depth = 0
    found_open = False
    for i in range(start_index, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                found_open = True
            elif ch == "}":
                depth -= 1
                if found_open and depth == 0:
                    return i
    return min(start_index + 80, len(lines) - 1)


def _parse_js_ts(file_path: str, content: str, language: str) -> list[CodeChunk]:
    """Extract functions and classes from JS/TS source using regex heuristics."""
    lines = content.splitlines(keepends=True)
    chunks: list[CodeChunk] = []
    seen_ranges: set[tuple[int, int]] = set()

    patterns: list[tuple[re.Pattern[str], ChunkType]] = [
        (_JS_CLASS_RE, ChunkType.CLASS),
        (_JS_FUNCTION_RE, ChunkType.FUNCTION),
        (_JS_ARROW_RE, ChunkType.FUNCTION),
    ]

    for pattern, chunk_type in patterns:
        for match in pattern.finditer(content):
            symbol_name = match.group(1)
            # Determine line number from character offset
            start_line = content[: match.start()].count("\n") + 1
            start_idx = start_line - 1
            end_idx = _find_block_end(lines, start_idx)
            end_line = end_idx + 1

            range_key = (start_line, end_line)
            if range_key in seen_ranges:
                continue
            seen_ranges.add(range_key)

            chunk_content = "".join(lines[start_idx : end_idx + 1])
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type=chunk_type,
                    symbol_name=symbol_name,
                    content=chunk_content,
                    language=language,
                )
            )

    return chunks


# ── Sliding-window fallback ──────────────────────────────────────────

_WINDOW_SIZE = 80
_OVERLAP = 20


def _sliding_window_chunks(
    file_path: str,
    content: str,
    language: str,
) -> list[CodeChunk]:
    """Split content into overlapping windows as a language-agnostic fallback."""
    lines = content.splitlines(keepends=True)
    total = len(lines)
    if total == 0:
        return []

    chunks: list[CodeChunk] = []
    start = 0
    chunk_idx = 0

    while start < total:
        end = min(start + _WINDOW_SIZE, total)
        chunk_content = "".join(lines[start:end])
        chunks.append(
            CodeChunk(
                file_path=file_path,
                start_line=start + 1,
                end_line=end,
                chunk_type=ChunkType.MODULE,
                symbol_name=f"chunk_{chunk_idx}",
                content=chunk_content,
                language=language,
            )
        )
        chunk_idx += 1
        start += _WINDOW_SIZE - _OVERLAP

    return chunks


# ── Public API ────────────────────────────────────────────────────────


def parse_file(file_path: str, content: str) -> list[CodeChunk]:
    """Parse *content* of the file at *file_path* into semantic code chunks.

    Uses language-specific parsers where available:
    - **Python**: AST-based extraction of functions and classes.
    - **JavaScript/TypeScript**: Regex-based heuristic for function and class
      detection.
    - **Other languages**: Sliding-window chunking (~80 lines, 20-line overlap).

    If a language-specific parser yields no chunks (e.g. the file is only
    top-level statements), the sliding-window fallback is used instead.
    """
    if not content or not content.strip():
        return []

    language = _detect_language(file_path)
    chunks: list[CodeChunk] = []

    if language == "python":
        chunks = _parse_python(file_path, content)
    elif language in ("javascript", "typescript"):
        chunks = _parse_js_ts(file_path, content, language)

    # Fallback: if no semantic chunks found, use sliding window
    if not chunks:
        chunks = _sliding_window_chunks(file_path, content, language)

    return chunks
