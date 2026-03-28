"""Non-Functional Quality Assessor — ISO/IEC 25010 quality model for AI code.

AI-generated code often passes functional tests but accumulates technical
debt through poor maintainability, readability, and performance. This
module scores code against non-functional quality characteristics (NFQCs)
from the ISO/IEC 25010 standard, catching "silent quality rot" that
functional tests miss.

Based on:
- ISO/IEC 25010:2023 Software Quality Model
- arXiv 2511.10271 "Quality Assurance of LLM-generated Code: NFQCs" (2025)
- arXiv 2505.13766 "Standards-Focused Review of LLM-Based SQA" (2025)
- Addy Osmani "My LLM Coding Workflow Going into 2026" (Medium)
- ContextQA "LLM Testing Tools and Frameworks 2026"

Key capabilities:
- Six NFQC dimensions: maintainability, readability, performance, security,
  reliability, and testability
- Heuristic-based scoring per dimension (0-1)
- Pattern-based detection of AI-typical code smells
- Aggregate quality profile with radar-chart data
- Comparison: AI-generated vs human baseline
- Quality gate: exemplary / acceptable / needs_improvement / poor
- Batch assessment across multiple code samples
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

class QualityGrade(StrEnum):
    EXEMPLARY = "exemplary"          # >= 0.85
    ACCEPTABLE = "acceptable"        # >= 0.65
    NEEDS_IMPROVEMENT = "needs_improvement"  # >= 0.45
    POOR = "poor"                    # < 0.45


class NFQCDimension(StrEnum):
    MAINTAINABILITY = "maintainability"
    READABILITY = "readability"
    PERFORMANCE = "performance"
    SECURITY = "security"
    RELIABILITY = "reliability"
    TESTABILITY = "testability"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class CodeOrigin(StrEnum):
    AI_GENERATED = "ai_generated"
    HUMAN_WRITTEN = "human_written"
    UNKNOWN = "unknown"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class DimensionResult:
    """Score for a single NFQC dimension."""

    dimension: NFQCDimension
    score: float  # 0-1
    issues: list[str] = field(default_factory=list)
    details: str = ""


@dataclass
class AssessmentConfig:
    """Configuration for quality assessment."""

    exemplary_threshold: float = 0.85
    acceptable_threshold: float = 0.65
    needs_improvement_threshold: float = 0.45
    max_function_length: int = 50  # lines
    max_cyclomatic_complexity: int = 10
    max_nesting_depth: int = 4
    max_parameter_count: int = 5
    dimension_weights: dict[str, float] = field(default_factory=lambda: {
        "maintainability": 0.25,
        "readability": 0.20,
        "performance": 0.15,
        "security": 0.15,
        "reliability": 0.15,
        "testability": 0.10,
    })


@dataclass
class CodeSample:
    """A code sample to assess."""

    sample_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    code: str = ""
    language: str = "python"
    origin: CodeOrigin = CodeOrigin.UNKNOWN
    filename: str = ""


@dataclass
class AssessmentResult:
    """Complete assessment of a code sample."""

    sample_id: str = ""
    dimensions: list[DimensionResult] = field(default_factory=list)
    composite_score: float = 0.0
    grade: QualityGrade = QualityGrade.POOR
    gate: GateDecision = GateDecision.BLOCK
    ai_smell_count: int = 0
    origin: CodeOrigin = CodeOrigin.UNKNOWN
    assessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class BatchAssessmentReport:
    """Batch assessment across multiple code samples."""

    results: list[AssessmentResult] = field(default_factory=list)
    avg_score: float = 0.0
    grade_distribution: dict[str, int] = field(default_factory=dict)
    weakest_dimension: str = ""
    strongest_dimension: str = ""
    total_ai_smells: int = 0
    ai_vs_human_delta: float = 0.0  # positive = AI better


# ── AI-typical code smell patterns ───────────────────────────────────────

AI_CODE_SMELLS = [
    (r"# TODO|# FIXME|# HACK|# XXX", "unresolved_marker"),
    (r"pass\s*$", "empty_pass_block"),
    (r"except\s*:", "bare_except"),
    (r"except Exception:", "broad_except"),
    (r"import \*", "wildcard_import"),
    (r"print\(", "debug_print"),
    (r"\.format\(", "old_style_format"),
    (r"type:\s*ignore", "type_ignore_comment"),
    (r"noqa", "noqa_suppression"),
    (r"Any\b", "any_type_usage"),
]

# Security-sensitive patterns
SECURITY_PATTERNS = [
    (r"eval\(", "eval_usage"),
    (r"exec\(", "exec_usage"),
    (r"subprocess\.call\(.*shell\s*=\s*True", "shell_injection_risk"),
    (r"os\.system\(", "os_system_usage"),
    (r"password\s*=\s*['\"]", "hardcoded_password"),
    (r"secret\s*=\s*['\"]", "hardcoded_secret"),
]


# ── Pure helpers ─────────────────────────────────────────────────────────

def _count_lines(code: str) -> int:
    """Count non-empty, non-comment lines."""
    lines = code.strip().split("\n")
    return sum(1 for line in lines if line.strip() and not line.strip().startswith("#"))


def _estimate_cyclomatic_complexity(code: str) -> int:
    """Estimate cyclomatic complexity via branch keyword counting."""
    branch_keywords = [r"\bif\b", r"\belif\b", r"\bfor\b", r"\bwhile\b",
                       r"\bexcept\b", r"\band\b", r"\bor\b"]
    complexity = 1  # base
    for pattern in branch_keywords:
        complexity += len(re.findall(pattern, code))
    return complexity


def _max_nesting_depth(code: str) -> int:
    """Estimate max nesting depth from indentation."""
    max_depth = 0
    for line in code.split("\n"):
        stripped = line.rstrip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        depth = indent // 4  # assume 4-space indent
        max_depth = max(max_depth, depth)
    return max_depth


def _count_functions(code: str) -> int:
    """Count function definitions."""
    return len(re.findall(r"^\s*def \w+", code, re.MULTILINE))


def _avg_function_length(code: str) -> float:
    """Estimate average function length in lines."""
    functions = re.split(r"^\s*def \w+", code, flags=re.MULTILINE)
    if len(functions) <= 1:
        return _count_lines(code)
    lengths = [_count_lines(f) for f in functions[1:]]
    return sum(lengths) / len(lengths) if lengths else 0


def _count_pattern_matches(code: str, patterns: list[tuple[str, str]]) -> list[str]:
    """Count matches for a list of (regex, name) patterns."""
    found: list[str] = []
    for pattern, name in patterns:
        if re.search(pattern, code, re.MULTILINE):
            found.append(name)
    return found


def _score_maintainability(code: str, config: AssessmentConfig) -> DimensionResult:
    """Score maintainability: function length, complexity, nesting."""
    issues: list[str] = []
    score = 1.0

    avg_len = _avg_function_length(code)
    if avg_len > config.max_function_length:
        score -= 0.25
        issues.append(f"avg function length {avg_len:.0f} > {config.max_function_length}")

    complexity = _estimate_cyclomatic_complexity(code)
    if complexity > config.max_cyclomatic_complexity:
        penalty = min(0.3, (complexity - config.max_cyclomatic_complexity) * 0.03)
        score -= penalty
        issues.append(f"cyclomatic complexity {complexity} > {config.max_cyclomatic_complexity}")

    nesting = _max_nesting_depth(code)
    if nesting > config.max_nesting_depth:
        score -= 0.2
        issues.append(f"max nesting depth {nesting} > {config.max_nesting_depth}")

    return DimensionResult(
        dimension=NFQCDimension.MAINTAINABILITY,
        score=round(max(0.0, score), 4),
        issues=issues,
        details=f"avg_fn_len={avg_len:.0f}, complexity={complexity}, nesting={nesting}",
    )


def _score_readability(code: str, _config: AssessmentConfig) -> DimensionResult:
    """Score readability: naming, comments, structure."""
    issues: list[str] = []
    score = 1.0

    lines = code.strip().split("\n")
    total = len(lines) if lines else 1

    # Comment density: 5-25% is ideal
    comment_lines = sum(1 for ln in lines if ln.strip().startswith("#"))
    comment_ratio = comment_lines / total
    if comment_ratio < 0.03:
        score -= 0.15
        issues.append("very low comment density")
    elif comment_ratio > 0.40:
        score -= 0.10
        issues.append("excessive comments")

    # Short variable names (single char not in loop)
    single_char_vars = re.findall(r"\b([a-z])\s*=", code)
    loop_vars = re.findall(r"for\s+([a-z])\s+in", code)
    non_loop_singles = set(single_char_vars) - set(loop_vars) - {"_"}
    if len(non_loop_singles) > 3:
        score -= 0.15
        issues.append(f"{len(non_loop_singles)} single-char variable names")

    # Long lines
    long_lines = sum(1 for ln in lines if len(ln) > 120)
    if long_lines > 3:
        score -= 0.10
        issues.append(f"{long_lines} lines > 120 chars")

    return DimensionResult(
        dimension=NFQCDimension.READABILITY,
        score=round(max(0.0, score), 4),
        issues=issues,
    )


def _score_performance(code: str, _config: AssessmentConfig) -> DimensionResult:
    """Score performance: anti-patterns like nested loops, repeated concatenation."""
    issues: list[str] = []
    score = 1.0

    # Nested loops
    nested_for = re.findall(r"for\b.*:\s*\n\s+for\b", code)
    if nested_for:
        score -= 0.20
        issues.append(f"{len(nested_for)} nested loops detected")

    # String concatenation in loop
    if re.search(r"for\b.*:.*\+=\s*['\"]", code, re.DOTALL):
        score -= 0.15
        issues.append("string concatenation in loop")

    # Global variable usage
    global_refs = re.findall(r"\bglobal\b", code)
    if global_refs:
        score -= 0.10
        issues.append(f"{len(global_refs)} global declarations")

    return DimensionResult(
        dimension=NFQCDimension.PERFORMANCE,
        score=round(max(0.0, score), 4),
        issues=issues,
    )


def _score_security(code: str, _config: AssessmentConfig) -> DimensionResult:
    """Score security: dangerous patterns."""
    found = _count_pattern_matches(code, SECURITY_PATTERNS)
    score = max(0.0, 1.0 - len(found) * 0.20)
    return DimensionResult(
        dimension=NFQCDimension.SECURITY,
        score=round(score, 4),
        issues=found,
    )


def _score_reliability(code: str, _config: AssessmentConfig) -> DimensionResult:
    """Score reliability: error handling, bare excepts, assertions."""
    issues: list[str] = []
    score = 1.0

    if re.search(r"except\s*:", code):
        score -= 0.25
        issues.append("bare except clause")

    if re.search(r"except Exception:", code):
        score -= 0.10
        issues.append("broad except Exception")

    # No error handling at all
    func_count = _count_functions(code)
    try_count = len(re.findall(r"\btry\b:", code))
    if func_count > 3 and try_count == 0:
        score -= 0.15
        issues.append("no error handling in multi-function code")

    return DimensionResult(
        dimension=NFQCDimension.RELIABILITY,
        score=round(max(0.0, score), 4),
        issues=issues,
    )


def _score_testability(code: str, config: AssessmentConfig) -> DimensionResult:
    """Score testability: dependency injection, function size, global state."""
    issues: list[str] = []
    score = 1.0

    # Functions with too many parameters
    params = re.findall(r"def \w+\(([^)]*)\)", code)
    for p in params:
        param_count = len([x for x in p.split(",") if x.strip() and x.strip() != "self"])
        if param_count > config.max_parameter_count:
            score -= 0.15
            issues.append(
                f"function with {param_count} params (max {config.max_parameter_count})"
            )
            break

    # Class-level mutable state
    class_vars = re.findall(r"^\s+\w+\s*:\s*list|^\s+\w+\s*=\s*\[", code, re.MULTILINE)
    if len(class_vars) > 3:
        score -= 0.10
        issues.append("excessive mutable class state")

    # Global functions with side effects (writes to files, network)
    side_effects = re.findall(r"open\(|requests\.|urllib\.", code)
    if side_effects:
        score -= 0.15
        issues.append("functions with I/O side effects")

    return DimensionResult(
        dimension=NFQCDimension.TESTABILITY,
        score=round(max(0.0, score), 4),
        issues=issues,
    )


# ── Main class ───────────────────────────────────────────────────────────

class NonFunctionalQualityAssessor:
    """Assesses code against ISO/IEC 25010 non-functional quality characteristics."""

    def __init__(self, config: AssessmentConfig | None = None) -> None:
        self._config = config or AssessmentConfig()
        self._results: list[AssessmentResult] = []

    @property
    def config(self) -> AssessmentConfig:
        return self._config

    def assess(self, sample: CodeSample) -> AssessmentResult:
        """Assess a code sample across all NFQC dimensions."""
        code = sample.code
        if not code.strip():
            result = AssessmentResult(
                sample_id=sample.sample_id,
                composite_score=0.0,
                grade=QualityGrade.POOR,
                gate=GateDecision.BLOCK,
                origin=sample.origin,
            )
            self._results.append(result)
            return result

        dimensions = [
            _score_maintainability(code, self._config),
            _score_readability(code, self._config),
            _score_performance(code, self._config),
            _score_security(code, self._config),
            _score_reliability(code, self._config),
            _score_testability(code, self._config),
        ]

        # Weighted composite
        weights = self._config.dimension_weights
        total_weight = sum(weights.values())
        composite = sum(
            d.score * weights.get(d.dimension, 0.0) for d in dimensions
        )
        if total_weight > 0:
            composite /= total_weight

        # AI smells
        ai_smells = _count_pattern_matches(code, AI_CODE_SMELLS)

        grade = _grade_score(composite, self._config)
        gate = _grade_to_gate(grade)

        result = AssessmentResult(
            sample_id=sample.sample_id,
            dimensions=dimensions,
            composite_score=round(composite, 4),
            grade=grade,
            gate=gate,
            ai_smell_count=len(ai_smells),
            origin=sample.origin,
        )
        self._results.append(result)
        return result

    def batch_report(self) -> BatchAssessmentReport:
        """Generate batch report across all assessed samples."""
        if not self._results:
            return BatchAssessmentReport()

        avg = sum(r.composite_score for r in self._results) / len(self._results)

        grade_dist: dict[str, int] = {}
        for r in self._results:
            grade_dist[r.grade] = grade_dist.get(r.grade, 0) + 1

        # Find weakest/strongest dimension across all results
        dim_scores: dict[str, list[float]] = {}
        for r in self._results:
            for d in r.dimensions:
                dim_scores.setdefault(d.dimension, []).append(d.score)

        dim_avgs = {k: sum(v) / len(v) for k, v in dim_scores.items()} if dim_scores else {}
        weakest = min(dim_avgs, key=dim_avgs.get) if dim_avgs else ""
        strongest = max(dim_avgs, key=dim_avgs.get) if dim_avgs else ""

        # AI vs human comparison
        ai_scores = [
            r.composite_score for r in self._results
            if r.origin == CodeOrigin.AI_GENERATED
        ]
        human_scores = [
            r.composite_score for r in self._results
            if r.origin == CodeOrigin.HUMAN_WRITTEN
        ]
        delta = 0.0
        if ai_scores and human_scores:
            delta = (sum(ai_scores) / len(ai_scores)) - (sum(human_scores) / len(human_scores))

        return BatchAssessmentReport(
            results=self._results,
            avg_score=round(avg, 4),
            grade_distribution=grade_dist,
            weakest_dimension=weakest,
            strongest_dimension=strongest,
            total_ai_smells=sum(r.ai_smell_count for r in self._results),
            ai_vs_human_delta=round(delta, 4),
        )


# ── Module-level helpers ─────────────────────────────────────────────────

def _grade_score(score: float, config: AssessmentConfig) -> QualityGrade:
    """Assign grade based on composite score."""
    if score >= config.exemplary_threshold:
        return QualityGrade.EXEMPLARY
    if score >= config.acceptable_threshold:
        return QualityGrade.ACCEPTABLE
    if score >= config.needs_improvement_threshold:
        return QualityGrade.NEEDS_IMPROVEMENT
    return QualityGrade.POOR


def _grade_to_gate(grade: QualityGrade) -> GateDecision:
    """Map grade to gate decision."""
    if grade in (QualityGrade.EXEMPLARY, QualityGrade.ACCEPTABLE):
        return GateDecision.PASS
    if grade == QualityGrade.NEEDS_IMPROVEMENT:
        return GateDecision.WARN
    return GateDecision.BLOCK
