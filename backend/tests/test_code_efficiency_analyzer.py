"""Tests for Code Efficiency Analyzer — performance anti-pattern detection."""

from __future__ import annotations

import pytest

from app.quality.code_efficiency_analyzer import (
    AnalysisResult,
    BatchReport,
    CodeEfficiencyAnalyzer,
    EfficiencyIssueType,
    GateDecision,
    IssueSeverity,
)


@pytest.fixture
def analyzer() -> CodeEfficiencyAnalyzer:
    return CodeEfficiencyAnalyzer()


@pytest.fixture
def strict_analyzer() -> CodeEfficiencyAnalyzer:
    return CodeEfficiencyAnalyzer(warn_threshold=0.9, block_threshold=0.7)


# ── Detection: nested loops ──────────────────────────────────────────────

class TestNestedLoops:
    def test_detects_nested_for_loops(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "for i in range(n):\n"
            "    for j in range(n):\n"
            "        matrix[i][j] = 0\n"
        )
        result = analyzer.analyze("t1", code)
        types = [i.issue_type for i in result.issues]
        assert EfficiencyIssueType.COMPLEXITY in types

    def test_detects_nested_while_loops(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "while a > 0:\n"
            "    while b > 0:\n"
            "        b -= 1\n"
            "    a -= 1\n"
        )
        result = analyzer.analyze("t2", code)
        types = [i.issue_type for i in result.issues]
        assert EfficiencyIssueType.COMPLEXITY in types

    def test_no_false_positive_single_loop(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "for i in range(n):\n"
            "    print(i)\n"
        )
        result = analyzer.analyze("t3", code)
        nested = [i for i in result.issues if i.issue_type == EfficiencyIssueType.COMPLEXITY]
        assert len(nested) == 0

    def test_nested_loop_has_suggestion(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "for x in items:\n"
            "    for y in items:\n"
            "        process(x, y)\n"
        )
        result = analyzer.analyze("t4", code)
        nested = [i for i in result.issues if i.issue_type == EfficiencyIssueType.COMPLEXITY]
        assert nested
        assert nested[0].suggestion != ""
        assert nested[0].line_hint is not None


# ── Detection: string concatenation in loops ─────────────────────────────

class TestStringConcatInLoop:
    def test_detects_concat_in_for_loop(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "result = ''\n"
            "for item in items:\n"
            "    result += str(item)\n"
        )
        result = analyzer.analyze("t5", code)
        types = [i.issue_type for i in result.issues]
        assert EfficiencyIssueType.DATA_STRUCTURE in types

    def test_no_false_positive_outside_loop(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "result = ''\n"
            "result += 'hello'\n"
        )
        result = analyzer.analyze("t6", code)
        concat_issues = [
            i for i in result.issues
            if "concatenation" in i.description.lower()
        ]
        assert len(concat_issues) == 0

    def test_detects_concat_with_string_literal(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "s = ''\n"
            "for c in chars:\n"
            "    s += 'x'\n"
        )
        result = analyzer.analyze("t7", code)
        concat_issues = [
            i for i in result.issues
            if "concatenation" in i.description.lower()
        ]
        assert len(concat_issues) >= 1


# ── Detection: unbounded collections ─────────────────────────────────────

class TestUnboundedCollections:
    def test_detects_unbounded_append(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "results = []\n"
            "for item in stream:\n"
            "    results.append(item)\n"
        )
        result = analyzer.analyze("t8", code)
        mem = [i for i in result.issues if i.issue_type == EfficiencyIssueType.MEMORY]
        assert len(mem) >= 1

    def test_no_issue_with_size_guard(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "results = []\n"
            "for item in stream:\n"
            "    if len(results) < 100:\n"
            "        results.append(item)\n"
        )
        result = analyzer.analyze("t9", code)
        mem = [
            i for i in result.issues
            if i.issue_type == EfficiencyIssueType.MEMORY
            and "unbounded" in i.description.lower()
        ]
        assert len(mem) == 0

    def test_no_false_positive_outside_loop(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "items = []\n"
            "items.append(1)\n"
            "items.append(2)\n"
        )
        result = analyzer.analyze("t10", code)
        mem = [
            i for i in result.issues
            if "unbounded" in i.description.lower()
        ]
        assert len(mem) == 0


# ── Detection: N+1 queries ───────────────────────────────────────────────

class TestNPlusOne:
    def test_detects_query_in_loop(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "for user in users:\n"
            "    orders = db.query(Order).filter(user_id=user.id)\n"
        )
        result = analyzer.analyze("t11", code)
        io_issues = [i for i in result.issues if i.issue_type == EfficiencyIssueType.IO]
        assert len(io_issues) >= 1
        assert io_issues[0].severity == IssueSeverity.CRITICAL

    def test_detects_execute_in_loop(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "for pid in product_ids:\n"
            "    cursor.execute('SELECT * FROM products WHERE id = ?', (pid,))\n"
        )
        result = analyzer.analyze("t12", code)
        io_issues = [i for i in result.issues if i.issue_type == EfficiencyIssueType.IO]
        assert len(io_issues) >= 1

    def test_no_false_positive_query_outside_loop(
        self, analyzer: CodeEfficiencyAnalyzer,
    ) -> None:
        code = (
            "all_users = db.query(User).all()\n"
            "for u in all_users:\n"
            "    print(u.name)\n"
        )
        result = analyzer.analyze("t13", code)
        io_issues = [i for i in result.issues if i.issue_type == EfficiencyIssueType.IO]
        assert len(io_issues) == 0


# ── Detection: missing generators ────────────────────────────────────────

class TestMissingGenerators:
    def test_detects_list_comp_in_sum(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = "total = sum([x * x for x in values])\n"
        result = analyzer.analyze("t14", code)
        mem = [i for i in result.issues if i.issue_type == EfficiencyIssueType.MEMORY]
        assert len(mem) >= 1

    def test_detects_list_comp_in_any(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = "found = any([item.active for item in items])\n"
        result = analyzer.analyze("t15", code)
        mem = [i for i in result.issues if i.issue_type == EfficiencyIssueType.MEMORY]
        assert len(mem) >= 1

    def test_no_issue_with_generator(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = "total = sum(x * x for x in values)\n"
        result = analyzer.analyze("t16", code)
        gen_issues = [
            i for i in result.issues
            if "generator" in i.description.lower()
        ]
        assert len(gen_issues) == 0


# ── Detection: repeated lookups ──────────────────────────────────────────

class TestRepeatedLookups:
    def test_detects_repeated_bracket_lookup(
        self, analyzer: CodeEfficiencyAnalyzer,
    ) -> None:
        code = (
            "for i in range(n):\n"
            "    a = config[key]\n"
            "    b = config[key]\n"
            "    c = config[key]\n"
        )
        result = analyzer.analyze("t17", code)
        ds = [i for i in result.issues if i.issue_type == EfficiencyIssueType.DATA_STRUCTURE]
        repeated = [i for i in ds if "repeated" in i.description.lower()]
        assert len(repeated) >= 1

    def test_no_issue_for_two_lookups(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "for i in range(n):\n"
            "    a = config[key]\n"
            "    b = config[key]\n"
        )
        result = analyzer.analyze("t18", code)
        repeated = [
            i for i in result.issues if "repeated" in i.description.lower()
        ]
        assert len(repeated) == 0


# ── Scoring ──────────────────────────────────────────────────────────────

class TestScoring:
    def test_clean_code_scores_one(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = "x = 1\nprint(x)\n"
        result = analyzer.analyze("clean", code)
        assert result.score == 1.0

    def test_issues_reduce_score(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "for i in range(n):\n"
            "    for j in range(n):\n"
            "        pass\n"
        )
        result = analyzer.analyze("nested", code)
        assert result.score < 1.0

    def test_score_never_negative(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        # Code with many issues
        code = (
            "for user in users:\n"
            "    orders = db.query(Order).filter(user_id=user.id)\n"
            "    for o in orders:\n"
            "        for item in o.items:\n"
            "            result += str(item)\n"
            "            data.append(item)\n"
            "total = sum([x for x in data])\n"
        )
        result = analyzer.analyze("heavy", code)
        assert result.score >= 0.0

    def test_score_range(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "for i in range(n):\n"
            "    for j in range(n):\n"
            "        pass\n"
        )
        result = analyzer.analyze("range_check", code)
        assert 0.0 <= result.score <= 1.0


# ── Gate decisions ───────────────────────────────────────────────────────

class TestGateDecisions:
    def test_clean_code_passes(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        result = analyzer.analyze("gate_pass", "x = 1\n")
        assert result.gate_decision == GateDecision.PASS

    def test_warn_threshold(self) -> None:
        # Use thresholds that will produce WARN for a single high-severity issue
        a = CodeEfficiencyAnalyzer(warn_threshold=0.9, block_threshold=0.4)
        code = (
            "for i in range(n):\n"
            "    for j in range(n):\n"
            "        pass\n"
        )
        result = a.analyze("gate_warn", code)
        assert result.gate_decision in (GateDecision.WARN, GateDecision.BLOCK)

    def test_block_threshold(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        # Accumulate enough issues to drop below block threshold (0.4)
        code = (
            "for user in users:\n"
            "    orders = db.query(Order).filter(user_id=user.id)\n"
            "    for o in orders:\n"
            "        for item in o.items:\n"
            "            result += str(item)\n"
            "            data.append(item)\n"
            "total = sum([x for x in data])\n"
        )
        result = analyzer.analyze("gate_block", code)
        # With critical + high + medium + low issues, score should be very low
        assert result.gate_decision in (GateDecision.WARN, GateDecision.BLOCK)


# ── Batch analysis ───────────────────────────────────────────────────────

class TestBatchAnalysis:
    def test_empty_batch(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        report = analyzer.analyze_batch([])
        assert isinstance(report, BatchReport)
        assert report.avg_score == 1.0
        assert report.total_issues == 0
        assert report.gate_decision == GateDecision.PASS

    def test_batch_with_mixed_items(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        items = [
            ("clean", "x = 1\n"),
            ("nested", "for i in r:\n    for j in r:\n        pass\n"),
        ]
        report = analyzer.analyze_batch(items)
        assert len(report.results) == 2
        assert report.total_issues >= 1
        assert 0.0 <= report.avg_score <= 1.0

    def test_batch_gate_worst_wins(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        items = [
            ("clean", "x = 1\n"),
            (
                "bad",
                "for u in users:\n"
                "    db.execute('SELECT * FROM t WHERE id=?', (u,))\n"
                "    for i in range(n):\n"
                "        for j in range(n):\n"
                "            s += 'x'\n"
                "            data.append(j)\n"
                "total = sum([x for x in data])\n",
            ),
        ]
        report = analyzer.analyze_batch(items)
        # The batch gate should reflect the worst item
        assert report.gate_decision != GateDecision.PASS or report.total_issues == 0

    def test_batch_results_count(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        items = [("a", "x=1\n"), ("b", "y=2\n"), ("c", "z=3\n")]
        report = analyzer.analyze_batch(items)
        assert len(report.results) == 3


# ── Edge cases ───────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_code(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        result = analyzer.analyze("empty", "")
        assert isinstance(result, AnalysisResult)
        assert result.score == 1.0
        assert len(result.issues) == 0
        assert result.gate_decision == GateDecision.PASS

    def test_whitespace_only(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        result = analyzer.analyze("ws", "   \n\n  \n")
        assert result.score == 1.0

    def test_comments_only(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        result = analyzer.analyze("comments", "# just a comment\n# another\n")
        assert result.score == 1.0

    def test_analyzed_at_is_set(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        result = analyzer.analyze("ts", "x = 1\n")
        assert "T" in result.analyzed_at

    def test_issue_ids_unique(self, analyzer: CodeEfficiencyAnalyzer) -> None:
        code = (
            "for i in range(n):\n"
            "    for j in range(n):\n"
            "        result += str(j)\n"
        )
        result = analyzer.analyze("uid", code)
        ids = [i.id for i in result.issues]
        assert len(ids) == len(set(ids))
