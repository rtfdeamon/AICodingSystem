"""Regression Test Guard — detect regressions in LLM-generated code across
model versions, prompt changes, and code iterations.

Research shows that LLM test generation relies heavily on surface-level cues
and struggles to maintain regression awareness as programs evolve. Pass rates
of newly generated tests drop to 66% under semantic-altering changes, with
99%+ of failures caused by residual alignment to original behavior.

Based on Yang et al. "ReCatcher: Towards LLMs Regression Testing for Code
Generation" (arXiv:2507.19390, July 2025) and Chen et al. "Evaluating
LLM-Based Test Generation Under Software Evolution" (arXiv:2603.23443,
March 2026).

Key capabilities:
- Behavioral fingerprinting: hash-based signatures of code behavior
- Semantic diff detection: distinguish semantic-altering from cosmetic changes
- Regression detection: compare outputs across code versions
- Regression scoring: weighted by severity and affected functionality
- History tracking: full audit of all versions and regressions found
- Quality gate: configurable regression tolerance
- Batch regression scanning across multiple code pairs
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class ChangeType(StrEnum):
    SEMANTIC_ALTERING = "semantic_altering"
    SEMANTIC_PRESERVING = "semantic_preserving"
    COSMETIC = "cosmetic"
    UNKNOWN = "unknown"


class RegressionSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Severity weights ────────────────────────────────────────────────────

_SEVERITY_WEIGHT: dict[RegressionSeverity, float] = {
    RegressionSeverity.CRITICAL: 1.0,
    RegressionSeverity.HIGH: 0.7,
    RegressionSeverity.MEDIUM: 0.4,
    RegressionSeverity.LOW: 0.15,
}


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class CodeFingerprint:
    """Behavioral fingerprint of a code version."""

    version_id: str
    structural_hash: str
    normalized_hash: str
    function_signatures: list[str]
    import_set: frozenset[str]
    line_count: int
    complexity_estimate: int
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class RegressionFinding:
    """A detected regression between two code versions."""

    id: str
    severity: RegressionSeverity
    description: str
    change_type: ChangeType
    affected_functions: list[str]
    old_snippet: str = ""
    new_snippet: str = ""

    @property
    def weight(self) -> float:
        return _SEVERITY_WEIGHT.get(self.severity, 0.3)


@dataclass
class ComparisonResult:
    """Result of comparing two code versions."""

    old_version: str
    new_version: str
    change_type: ChangeType
    diff_ratio: float
    regressions: list[RegressionFinding]
    regression_score: float
    gate_decision: GateDecision
    functions_added: list[str] = field(default_factory=list)
    functions_removed: list[str] = field(default_factory=list)
    functions_modified: list[str] = field(default_factory=list)
    compared_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchRegressionReport:
    """Aggregated report across multiple comparisons."""

    results: list[ComparisonResult]
    total_regressions: int
    avg_regression_score: float
    gate_decision: GateDecision


# ── Function extraction patterns ─────────────────────────────────────────

_FUNC_DEF_PATTERN = re.compile(
    r"^(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)",
    re.MULTILINE,
)

_CLASS_DEF_PATTERN = re.compile(
    r"^class\s+(\w+)\s*(?:\([^)]*\))?\s*:",
    re.MULTILINE,
)

_IMPORT_PATTERN = re.compile(
    r"^(?:from\s+(\S+)\s+)?import\s+(.+)$",
    re.MULTILINE,
)

_COMMENT_PATTERN = re.compile(r"#.*$", re.MULTILINE)
_DOCSTRING_PATTERN = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')
_WHITESPACE_PATTERN = re.compile(r"\s+")


# ── Main class ──────────────────────────────────────────────────────────

class RegressionTestGuard:
    """Detect regressions in LLM-generated code across versions.

    Compares code fingerprints, detects semantic changes, and flags
    potential regressions based on structural and behavioral analysis.
    """

    __test__ = False

    def __init__(
        self,
        block_threshold: float = 0.5,
        warn_threshold: float = 0.2,
        min_diff_for_semantic: float = 0.05,
    ) -> None:
        self.block_threshold = block_threshold
        self.warn_threshold = warn_threshold
        self.min_diff_for_semantic = min_diff_for_semantic
        self._history: list[ComparisonResult] = []

    # ── Fingerprinting ───────────────────────────────────────────────────

    def fingerprint(self, version_id: str, code: str) -> CodeFingerprint:
        """Create a behavioral fingerprint of a code version."""
        normalized = self._normalize_code(code)
        functions = self._extract_functions(code)
        imports = self._extract_imports(code)
        complexity = self._estimate_complexity(code)

        return CodeFingerprint(
            version_id=version_id,
            structural_hash=hashlib.sha256(code.encode()).hexdigest()[:16],
            normalized_hash=hashlib.sha256(normalized.encode()).hexdigest()[:16],
            function_signatures=functions,
            import_set=frozenset(imports),
            line_count=len(code.strip().splitlines()),
            complexity_estimate=complexity,
        )

    def _normalize_code(self, code: str) -> str:
        """Normalize code by removing comments, docstrings, whitespace."""
        result = _DOCSTRING_PATTERN.sub("", code)
        result = _COMMENT_PATTERN.sub("", result)
        result = _WHITESPACE_PATTERN.sub(" ", result).strip()
        return result

    def _extract_functions(self, code: str) -> list[str]:
        """Extract function signatures from code."""
        sigs: list[str] = []
        for m in _FUNC_DEF_PATTERN.finditer(code):
            name = m.group(1)
            params = m.group(2).strip()
            sigs.append(f"{name}({params})")
        return sorted(sigs)

    def _extract_imports(self, code: str) -> list[str]:
        """Extract import statements."""
        imports: list[str] = []
        for m in _IMPORT_PATTERN.finditer(code):
            module = m.group(1) or ""
            names = m.group(2).strip()
            if module:
                imports.append(f"from {module} import {names}")
            else:
                imports.append(f"import {names}")
        return sorted(imports)

    def _estimate_complexity(self, code: str) -> int:
        """Rough cyclomatic complexity estimate."""
        keywords = ["if ", "elif ", "else:", "for ", "while ", "except ",
                     "with ", "and ", "or ", "try:", "finally:"]
        complexity = 1
        for line in code.splitlines():
            stripped = line.strip()
            for kw in keywords:
                if stripped.startswith(kw) or f" {kw}" in stripped:
                    complexity += 1
                    break
        return complexity

    # ── Change classification ────────────────────────────────────────────

    def classify_change(
        self,
        old_fp: CodeFingerprint,
        new_fp: CodeFingerprint,
        old_code: str,
        new_code: str,
    ) -> ChangeType:
        """Classify the type of change between two versions."""
        if old_fp.structural_hash == new_fp.structural_hash:
            return ChangeType.COSMETIC

        if old_fp.normalized_hash == new_fp.normalized_hash:
            return ChangeType.COSMETIC

        diff_ratio = 1.0 - difflib.SequenceMatcher(
            None, old_code, new_code,
        ).ratio()

        if diff_ratio < self.min_diff_for_semantic:
            return ChangeType.SEMANTIC_PRESERVING

        # Check if function signatures changed
        old_funcs = set(old_fp.function_signatures)
        new_funcs = set(new_fp.function_signatures)

        if old_funcs != new_funcs:
            return ChangeType.SEMANTIC_ALTERING

        # Check if imports changed significantly
        if old_fp.import_set != new_fp.import_set:
            added = new_fp.import_set - old_fp.import_set
            removed = old_fp.import_set - new_fp.import_set
            if added or removed:
                return ChangeType.SEMANTIC_ALTERING

        # If normalized hashes differ but no structural change detected
        return ChangeType.SEMANTIC_PRESERVING

    # ── Regression detection ─────────────────────────────────────────────

    def detect_regressions(
        self,
        old_code: str,
        new_code: str,
        old_fp: CodeFingerprint,
        new_fp: CodeFingerprint,
    ) -> list[RegressionFinding]:
        """Detect potential regressions between two versions."""
        regressions: list[RegressionFinding] = []

        # Check for removed functions
        old_funcs = {f.split("(")[0]: f for f in old_fp.function_signatures}
        new_funcs = {f.split("(")[0]: f for f in new_fp.function_signatures}

        removed = set(old_funcs.keys()) - set(new_funcs.keys())
        for fn in removed:
            regressions.append(RegressionFinding(
                id=uuid.uuid4().hex[:12],
                severity=RegressionSeverity.HIGH,
                description=f"Function '{fn}' was removed",
                change_type=ChangeType.SEMANTIC_ALTERING,
                affected_functions=[fn],
            ))

        # Check for changed signatures
        common = set(old_funcs.keys()) & set(new_funcs.keys())
        for fn in common:
            if old_funcs[fn] != new_funcs[fn]:
                regressions.append(RegressionFinding(
                    id=uuid.uuid4().hex[:12],
                    severity=RegressionSeverity.MEDIUM,
                    description=(
                        f"Function '{fn}' signature changed: "
                        f"{old_funcs[fn]} -> {new_funcs[fn]}"
                    ),
                    change_type=ChangeType.SEMANTIC_ALTERING,
                    affected_functions=[fn],
                ))

        # Check for removed imports
        removed_imports = old_fp.import_set - new_fp.import_set
        if removed_imports:
            regressions.append(RegressionFinding(
                id=uuid.uuid4().hex[:12],
                severity=RegressionSeverity.MEDIUM,
                description=f"Removed imports: {', '.join(sorted(removed_imports))}",
                change_type=ChangeType.SEMANTIC_ALTERING,
                affected_functions=[],
            ))

        # Check for significant complexity reduction (might indicate lost logic)
        if old_fp.complexity_estimate > 0:
            reduction = 1.0 - (new_fp.complexity_estimate / old_fp.complexity_estimate)
            if reduction > 0.5:
                regressions.append(RegressionFinding(
                    id=uuid.uuid4().hex[:12],
                    severity=RegressionSeverity.LOW,
                    description=(
                        f"Significant complexity reduction ({old_fp.complexity_estimate}"
                        f" -> {new_fp.complexity_estimate}), possible lost logic"
                    ),
                    change_type=ChangeType.SEMANTIC_ALTERING,
                    affected_functions=[],
                ))

        # Check for significant line count reduction
        if old_fp.line_count > 0:
            line_reduction = 1.0 - (new_fp.line_count / old_fp.line_count)
            if line_reduction > 0.3 and old_fp.line_count > 10:
                regressions.append(RegressionFinding(
                    id=uuid.uuid4().hex[:12],
                    severity=RegressionSeverity.LOW,
                    description=(
                        f"Significant code reduction ({old_fp.line_count}"
                        f" -> {new_fp.line_count} lines), review for lost functionality"
                    ),
                    change_type=ChangeType.SEMANTIC_ALTERING,
                    affected_functions=[],
                ))

        return regressions

    # ── Comparison ───────────────────────────────────────────────────────

    def compare(
        self,
        old_version: str,
        new_version: str,
        old_code: str,
        new_code: str,
    ) -> ComparisonResult:
        """Compare two code versions and detect regressions."""
        old_fp = self.fingerprint(old_version, old_code)
        new_fp = self.fingerprint(new_version, new_code)

        change_type = self.classify_change(old_fp, new_fp, old_code, new_code)
        diff_ratio = 1.0 - difflib.SequenceMatcher(
            None, old_code, new_code,
        ).ratio()

        regressions = self.detect_regressions(old_code, new_code, old_fp, new_fp)

        # Compute regression score
        score = sum(r.weight for r in regressions)
        score = round(min(score, 1.0), 4)

        # Gate decision
        if score >= self.block_threshold:
            gate = GateDecision.BLOCK
        elif score >= self.warn_threshold:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        # Function diffs
        old_func_names = {f.split("(")[0] for f in old_fp.function_signatures}
        new_func_names = {f.split("(")[0] for f in new_fp.function_signatures}

        result = ComparisonResult(
            old_version=old_version,
            new_version=new_version,
            change_type=change_type,
            diff_ratio=round(diff_ratio, 4),
            regressions=regressions,
            regression_score=score,
            gate_decision=gate,
            functions_added=sorted(new_func_names - old_func_names),
            functions_removed=sorted(old_func_names - new_func_names),
            functions_modified=[
                f.split("(")[0] for f in old_fp.function_signatures
                if f.split("(")[0] in new_func_names
                and f not in new_fp.function_signatures
            ],
        )

        self._history.append(result)
        return result

    # ── Batch ────────────────────────────────────────────────────────────

    def batch_compare(
        self,
        pairs: list[tuple[str, str, str, str]],
    ) -> BatchRegressionReport:
        """Compare multiple code pairs.

        Each tuple is (old_version, new_version, old_code, new_code).
        """
        results = [
            self.compare(ov, nv, oc, nc)
            for ov, nv, oc, nc in pairs
        ]

        total_reg = sum(len(r.regressions) for r in results)
        avg_score = (
            sum(r.regression_score for r in results) / len(results)
            if results else 0.0
        )

        gates = [r.gate_decision for r in results]
        if GateDecision.BLOCK in gates:
            gate = GateDecision.BLOCK
        elif GateDecision.WARN in gates:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        return BatchRegressionReport(
            results=results,
            total_regressions=total_reg,
            avg_regression_score=round(avg_score, 4),
            gate_decision=gate,
        )

    @property
    def history(self) -> list[ComparisonResult]:
        return list(self._history)
