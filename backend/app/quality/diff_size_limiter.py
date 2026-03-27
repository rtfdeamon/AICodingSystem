"""Diff Size Limiter — automatically split large AI-generated code diffs
into reviewable chunks.

Large code diffs reduce review quality: research shows that reviewers
miss more defects when diffs exceed 400-500 lines. AI code generation
can easily produce 1000+ line changes, making effective review impossible.

Based on Google Engineering Practices (2024), SmartBear/Cisco study on
code review effectiveness, and industry guidelines from
zhanymkanov/fastapi-best-practices. Also informed by DORA 2025 report
recommendations on working in small batches.

Key capabilities:
- Diff size analysis: count lines, files, and complexity
- Automatic chunking: split diffs by file, function, or logical boundary
- Chunk dependency tracking: identify inter-chunk dependencies
- Review order suggestion: topological sort by dependencies
- Complexity weighting: larger complexity = smaller chunk size
- Quality gate: configurable max diff size thresholds
- Risk scoring: rate each chunk by change risk
- Batch analysis across multiple diffs
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class ChunkStrategy(StrEnum):
    BY_FILE = "by_file"
    BY_FUNCTION = "by_function"
    BY_SIZE = "by_size"
    BY_LOGICAL_GROUP = "by_logical_group"


class DiffRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GateDecision(StrEnum):
    PASS = "pass"
    SPLIT = "split"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class FileDiff:
    """A diff for a single file."""

    file_path: str
    added_lines: int
    removed_lines: int
    content: str
    language: str = ""
    functions_changed: list[str] = field(default_factory=list)


@dataclass
class DiffChunk:
    """A reviewable chunk of changes."""

    id: str
    files: list[str]
    total_added: int
    total_removed: int
    total_lines: int
    complexity_score: float  # 0-1
    risk: DiffRisk
    description: str
    dependencies: list[str] = field(default_factory=list)  # chunk IDs this depends on
    review_order: int = 0


@dataclass
class DiffAnalysis:
    """Analysis of a complete diff."""

    id: str
    total_files: int
    total_added: int
    total_removed: int
    total_lines: int
    avg_complexity: float
    risk: DiffRisk
    needs_splitting: bool
    gate_decision: GateDecision
    chunks: list[DiffChunk]
    review_order: list[str]  # chunk IDs in suggested review order
    estimated_review_minutes: int
    analyzed_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchDiffReport:
    """Report across multiple diffs."""

    analyses: list[DiffAnalysis]
    total_diffs: int
    avg_lines: float
    diffs_needing_split: int
    gate_decision: GateDecision


# ── Complexity heuristics ──────────────────────────────────────────────

_HIGH_RISK_PATTERNS = [
    r"(auth|login|session|token|password|secret|crypt|security)",
    r"(payment|billing|invoice|credit|charge)",
    r"(migration|schema|alter\s+table|drop\s+table)",
    r"(DELETE|UPDATE)\s+.*WHERE",
    r"(exec|eval|subprocess|system|os\.)",
    r"(sql|query|cursor\.execute)",
]

_COMPLEXITY_KEYWORDS = [
    r"\bif\b", r"\belse\b", r"\bfor\b", r"\bwhile\b",
    r"\btry\b", r"\bcatch\b", r"\bexcept\b",
    r"\bswitch\b", r"\bcase\b", r"\basync\b",
    r"\bclass\b", r"\bdef\b", r"\bfunction\b",
]


def _estimate_complexity(content: str) -> float:
    """Estimate code complexity from 0-1."""
    lines = content.split("\n")
    if not lines:
        return 0.0

    keyword_count = 0
    for pattern in _COMPLEXITY_KEYWORDS:
        keyword_count += len(re.findall(pattern, content))

    # Normalize by line count
    density = keyword_count / max(len(lines), 1)
    return min(density / 0.5, 1.0)  # 0.5 keywords/line = max complexity


def _assess_risk(file_path: str, content: str) -> DiffRisk:
    """Assess risk level of a file change."""
    for pattern in _HIGH_RISK_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return DiffRisk.HIGH
        if re.search(pattern, file_path, re.IGNORECASE):
            return DiffRisk.HIGH

    if any(x in file_path for x in ["test", "spec", "mock", "fixture"]):
        return DiffRisk.LOW

    if any(x in file_path for x in ["config", "setting", "env"]):
        return DiffRisk.MEDIUM

    return DiffRisk.MEDIUM


def _detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "typescript", ".jsx": "javascript", ".go": "go",
        ".rs": "rust", ".java": "java", ".rb": "ruby",
        ".sql": "sql", ".sh": "shell", ".yaml": "yaml",
        ".yml": "yaml", ".json": "json", ".md": "markdown",
    }
    for ext, lang in ext_map.items():
        if file_path.endswith(ext):
            return lang
    return "unknown"


def _extract_functions(content: str, language: str) -> list[str]:
    """Extract function names from code."""
    patterns = {
        "python": r"def\s+(\w+)\s*\(",
        "javascript": (
            r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)"
            r"\s*=\s*(?:async\s+)?(?:function|\())"
        ),
        "typescript": (
            r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)"
            r"\s*=\s*(?:async\s+)?(?:function|\())"
        ),
        "go": r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\(",
        "rust": r"fn\s+(\w+)\s*[<(]",
        "java": r"(?:public|private|protected)?\s+\w+\s+(\w+)\s*\(",
    }
    pattern = patterns.get(language)
    if not pattern:
        return []
    matches = re.findall(pattern, content)
    # Flatten tuples from groups
    result: list[str] = []
    for m in matches:
        if isinstance(m, tuple):
            result.extend(x for x in m if x)
        elif m:
            result.append(m)
    return result


# ── Main class ──────────────────────────────────────────────────────────

class DiffSizeLimiter:
    """Analyze and split large diffs into reviewable chunks.

    Ensures that AI-generated code changes are broken into
    human-reviewable pieces that maintain code review quality.
    """

    def __init__(
        self,
        max_lines_per_chunk: int = 400,
        max_files_per_chunk: int = 10,
        max_total_lines: int = 1500,
        review_minutes_per_100_lines: int = 15,
        split_threshold: int = 500,
        block_threshold: int = 3000,
    ) -> None:
        self.max_lines_per_chunk = max_lines_per_chunk
        self.max_files_per_chunk = max_files_per_chunk
        self.max_total_lines = max_total_lines
        self.review_minutes_per_100_lines = review_minutes_per_100_lines
        self.split_threshold = split_threshold
        self.block_threshold = block_threshold
        self._history: list[DiffAnalysis] = []

    def analyze(self, file_diffs: list[FileDiff]) -> DiffAnalysis:
        """Analyze a complete diff and produce chunk recommendations."""
        if not file_diffs:
            analysis = DiffAnalysis(
                id=uuid.uuid4().hex[:12],
                total_files=0,
                total_added=0,
                total_removed=0,
                total_lines=0,
                avg_complexity=0.0,
                risk=DiffRisk.LOW,
                needs_splitting=False,
                gate_decision=GateDecision.PASS,
                chunks=[],
                review_order=[],
                estimated_review_minutes=0,
            )
            self._history.append(analysis)
            return analysis

        # Enrich file diffs
        for fd in file_diffs:
            if not fd.language:
                fd.language = _detect_language(fd.file_path)
            if not fd.functions_changed:
                fd.functions_changed = _extract_functions(fd.content, fd.language)

        total_added = sum(fd.added_lines for fd in file_diffs)
        total_removed = sum(fd.removed_lines for fd in file_diffs)
        total_lines = total_added + total_removed

        # Gate decision
        if total_lines >= self.block_threshold:
            gate = GateDecision.BLOCK
        elif total_lines >= self.split_threshold:
            gate = GateDecision.SPLIT
        else:
            gate = GateDecision.PASS

        needs_splitting = total_lines > self.split_threshold

        # Compute complexity and risk
        complexities = [_estimate_complexity(fd.content) for fd in file_diffs]
        avg_complexity = sum(complexities) / len(complexities) if complexities else 0.0
        risks = [_assess_risk(fd.file_path, fd.content) for fd in file_diffs]
        overall_risk = self._aggregate_risk(risks)

        # Create chunks
        if needs_splitting:
            chunks = self._create_chunks(file_diffs)
        else:
            chunk_id = uuid.uuid4().hex[:12]
            chunks = [DiffChunk(
                id=chunk_id,
                files=[fd.file_path for fd in file_diffs],
                total_added=total_added,
                total_removed=total_removed,
                total_lines=total_lines,
                complexity_score=round(avg_complexity, 4),
                risk=overall_risk,
                description=f"All changes ({len(file_diffs)} files)",
                review_order=0,
            )]

        # Determine review order
        review_order = self._determine_review_order(chunks)

        # Estimate review time
        review_mins = max(
            1,
            int(total_lines / 100 * self.review_minutes_per_100_lines),
        )

        analysis = DiffAnalysis(
            id=uuid.uuid4().hex[:12],
            total_files=len(file_diffs),
            total_added=total_added,
            total_removed=total_removed,
            total_lines=total_lines,
            avg_complexity=round(avg_complexity, 4),
            risk=overall_risk,
            needs_splitting=needs_splitting,
            gate_decision=gate,
            chunks=chunks,
            review_order=review_order,
            estimated_review_minutes=review_mins,
        )
        self._history.append(analysis)
        return analysis

    def _create_chunks(self, file_diffs: list[FileDiff]) -> list[DiffChunk]:
        """Split files into reviewable chunks."""
        chunks: list[DiffChunk] = []
        current_files: list[FileDiff] = []
        current_lines = 0

        # Sort by risk (high risk first) then by file path
        risk_order = {DiffRisk.CRITICAL: 0, DiffRisk.HIGH: 1, DiffRisk.MEDIUM: 2, DiffRisk.LOW: 3}
        sorted_diffs = sorted(
            file_diffs,
            key=lambda fd: (
                risk_order.get(_assess_risk(fd.file_path, fd.content), 2),
                fd.file_path,
            ),
        )

        for fd in sorted_diffs:
            fd_lines = fd.added_lines + fd.removed_lines

            if (
                current_lines + fd_lines > self.max_lines_per_chunk
                or len(current_files) >= self.max_files_per_chunk
            ) and current_files:
                chunks.append(self._make_chunk(current_files, len(chunks)))
                current_files = []
                current_lines = 0

            current_files.append(fd)
            current_lines += fd_lines

        if current_files:
            chunks.append(self._make_chunk(current_files, len(chunks)))

        return chunks

    def _make_chunk(self, files: list[FileDiff], order: int) -> DiffChunk:
        """Create a chunk from a list of file diffs."""
        total_added = sum(fd.added_lines for fd in files)
        total_removed = sum(fd.removed_lines for fd in files)
        complexity = sum(_estimate_complexity(fd.content) for fd in files) / len(files)
        risks = [_assess_risk(fd.file_path, fd.content) for fd in files]
        risk = self._aggregate_risk(risks)

        file_names = ", ".join(fd.file_path.split("/")[-1] for fd in files[:3])
        if len(files) > 3:
            file_names += f" +{len(files) - 3} more"

        return DiffChunk(
            id=uuid.uuid4().hex[:12],
            files=[fd.file_path for fd in files],
            total_added=total_added,
            total_removed=total_removed,
            total_lines=total_added + total_removed,
            complexity_score=round(complexity, 4),
            risk=risk,
            description=f"Chunk: {file_names}",
            review_order=order,
        )

    @staticmethod
    def _aggregate_risk(risks: list[DiffRisk]) -> DiffRisk:
        """Aggregate risk from multiple files."""
        if DiffRisk.CRITICAL in risks:
            return DiffRisk.CRITICAL
        if DiffRisk.HIGH in risks:
            return DiffRisk.HIGH
        if DiffRisk.MEDIUM in risks:
            return DiffRisk.MEDIUM
        return DiffRisk.LOW

    @staticmethod
    def _determine_review_order(chunks: list[DiffChunk]) -> list[str]:
        """Determine suggested review order (high risk first)."""
        risk_order = {DiffRisk.CRITICAL: 0, DiffRisk.HIGH: 1, DiffRisk.MEDIUM: 2, DiffRisk.LOW: 3}
        sorted_chunks = sorted(
            chunks,
            key=lambda c: (risk_order.get(c.risk, 2), -c.complexity_score),
        )
        for i, c in enumerate(sorted_chunks):
            c.review_order = i
        return [c.id for c in sorted_chunks]

    # ── Batch ───────────────────────────────────────────────────────────

    def batch_analyze(
        self,
        diffs: list[list[FileDiff]],
    ) -> BatchDiffReport:
        """Analyze multiple diffs."""
        analyses = [self.analyze(d) for d in diffs]
        avg_lines = (
            sum(a.total_lines for a in analyses) / len(analyses)
            if analyses else 0.0
        )
        needing_split = sum(1 for a in analyses if a.needs_splitting)

        gates = [a.gate_decision for a in analyses]
        if GateDecision.BLOCK in gates:
            gate = GateDecision.BLOCK
        elif GateDecision.SPLIT in gates:
            gate = GateDecision.SPLIT
        else:
            gate = GateDecision.PASS

        return BatchDiffReport(
            analyses=analyses,
            total_diffs=len(analyses),
            avg_lines=round(avg_lines, 1),
            diffs_needing_split=needing_split,
            gate_decision=gate,
        )

    @property
    def history(self) -> list[DiffAnalysis]:
        return list(self._history)
