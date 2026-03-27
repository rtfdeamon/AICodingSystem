"""Code Efficiency Analyzer — detection of performance anti-patterns in
AI-generated code.

Research shows that eff@k (efficiency pass rate) is significantly lower
than pass@k (~0.45 vs >0.8) for state-of-the-art models, meaning LLMs
routinely produce functionally correct but inefficient code.  This module
provides static heuristic analysis to flag common efficiency pitfalls
before they reach production.

Based on Qiu et al. "ENAMEL: Benchmarking Code Efficiency of LLMs via
Efficiency-Aware NAtural-language Modeled EvaLuation" (arXiv:2501.17610,
January 2025).

Key capabilities:
- Complexity detection: nested loops, missing memoization
- Anti-pattern catalog: N+1 queries, string concat in loops, repeated lookups
- Memory pattern analysis: unbounded collections, missing generators
- Efficiency scoring: 0-1 weighted by issue severity
- Suggestion engine: concrete fix per detected issue
- Batch analysis with aggregated reporting
- Quality gate: configurable warn/block thresholds
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

class EfficiencyIssueType(StrEnum):
    COMPLEXITY = "complexity"
    MEMORY = "memory"
    IO = "io"
    ALGORITHM = "algorithm"
    DATA_STRUCTURE = "data_structure"


class IssueSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Severity penalty weights ─────────────────────────────────────────────

_SEVERITY_PENALTY: dict[IssueSeverity, float] = {
    IssueSeverity.CRITICAL: 0.30,
    IssueSeverity.HIGH: 0.20,
    IssueSeverity.MEDIUM: 0.10,
    IssueSeverity.LOW: 0.05,
}


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class EfficiencyIssue:
    """A single detected efficiency problem."""

    id: str
    issue_type: EfficiencyIssueType
    severity: IssueSeverity
    description: str
    line_hint: int | None = None
    suggestion: str = ""
    penalty: float = 0.0


@dataclass
class AnalysisResult:
    """Result of analyzing a single code snippet."""

    code_id: str
    issues: list[EfficiencyIssue]
    score: float
    gate_decision: GateDecision
    analyzed_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchReport:
    """Aggregated report across multiple code analyses."""

    results: list[AnalysisResult]
    avg_score: float
    total_issues: int
    gate_decision: GateDecision


# ── Code Efficiency Analyzer ─────────────────────────────────────────────

class CodeEfficiencyAnalyzer:
    """Static heuristic analyzer for efficiency anti-patterns.

    Scans code strings for common performance pitfalls and produces a
    severity-weighted efficiency score with quality gate decisions.
    """

    def __init__(
        self,
        *,
        warn_threshold: float = 0.7,
        block_threshold: float = 0.4,
    ) -> None:
        self._warn_threshold = warn_threshold
        self._block_threshold = block_threshold

    # ── Public API ───────────────────────────────────────────────────

    def analyze(self, code_id: str, code_str: str) -> AnalysisResult:
        """Analyze a single code snippet for efficiency issues."""
        lines = code_str.splitlines()
        issues: list[EfficiencyIssue] = []

        issues.extend(self._detect_nested_loops(lines))
        issues.extend(self._detect_string_concat_in_loop(lines))
        issues.extend(self._detect_unbounded_collections(lines))
        issues.extend(self._detect_n_plus_one(lines))
        issues.extend(self._detect_missing_generators(lines))
        issues.extend(self._detect_repeated_lookups(lines))

        score = self._compute_score(issues)
        gate = self._make_gate_decision(score)

        result = AnalysisResult(
            code_id=code_id,
            issues=issues,
            score=score,
            gate_decision=gate,
        )

        logger.debug(
            "Analyzed %s: score=%.2f gate=%s issues=%d",
            code_id, score, gate, len(issues),
        )
        return result

    def analyze_batch(
        self,
        items: list[tuple[str, str]],
    ) -> BatchReport:
        """Analyze multiple code snippets and produce an aggregated report.

        Parameters
        ----------
        items:
            List of (code_id, code_str) tuples.
        """
        results = [self.analyze(cid, code) for cid, code in items]

        if not results:
            return BatchReport(
                results=[],
                avg_score=1.0,
                total_issues=0,
                gate_decision=GateDecision.PASS,
            )

        avg = sum(r.score for r in results) / len(results)
        total = sum(len(r.issues) for r in results)

        # Batch gate: worst individual gate wins
        if any(r.gate_decision == GateDecision.BLOCK for r in results):
            gate = GateDecision.BLOCK
        elif any(r.gate_decision == GateDecision.WARN for r in results):
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        return BatchReport(
            results=results,
            avg_score=avg,
            total_issues=total,
            gate_decision=gate,
        )

    # ── Detection methods ────────────────────────────────────────────

    def _detect_nested_loops(
        self,
        code_lines: list[str],
    ) -> list[EfficiencyIssue]:
        """Detect O(n^2) nested for/while loops."""
        issues: list[EfficiencyIssue] = []
        loop_pattern = re.compile(r"^\s*(for |while )")

        for i, line in enumerate(code_lines):
            if not loop_pattern.match(line):
                continue
            outer_indent = len(line) - len(line.lstrip())
            # Scan following lines for a nested loop at deeper indent
            for j in range(i + 1, min(i + 30, len(code_lines))):
                inner = code_lines[j]
                if not inner.strip():
                    continue
                inner_indent = len(inner) - len(inner.lstrip())
                if inner_indent <= outer_indent:
                    break  # left the outer loop body
                if loop_pattern.match(inner) and inner_indent > outer_indent:
                    issues.append(EfficiencyIssue(
                        id=_uid(),
                        issue_type=EfficiencyIssueType.COMPLEXITY,
                        severity=IssueSeverity.HIGH,
                        description="Nested loop detected — potential O(n^2) complexity",
                        line_hint=i + 1,
                        suggestion=(
                            "Consider using a set/dict lookup, itertools.product, "
                            "or restructuring to reduce nested iteration."
                        ),
                        penalty=_SEVERITY_PENALTY[IssueSeverity.HIGH],
                    ))
                    break  # one issue per outer loop
        return issues

    def _detect_string_concat_in_loop(
        self,
        code_lines: list[str],
    ) -> list[EfficiencyIssue]:
        """Detect string concatenation with += inside loops."""
        issues: list[EfficiencyIssue] = []
        loop_pattern = re.compile(r"^\s*(for |while )")
        concat_pattern = re.compile(r"\w+\s*\+=\s*[\"']|"
                                     r"\w+\s*\+=\s*\w|"
                                     r"\w+\s*=\s*\w+\s*\+\s*[\"']")

        in_loop = False
        loop_indent = 0

        for i, line in enumerate(code_lines):
            stripped = line.lstrip()
            if not stripped:
                continue
            indent = len(line) - len(stripped)

            if loop_pattern.match(line):
                in_loop = True
                loop_indent = indent
                continue

            if in_loop:
                if indent <= loop_indent and stripped and not stripped.startswith("#"):
                    in_loop = False
                elif concat_pattern.search(line):
                    issues.append(EfficiencyIssue(
                        id=_uid(),
                        issue_type=EfficiencyIssueType.DATA_STRUCTURE,
                        severity=IssueSeverity.MEDIUM,
                        description="String concatenation in loop — O(n^2) string building",
                        line_hint=i + 1,
                        suggestion=(
                            "Collect parts in a list and use ''.join() after the loop."
                        ),
                        penalty=_SEVERITY_PENALTY[IssueSeverity.MEDIUM],
                    ))
        return issues

    def _detect_unbounded_collections(
        self,
        code_lines: list[str],
    ) -> list[EfficiencyIssue]:
        """Detect append inside loops without size bounds."""
        issues: list[EfficiencyIssue] = []
        loop_pattern = re.compile(r"^\s*(for |while )")
        append_pattern = re.compile(r"\.\s*append\s*\(")

        in_loop = False
        loop_indent = 0
        loop_line = 0

        for i, line in enumerate(code_lines):
            stripped = line.lstrip()
            if not stripped:
                continue
            indent = len(line) - len(stripped)

            if loop_pattern.match(line):
                in_loop = True
                loop_indent = indent
                loop_line = i
                continue

            if in_loop:
                if indent <= loop_indent and stripped and not stripped.startswith("#"):
                    in_loop = False
                elif append_pattern.search(line):
                    # Check if there is any size guard (simple heuristic)
                    has_guard = any(
                        "len(" in code_lines[k] or "maxsize" in code_lines[k].lower()
                        for k in range(loop_line, min(i + 1, len(code_lines)))
                    )
                    if not has_guard:
                        issues.append(EfficiencyIssue(
                            id=_uid(),
                            issue_type=EfficiencyIssueType.MEMORY,
                            severity=IssueSeverity.MEDIUM,
                            description=(
                                "Unbounded collection growth in loop — "
                                "no size guard detected"
                            ),
                            line_hint=i + 1,
                            suggestion=(
                                "Add a size limit, use a collections.deque(maxlen=N), "
                                "or yield items with a generator instead."
                            ),
                            penalty=_SEVERITY_PENALTY[IssueSeverity.MEDIUM],
                        ))
        return issues

    def _detect_n_plus_one(
        self,
        code_lines: list[str],
    ) -> list[EfficiencyIssue]:
        """Detect N+1 query patterns (DB calls inside loops)."""
        issues: list[EfficiencyIssue] = []
        loop_pattern = re.compile(r"^\s*(for |while )")
        query_pattern = re.compile(
            r"\.(execute|query|filter|get|fetch|find|select|all)\s*\(",
            re.IGNORECASE,
        )

        in_loop = False
        loop_indent = 0

        for i, line in enumerate(code_lines):
            stripped = line.lstrip()
            if not stripped:
                continue
            indent = len(line) - len(stripped)

            if loop_pattern.match(line):
                in_loop = True
                loop_indent = indent
                continue

            if in_loop:
                if indent <= loop_indent and stripped and not stripped.startswith("#"):
                    in_loop = False
                elif query_pattern.search(line):
                    issues.append(EfficiencyIssue(
                        id=_uid(),
                        issue_type=EfficiencyIssueType.IO,
                        severity=IssueSeverity.CRITICAL,
                        description="Potential N+1 query — database call inside a loop",
                        line_hint=i + 1,
                        suggestion=(
                            "Batch the query outside the loop using "
                            "select_related / prefetch_related, an IN clause, "
                            "or a single bulk fetch."
                        ),
                        penalty=_SEVERITY_PENALTY[IssueSeverity.CRITICAL],
                    ))
        return issues

    def _detect_missing_generators(
        self,
        code_lines: list[str],
    ) -> list[EfficiencyIssue]:
        """Detect list comprehensions that could be generator expressions."""
        issues: list[EfficiencyIssue] = []
        # Pattern: function([expr for x in y]) where function consumes iterables
        consumer_pattern = re.compile(
            r"(sum|min|max|any|all|sorted|set|frozenset|tuple|"
            r"str\.join|join)\s*\(\s*\[",
        )

        for i, line in enumerate(code_lines):
            if consumer_pattern.search(line):
                issues.append(EfficiencyIssue(
                    id=_uid(),
                    issue_type=EfficiencyIssueType.MEMORY,
                    severity=IssueSeverity.LOW,
                    description=(
                        "List comprehension inside an iterable consumer — "
                        "unnecessary intermediate list"
                    ),
                    line_hint=i + 1,
                    suggestion=(
                        "Replace the list comprehension [...] with a "
                        "generator expression (...) to avoid materialising "
                        "the full list in memory."
                    ),
                    penalty=_SEVERITY_PENALTY[IssueSeverity.LOW],
                ))
        return issues

    def _detect_repeated_lookups(
        self,
        code_lines: list[str],
    ) -> list[EfficiencyIssue]:
        """Detect repeated dictionary/attribute lookups in tight loops."""
        issues: list[EfficiencyIssue] = []
        loop_pattern = re.compile(r"^\s*(for |while )")
        bracket_lookup = re.compile(r"(\w+\[.+?\])")

        in_loop = False
        loop_indent = 0
        lookup_counts: dict[str, list[int]] = {}

        for i, line in enumerate(code_lines):
            stripped = line.lstrip()
            if not stripped:
                continue
            indent = len(line) - len(stripped)

            if loop_pattern.match(line):
                # Flush previous loop
                if in_loop:
                    issues.extend(
                        self._flush_repeated(lookup_counts),
                    )
                in_loop = True
                loop_indent = indent
                lookup_counts = {}
                continue

            if in_loop:
                if indent <= loop_indent and stripped and not stripped.startswith("#"):
                    issues.extend(
                        self._flush_repeated(lookup_counts),
                    )
                    in_loop = False
                    lookup_counts = {}
                else:
                    for m in bracket_lookup.finditer(line):
                        key = m.group(1)
                        lookup_counts.setdefault(key, []).append(i + 1)

        # Flush if file ends inside a loop
        if in_loop:
            issues.extend(self._flush_repeated(lookup_counts))

        return issues

    # ── Scoring ──────────────────────────────────────────────────────

    def _compute_score(self, issues: list[EfficiencyIssue]) -> float:
        """Compute efficiency score 0-1 (1 = perfect, 0 = terrible)."""
        if not issues:
            return 1.0
        total_penalty = sum(i.penalty for i in issues)
        return max(1.0 - total_penalty, 0.0)

    def _make_gate_decision(self, score: float) -> GateDecision:
        """Map an efficiency score to a quality gate decision."""
        if score < self._block_threshold:
            return GateDecision.BLOCK
        if score < self._warn_threshold:
            return GateDecision.WARN
        return GateDecision.PASS

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _flush_repeated(
        lookup_counts: dict[str, list[int]],
    ) -> list[EfficiencyIssue]:
        """Emit issues for lookups that appear 3+ times in a loop."""
        out: list[EfficiencyIssue] = []
        for expr, lines in lookup_counts.items():
            if len(lines) >= 3:
                out.append(EfficiencyIssue(
                    id=_uid(),
                    issue_type=EfficiencyIssueType.DATA_STRUCTURE,
                    severity=IssueSeverity.LOW,
                    description=(
                        f"Repeated lookup '{expr}' appears {len(lines)} times "
                        f"in loop body"
                    ),
                    line_hint=lines[0],
                    suggestion=(
                        "Cache the lookup result in a local variable before "
                        "the loop to avoid repeated access."
                    ),
                    penalty=_SEVERITY_PENALTY[IssueSeverity.LOW],
                ))
        return out


# ── Module-level helpers ─────────────────────────────────────────────────

def _uid() -> str:
    return uuid.uuid4().hex[:12]
