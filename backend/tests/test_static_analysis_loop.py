"""Tests for Static Analysis Feedback Loop — iterative SA-driven prompting."""

from __future__ import annotations

import pytest

from app.quality.static_analysis_loop import (
    FindingCategory,
    FindingSeverity,
    GateDecision,
    IterationOutcome,
    SAFinding,
    StaticAnalysisLoop,
)


@pytest.fixture
def loop() -> StaticAnalysisLoop:
    return StaticAnalysisLoop()


@pytest.fixture
def strict_loop() -> StaticAnalysisLoop:
    return StaticAnalysisLoop(gate_block_threshold=2, gate_warn_threshold=1)


# ── Parsing: Bandit ─────────────────────────────────────────────────────

class TestBanditParsing:
    def test_parse_bandit_output(self, loop: StaticAnalysisLoop) -> None:
        output = "HIGH CONFIDENCE B105 Use of hardcoded password at app.py:42"
        findings = loop.parse_findings(output, tool="bandit")
        assert len(findings) >= 1
        assert findings[0].rule_id == "B105"

    def test_bandit_security_category(self, loop: StaticAnalysisLoop) -> None:
        output = "MEDIUM CONFIDENCE B101 Assert used at test.py:10"
        findings = loop.parse_findings(output, tool="bandit")
        assert len(findings) >= 1
        assert findings[0].category == FindingCategory.SECURITY

    def test_bandit_severity_mapping(self, loop: StaticAnalysisLoop) -> None:
        output = "LOW CONFIDENCE B311 Random for crypto at crypto.py:5"
        findings = loop.parse_findings(output, tool="bandit")
        assert len(findings) >= 1
        assert findings[0].severity == FindingSeverity.LOW


# ── Parsing: Ruff ───────────────────────────────────────────────────────

class TestRuffParsing:
    def test_parse_ruff_output(self, loop: StaticAnalysisLoop) -> None:
        output = "app/main.py:10:1: E501 Line too long"
        findings = loop.parse_findings(output, tool="ruff")
        assert len(findings) == 1
        assert findings[0].rule_id == "E501"

    def test_ruff_file_and_line(self, loop: StaticAnalysisLoop) -> None:
        output = "models.py:25:5: S105 Possible hardcoded password"
        findings = loop.parse_findings(output, tool="ruff")
        assert len(findings) == 1
        assert findings[0].file_path == "models.py"
        assert findings[0].line == 25
        assert findings[0].column == 5

    def test_ruff_security_severity(self, loop: StaticAnalysisLoop) -> None:
        output = "auth.py:5:1: S105 Possible hardcoded password"
        findings = loop.parse_findings(output, tool="ruff")
        assert findings[0].severity == FindingSeverity.HIGH

    def test_ruff_multiple_findings(self, loop: StaticAnalysisLoop) -> None:
        output = (
            "a.py:1:1: E501 Line too long\n"
            "b.py:2:1: W291 Trailing whitespace\n"
            "c.py:3:1: S105 Hardcoded password\n"
        )
        findings = loop.parse_findings(output, tool="ruff")
        assert len(findings) == 3


# ── Parsing: Pylint ─────────────────────────────────────────────────────

class TestPylintParsing:
    def test_parse_pylint_output(self, loop: StaticAnalysisLoop) -> None:
        output = "module.py:15:0: C0114: Missing module docstring"
        findings = loop.parse_findings(output, tool="pylint")
        assert len(findings) == 1
        assert findings[0].rule_id == "C0114"

    def test_pylint_error_severity(self, loop: StaticAnalysisLoop) -> None:
        output = "module.py:10:4: E0602: Undefined variable 'foo'"
        findings = loop.parse_findings(output, tool="pylint")
        assert findings[0].severity == FindingSeverity.HIGH

    def test_pylint_convention_severity(self, loop: StaticAnalysisLoop) -> None:
        output = "module.py:1:0: C0114: Missing module docstring"
        findings = loop.parse_findings(output, tool="pylint")
        assert findings[0].severity == FindingSeverity.LOW


# ── Parsing: auto detection ─────────────────────────────────────────────

class TestAutoDetection:
    def test_detect_bandit(self, loop: StaticAnalysisLoop) -> None:
        output = "Bandit report:\nHIGH CONFIDENCE B105 password at main.py:1"
        findings = loop.parse_findings(output, tool="auto")
        assert len(findings) >= 1

    def test_detect_ruff(self, loop: StaticAnalysisLoop) -> None:
        output = "app/main.py:10:1: E501 Line too long"
        findings = loop.parse_findings(output, tool="auto")
        assert len(findings) >= 1

    def test_detect_generic(self, loop: StaticAnalysisLoop) -> None:
        output = "warning: something is wrong\nerror: critical failure"
        findings = loop.parse_findings(output, tool="auto")
        assert len(findings) == 2


# ── Scoring ─────────────────────────────────────────────────────────────

class TestScoring:
    def test_empty_findings_score_zero(self, loop: StaticAnalysisLoop) -> None:
        assert loop.compute_weighted_score([]) == 0.0

    def test_critical_finding_high_score(self, loop: StaticAnalysisLoop) -> None:
        findings = [SAFinding(
            id="f1",
            category=FindingCategory.SECURITY,
            severity=FindingSeverity.CRITICAL,
            rule_id="B105",
            message="hardcoded password",
        )]
        score = loop.compute_weighted_score(findings)
        assert score > 0

    def test_security_weighted_higher(self, loop: StaticAnalysisLoop) -> None:
        sec = [SAFinding(
            id="f1", category=FindingCategory.SECURITY,
            severity=FindingSeverity.MEDIUM, rule_id="S1", message="sec",
        )]
        read = [SAFinding(
            id="f2", category=FindingCategory.READABILITY,
            severity=FindingSeverity.MEDIUM, rule_id="C0", message="read",
        )]
        assert loop.compute_weighted_score(sec) > loop.compute_weighted_score(read)

    def test_category_breakdown(self, loop: StaticAnalysisLoop) -> None:
        findings = [
            SAFinding(id="f1", category=FindingCategory.SECURITY,
                      severity=FindingSeverity.HIGH, rule_id="B1", message="a"),
            SAFinding(id="f2", category=FindingCategory.SECURITY,
                      severity=FindingSeverity.LOW, rule_id="B2", message="b"),
            SAFinding(id="f3", category=FindingCategory.READABILITY,
                      severity=FindingSeverity.LOW, rule_id="C0", message="c"),
        ]
        bd = loop.category_breakdown(findings)
        assert bd[FindingCategory.SECURITY] == 2
        assert bd[FindingCategory.READABILITY] == 1


# ── Fix prompt generation ───────────────────────────────────────────────

class TestFixPrompt:
    def test_empty_findings_no_prompt(self, loop: StaticAnalysisLoop) -> None:
        assert loop.generate_fix_prompt("code", []) == ""

    def test_prompt_contains_findings(self, loop: StaticAnalysisLoop) -> None:
        findings = [SAFinding(
            id="f1", category=FindingCategory.SECURITY,
            severity=FindingSeverity.HIGH, rule_id="B105",
            message="hardcoded password", line=42,
        )]
        prompt = loop.generate_fix_prompt("x = 'pass123'", findings, iteration=2)
        assert "B105" in prompt
        assert "hardcoded password" in prompt
        assert "iteration 2" in prompt
        assert "x = 'pass123'" in prompt

    def test_prompt_groups_by_category(self, loop: StaticAnalysisLoop) -> None:
        findings = [
            SAFinding(id="f1", category=FindingCategory.SECURITY,
                      severity=FindingSeverity.HIGH, rule_id="B1", message="a"),
            SAFinding(id="f2", category=FindingCategory.READABILITY,
                      severity=FindingSeverity.LOW, rule_id="C0", message="b"),
        ]
        prompt = loop.generate_fix_prompt("code", findings)
        assert "SECURITY" in prompt
        assert "READABILITY" in prompt


# ── Iteration evaluation ────────────────────────────────────────────────

class TestIterationEval:
    def test_first_iteration_no_prev(self, loop: StaticAnalysisLoop) -> None:
        findings = [SAFinding(
            id="f1", category=FindingCategory.SECURITY,
            severity=FindingSeverity.LOW, rule_id="B1", message="a",
        )]
        result = loop.evaluate_iteration(0, findings)
        assert result.finding_count == 1

    def test_improved_when_count_decreases(self, loop: StaticAnalysisLoop) -> None:
        findings = [SAFinding(
            id="f1", category=FindingCategory.SECURITY,
            severity=FindingSeverity.LOW, rule_id="B1", message="a",
        )]
        result = loop.evaluate_iteration(1, findings, prev_count=5)
        assert result.outcome == IterationOutcome.IMPROVED

    def test_regressed_when_count_increases(self, loop: StaticAnalysisLoop) -> None:
        findings = [SAFinding(
            id=f"f{i}", category=FindingCategory.SECURITY,
            severity=FindingSeverity.LOW, rule_id="B1", message="a",
        ) for i in range(5)]
        result = loop.evaluate_iteration(1, findings, prev_count=2)
        assert result.outcome == IterationOutcome.REGRESSED

    def test_converged_when_zero_findings(self, loop: StaticAnalysisLoop) -> None:
        result = loop.evaluate_iteration(2, [], prev_count=0)
        assert result.outcome == IterationOutcome.CONVERGED

    def test_no_change_when_same_count(self, loop: StaticAnalysisLoop) -> None:
        findings = [SAFinding(
            id=f"f{i}", category=FindingCategory.SECURITY,
            severity=FindingSeverity.LOW, rule_id="B1", message="a",
        ) for i in range(3)]
        result = loop.evaluate_iteration(1, findings, prev_count=3)
        assert result.outcome == IterationOutcome.NO_CHANGE


# ── Full loop ───────────────────────────────────────────────────────────

class TestRunLoop:
    def test_loop_with_convergence(self, loop: StaticAnalysisLoop) -> None:
        iterations = [
            ("code1", "a.py:1:1: E501 Line too long\nb.py:2:1: W291 Trailing ws"),
            ("code2", "a.py:1:1: E501 Line too long"),
            ("code3", ""),
        ]
        report = loop.run_loop("c1", iterations)
        assert report.converged or report.final_finding_count == 0
        assert report.initial_finding_count >= 1
        assert report.reduction_rate > 0

    def test_loop_reduction_rate(self, loop: StaticAnalysisLoop) -> None:
        iterations = [
            ("c1", "a.py:1:1: E501 a\nb.py:2:1: W291 b\nc.py:3:1: S105 c\nd.py:4:1: E302 d"),
            ("c2", "a.py:1:1: E501 a\nb.py:2:1: W291 b"),
            ("c3", "a.py:1:1: E501 a"),
        ]
        report = loop.run_loop("test", iterations)
        assert report.reduction_rate > 0
        assert report.final_finding_count < report.initial_finding_count

    def test_loop_respects_max_iterations(self) -> None:
        small_loop = StaticAnalysisLoop(max_iterations=2)
        iterations = [
            ("c1", "a.py:1:1: E501 a"),
            ("c2", "a.py:1:1: E501 a"),
            ("c3", "a.py:1:1: E501 a"),
            ("c4", ""),
        ]
        report = small_loop.run_loop("test", iterations)
        assert len(report.iterations) <= 2

    def test_loop_empty_iterations(self, loop: StaticAnalysisLoop) -> None:
        report = loop.run_loop("empty", [("code", "")])
        assert report.final_finding_count == 0
        assert report.reduction_rate == 1.0

    def test_loop_category_breakdown(self, loop: StaticAnalysisLoop) -> None:
        iterations = [
            ("c1", "a.py:1:1: S105 password\nb.py:2:1: E501 long"),
        ]
        report = loop.run_loop("test", iterations)
        assert isinstance(report.category_breakdown, dict)


# ── Gate decisions ──────────────────────────────────────────────────────

class TestGateDecisions:
    def test_pass_on_clean(self, loop: StaticAnalysisLoop) -> None:
        report = loop.run_loop("c1", [("code", "")])
        assert report.gate_decision == GateDecision.PASS

    def test_block_on_many_findings(self, strict_loop: StaticAnalysisLoop) -> None:
        iterations = [
            ("c1", "a.py:1:1: S105 a\nb.py:2:1: S106 b\nc.py:3:1: S107 c"),
        ]
        report = strict_loop.run_loop("test", iterations)
        assert report.gate_decision in (GateDecision.WARN, GateDecision.BLOCK)

    def test_warn_on_moderate_findings(self, strict_loop: StaticAnalysisLoop) -> None:
        iterations = [
            ("c1", "a.py:1:1: E501 Line too long"),
        ]
        report = strict_loop.run_loop("test", iterations)
        assert report.gate_decision == GateDecision.WARN


# ── Batch loop ──────────────────────────────────────────────────────────

class TestBatchLoop:
    def test_batch_multiple_files(self, loop: StaticAnalysisLoop) -> None:
        items = [
            ("file1", [("c1", "a.py:1:1: E501 long"), ("c2", "")]),
            ("file2", [("c1", "b.py:1:1: S105 pwd"), ("c2", "b.py:1:1: S105 pwd")]),
        ]
        report = loop.batch_loop(items)
        assert len(report.reports) == 2
        assert report.total_initial_findings > 0

    def test_batch_avg_reduction(self, loop: StaticAnalysisLoop) -> None:
        items = [
            ("f1", [("c1", "a.py:1:1: E501 a\nb.py:2:1: W291 b"), ("c2", "")]),
            ("f2", [("c1", ""), ("c2", "")]),
        ]
        report = loop.batch_loop(items)
        assert report.avg_reduction_rate >= 0

    def test_batch_gate_worst_of_all(self, strict_loop: StaticAnalysisLoop) -> None:
        items = [
            ("f1", [("c1", "")]),
            ("f2", [("c1", "a.py:1:1: S105 a\nb.py:2:1: S106 b\nc.py:3:1: S107 c")]),
        ]
        report = strict_loop.batch_loop(items)
        assert report.gate_decision in (GateDecision.WARN, GateDecision.BLOCK)

    def test_batch_empty(self, loop: StaticAnalysisLoop) -> None:
        report = loop.batch_loop([])
        assert report.total_initial_findings == 0
        assert report.gate_decision == GateDecision.PASS


# ── Generic parser ──────────────────────────────────────────────────────

class TestGenericParser:
    def test_parse_error_lines(self, loop: StaticAnalysisLoop) -> None:
        output = "error: something broke\nwarning: be careful"
        findings = loop.parse_findings(output, tool="generic")
        assert len(findings) == 2

    def test_error_has_high_severity(self, loop: StaticAnalysisLoop) -> None:
        output = "error: critical failure"
        findings = loop.parse_findings(output, tool="generic")
        assert findings[0].severity == FindingSeverity.HIGH

    def test_info_has_info_severity(self, loop: StaticAnalysisLoop) -> None:
        output = "info: just a note"
        findings = loop.parse_findings(output, tool="generic")
        assert findings[0].severity == FindingSeverity.INFO
