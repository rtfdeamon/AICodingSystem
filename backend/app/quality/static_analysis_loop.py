"""Static Analysis Feedback Loop — iterative SA-driven prompting to fix code
quality issues in AI-generated code.

Research shows that iterative static analysis feedback can reduce security
issues from >40% to 13%, readability violations from >80% to 11%, and
reliability warnings from >50% to 11% within ten iterations.

Based on Bouzenia & Pradel "Static Analysis as a Feedback Loop: Enhancing
LLM-Generated Code Beyond Correctness" (arXiv:2508.14419, August 2025).

Key capabilities:
- Parse static analysis tool output into structured findings
- Classify findings by category: security, reliability, readability, performance
- Generate targeted fix prompts from finding context
- Track iteration history with finding count trend
- Convergence detection: stop when no new findings are resolved
- Quality gate: configurable thresholds per category
- Batch analysis across multiple code files
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

class FindingCategory(StrEnum):
    SECURITY = "security"
    RELIABILITY = "reliability"
    READABILITY = "readability"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    CORRECTNESS = "correctness"


class FindingSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class IterationOutcome(StrEnum):
    IMPROVED = "improved"
    NO_CHANGE = "no_change"
    REGRESSED = "regressed"
    CONVERGED = "converged"


# ── Severity weights ────────────────────────────────────────────────────

_SEVERITY_WEIGHT: dict[FindingSeverity, float] = {
    FindingSeverity.CRITICAL: 1.0,
    FindingSeverity.HIGH: 0.7,
    FindingSeverity.MEDIUM: 0.4,
    FindingSeverity.LOW: 0.2,
    FindingSeverity.INFO: 0.05,
}


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class SAFinding:
    """A single static analysis finding."""

    id: str
    category: FindingCategory
    severity: FindingSeverity
    rule_id: str
    message: str
    file_path: str = ""
    line: int | None = None
    column: int | None = None
    suggestion: str = ""

    @property
    def weight(self) -> float:
        return _SEVERITY_WEIGHT.get(self.severity, 0.1)


@dataclass
class IterationResult:
    """Result of a single SA iteration."""

    iteration: int
    findings: list[SAFinding]
    finding_count: int
    weighted_score: float
    outcome: IterationOutcome
    fix_prompt: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class LoopReport:
    """Full feedback loop report."""

    code_id: str
    iterations: list[IterationResult]
    final_finding_count: int
    initial_finding_count: int
    reduction_rate: float
    converged: bool
    gate_decision: GateDecision
    category_breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class BatchLoopReport:
    """Aggregated report across multiple code files."""

    reports: list[LoopReport]
    avg_reduction_rate: float
    total_initial_findings: int
    total_final_findings: int
    gate_decision: GateDecision


# ── Patterns for SA output parsing ───────────────────────────────────────

_BANDIT_PATTERN = re.compile(
    r"(?P<severity>LOW|MEDIUM|HIGH)\s+(?P<confidence>\w+)\s+"
    r"(?P<rule>B\d+)\s+(?P<message>.+?)(?:\s+at\s+(?P<file>.+?):(?P<line>\d+))?$",
    re.MULTILINE,
)

_PYLINT_PATTERN = re.compile(
    r"(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<rule>[A-Z]\d+):\s*(?P<message>.+)$",
    re.MULTILINE,
)

_RUFF_PATTERN = re.compile(
    r"(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<rule>[A-Z]+\d+)\s+(?P<message>.+)$",
    re.MULTILINE,
)

# ── Rule → category mapping ─────────────────────────────────────────────

_RULE_CATEGORY: dict[str, FindingCategory] = {}

# Bandit security rules
for _code in ["B101", "B102", "B103", "B104", "B105", "B106", "B107",
              "B108", "B110", "B112", "B201", "B301", "B302", "B303",
              "B304", "B305", "B306", "B307", "B308", "B310", "B311",
              "B312", "B320", "B321", "B322", "B323", "B324", "B501",
              "B502", "B503", "B504", "B505", "B506", "B507", "B601",
              "B602", "B603", "B604", "B605", "B606", "B607", "B608",
              "B609", "B610", "B611", "B701", "B702", "B703"]:
    _RULE_CATEGORY[_code] = FindingCategory.SECURITY

# Pylint/Ruff readability rules
for _prefix in ["C0", "C4", "W0612", "W0611"]:
    _RULE_CATEGORY[_prefix] = FindingCategory.READABILITY

# Pylint/Ruff reliability rules
for _prefix in ["E0", "E1", "F"]:
    _RULE_CATEGORY[_prefix] = FindingCategory.RELIABILITY

# Performance
for _prefix in ["PERF", "PLW", "SIM"]:
    _RULE_CATEGORY[_prefix] = FindingCategory.PERFORMANCE

# Security ruff rules
for _prefix in ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]:
    _RULE_CATEGORY[_prefix] = FindingCategory.SECURITY


def _classify_rule(rule_id: str) -> FindingCategory:
    """Map a rule ID to a finding category."""
    if rule_id in _RULE_CATEGORY:
        return _RULE_CATEGORY[rule_id]
    for prefix, cat in _RULE_CATEGORY.items():
        if rule_id.startswith(prefix):
            return cat
    return FindingCategory.MAINTAINABILITY


def _severity_from_str(s: str) -> FindingSeverity:
    """Convert a string to FindingSeverity."""
    mapping = {
        "low": FindingSeverity.LOW,
        "medium": FindingSeverity.MEDIUM,
        "high": FindingSeverity.HIGH,
        "critical": FindingSeverity.CRITICAL,
        "info": FindingSeverity.INFO,
        "warning": FindingSeverity.MEDIUM,
        "error": FindingSeverity.HIGH,
        "convention": FindingSeverity.LOW,
        "refactor": FindingSeverity.LOW,
    }
    return mapping.get(s.lower(), FindingSeverity.MEDIUM)


# ── Main class ──────────────────────────────────────────────────────────

class StaticAnalysisLoop:
    """Iterative static analysis feedback loop for LLM-generated code.

    Parses SA tool output, classifies findings, generates fix prompts,
    and tracks convergence across iterations.
    """

    __test__ = False

    def __init__(
        self,
        max_iterations: int = 10,
        convergence_threshold: int = 0,
        gate_block_threshold: int = 5,
        gate_warn_threshold: int = 2,
        category_weights: dict[FindingCategory, float] | None = None,
    ) -> None:
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold
        self.gate_block_threshold = gate_block_threshold
        self.gate_warn_threshold = gate_warn_threshold
        self.category_weights = category_weights or {
            FindingCategory.SECURITY: 2.0,
            FindingCategory.RELIABILITY: 1.5,
            FindingCategory.CORRECTNESS: 1.5,
            FindingCategory.PERFORMANCE: 1.0,
            FindingCategory.READABILITY: 0.5,
            FindingCategory.MAINTAINABILITY: 0.5,
        }

    # ── Parsing ──────────────────────────────────────────────────────────

    def parse_findings(
        self,
        raw_output: str,
        tool: str = "auto",
    ) -> list[SAFinding]:
        """Parse raw SA tool output into structured findings."""
        if tool == "auto":
            tool = self._detect_tool(raw_output)

        findings: list[SAFinding] = []

        if tool == "bandit":
            findings = self._parse_bandit(raw_output)
        elif tool == "pylint":
            findings = self._parse_pylint(raw_output)
        elif tool == "ruff":
            findings = self._parse_ruff(raw_output)
        else:
            findings = self._parse_generic(raw_output)

        return findings

    def _detect_tool(self, output: str) -> str:
        """Detect which SA tool produced the output."""
        if "Bandit" in output or re.search(r"B\d{3}", output):
            return "bandit"
        if re.search(r"[A-Z]\d{4}:", output):
            return "pylint"
        if re.search(r"[A-Z]+\d{3}\s", output):
            return "ruff"
        return "generic"

    def _parse_bandit(self, output: str) -> list[SAFinding]:
        findings: list[SAFinding] = []
        for m in _BANDIT_PATTERN.finditer(output):
            rule_id = m.group("rule")
            findings.append(SAFinding(
                id=uuid.uuid4().hex[:12],
                category=_classify_rule(rule_id),
                severity=_severity_from_str(m.group("severity")),
                rule_id=rule_id,
                message=m.group("message").strip(),
                file_path=m.group("file") or "",
                line=int(m.group("line")) if m.group("line") else None,
            ))
        return findings

    def _parse_pylint(self, output: str) -> list[SAFinding]:
        findings: list[SAFinding] = []
        for m in _PYLINT_PATTERN.finditer(output):
            rule_id = m.group("rule")
            findings.append(SAFinding(
                id=uuid.uuid4().hex[:12],
                category=_classify_rule(rule_id),
                severity=self._pylint_severity(rule_id),
                rule_id=rule_id,
                message=m.group("message").strip(),
                file_path=m.group("file"),
                line=int(m.group("line")),
                column=int(m.group("col")),
            ))
        return findings

    def _parse_ruff(self, output: str) -> list[SAFinding]:
        findings: list[SAFinding] = []
        for m in _RUFF_PATTERN.finditer(output):
            rule_id = m.group("rule")
            findings.append(SAFinding(
                id=uuid.uuid4().hex[:12],
                category=_classify_rule(rule_id),
                severity=self._ruff_severity(rule_id),
                rule_id=rule_id,
                message=m.group("message").strip(),
                file_path=m.group("file"),
                line=int(m.group("line")),
                column=int(m.group("col")),
            ))
        return findings

    def _parse_generic(self, output: str) -> list[SAFinding]:
        """Parse generic warning/error lines."""
        findings: list[SAFinding] = []
        for raw_line in output.strip().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            severity = FindingSeverity.MEDIUM
            if "error" in line.lower():
                severity = FindingSeverity.HIGH
            elif "warning" in line.lower():
                severity = FindingSeverity.MEDIUM
            elif "info" in line.lower():
                severity = FindingSeverity.INFO
            findings.append(SAFinding(
                id=uuid.uuid4().hex[:12],
                category=FindingCategory.MAINTAINABILITY,
                severity=severity,
                rule_id="GENERIC",
                message=line,
            ))
        return findings

    @staticmethod
    def _pylint_severity(rule_id: str) -> FindingSeverity:
        prefix = rule_id[0] if rule_id else ""
        return {
            "E": FindingSeverity.HIGH,
            "W": FindingSeverity.MEDIUM,
            "C": FindingSeverity.LOW,
            "R": FindingSeverity.LOW,
            "F": FindingSeverity.CRITICAL,
        }.get(prefix, FindingSeverity.MEDIUM)

    @staticmethod
    def _ruff_severity(rule_id: str) -> FindingSeverity:
        if rule_id.startswith("S"):
            return FindingSeverity.HIGH
        if rule_id.startswith("E") or rule_id.startswith("F"):
            return FindingSeverity.HIGH
        if rule_id.startswith("W") or rule_id.startswith("B"):
            return FindingSeverity.MEDIUM
        return FindingSeverity.LOW

    # ── Scoring ──────────────────────────────────────────────────────────

    def compute_weighted_score(self, findings: list[SAFinding]) -> float:
        """Compute weighted score (0 = perfect, higher = worse)."""
        if not findings:
            return 0.0
        total = 0.0
        for f in findings:
            cat_weight = self.category_weights.get(f.category, 1.0)
            total += f.weight * cat_weight
        return round(total, 4)

    def category_breakdown(self, findings: list[SAFinding]) -> dict[str, int]:
        """Count findings per category."""
        counts: dict[str, int] = {}
        for f in findings:
            counts[f.category] = counts.get(f.category, 0) + 1
        return counts

    # ── Fix prompt generation ────────────────────────────────────────────

    def generate_fix_prompt(
        self,
        code: str,
        findings: list[SAFinding],
        iteration: int = 1,
    ) -> str:
        """Generate a targeted fix prompt from SA findings."""
        if not findings:
            return ""

        lines: list[str] = [
            f"## Static Analysis Feedback (iteration {iteration})",
            "",
            f"The following {len(findings)} issue(s) were found in the code.",
            "Please fix ALL issues while preserving existing functionality.",
            "",
        ]

        by_category: dict[str, list[SAFinding]] = {}
        for f in findings:
            by_category.setdefault(f.category, []).append(f)

        for cat, cat_findings in sorted(by_category.items()):
            lines.append(f"### {cat.upper()} ({len(cat_findings)} issues)")
            for f in cat_findings:
                loc = f"line {f.line}" if f.line else "unknown location"
                lines.append(f"- [{f.severity}] {f.rule_id}: {f.message} ({loc})")
                if f.suggestion:
                    lines.append(f"  Fix: {f.suggestion}")
            lines.append("")

        lines.append("## Original code:")
        lines.append("```python")
        lines.append(code)
        lines.append("```")

        return "\n".join(lines)

    # ── Iteration logic ──────────────────────────────────────────────────

    def evaluate_iteration(
        self,
        iteration: int,
        findings: list[SAFinding],
        prev_count: int | None = None,
        code: str = "",
    ) -> IterationResult:
        """Evaluate a single iteration of the feedback loop."""
        count = len(findings)
        score = self.compute_weighted_score(findings)

        if prev_count is None:
            outcome = IterationOutcome.IMPROVED if count == 0 else IterationOutcome.NO_CHANGE
        elif count < prev_count:
            outcome = IterationOutcome.IMPROVED
        elif count > prev_count:
            outcome = IterationOutcome.REGRESSED
        elif count <= self.convergence_threshold:
            outcome = IterationOutcome.CONVERGED
        else:
            outcome = IterationOutcome.NO_CHANGE

        fix_prompt = self.generate_fix_prompt(code, findings, iteration + 1)

        return IterationResult(
            iteration=iteration,
            findings=findings,
            finding_count=count,
            weighted_score=score,
            outcome=outcome,
            fix_prompt=fix_prompt,
        )

    def run_loop(
        self,
        code_id: str,
        iteration_outputs: list[tuple[str, str]],
    ) -> LoopReport:
        """Run the full feedback loop given a list of (code, sa_output) tuples.

        Each tuple represents an iteration: the code submitted and the SA
        output received. The loop evaluates convergence and produces a report.
        """
        iterations: list[IterationResult] = []
        prev_count: int | None = None
        converged = False

        for i, (code, sa_output) in enumerate(iteration_outputs):
            findings = self.parse_findings(sa_output)
            result = self.evaluate_iteration(i, findings, prev_count, code)
            iterations.append(result)
            prev_count = result.finding_count

            if result.outcome == IterationOutcome.CONVERGED:
                converged = True
                break

            if i >= self.max_iterations - 1:
                break

        initial_count = iterations[0].finding_count if iterations else 0
        final_count = iterations[-1].finding_count if iterations else 0

        reduction = 1.0 - final_count / initial_count if initial_count > 0 else 1.0

        # Gate decision based on final findings
        gate = self._decide_gate(iterations[-1].findings if iterations else [])

        # Category breakdown of final findings
        breakdown = self.category_breakdown(
            iterations[-1].findings if iterations else [],
        )

        return LoopReport(
            code_id=code_id,
            iterations=iterations,
            final_finding_count=final_count,
            initial_finding_count=initial_count,
            reduction_rate=round(reduction, 4),
            converged=converged,
            gate_decision=gate,
            category_breakdown=breakdown,
        )

    def _decide_gate(self, findings: list[SAFinding]) -> GateDecision:
        """Decide gate based on remaining findings."""
        critical_high = sum(
            1 for f in findings
            if f.severity in (FindingSeverity.CRITICAL, FindingSeverity.HIGH)
        )
        total = len(findings)

        if critical_high >= self.gate_block_threshold:
            return GateDecision.BLOCK
        if total >= self.gate_block_threshold:
            return GateDecision.BLOCK
        if total >= self.gate_warn_threshold:
            return GateDecision.WARN
        return GateDecision.PASS

    # ── Batch ────────────────────────────────────────────────────────────

    def batch_loop(
        self,
        items: list[tuple[str, list[tuple[str, str]]]],
    ) -> BatchLoopReport:
        """Run feedback loops for multiple code files.

        Each item is (code_id, [(code, sa_output), ...]).
        """
        reports = [self.run_loop(cid, iters) for cid, iters in items]

        total_initial = sum(r.initial_finding_count for r in reports)
        total_final = sum(r.final_finding_count for r in reports)

        avg_reduction = (
            1.0 - total_final / total_initial if total_initial > 0 else 1.0
        )

        # Aggregate gate: worst of all
        gates = [r.gate_decision for r in reports]
        if GateDecision.BLOCK in gates:
            gate = GateDecision.BLOCK
        elif GateDecision.WARN in gates:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        return BatchLoopReport(
            reports=reports,
            avg_reduction_rate=round(avg_reduction, 4),
            total_initial_findings=total_initial,
            total_final_findings=total_final,
            gate_decision=gate,
        )
