"""Tests for Non-Functional Quality Assessor."""

from __future__ import annotations

import pytest

from app.quality.nonfunctional_quality_assessor import (
    AI_CODE_SMELLS,
    SECURITY_PATTERNS,
    AssessmentConfig,
    CodeOrigin,
    CodeSample,
    GateDecision,
    NFQCDimension,
    NonFunctionalQualityAssessor,
    QualityGrade,
    _avg_function_length,
    _count_functions,
    _count_lines,
    _count_pattern_matches,
    _estimate_cyclomatic_complexity,
    _grade_score,
    _grade_to_gate,
    _max_nesting_depth,
)

# ── Helper factories ──────────────────────────────────────────────────────

def _make_assessor(**overrides) -> NonFunctionalQualityAssessor:
    config = AssessmentConfig(**overrides) if overrides else None
    return NonFunctionalQualityAssessor(config)


GOOD_CODE = '''
def calculate_total(items: list[dict], tax_rate: float) -> float:
    """Calculate the total price with tax for a list of items."""
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    tax = subtotal * tax_rate
    return round(subtotal + tax, 2)


def validate_email(email: str) -> bool:
    """Check if email has a valid format."""
    import re
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email))
'''

BAD_CODE = '''
import *
def f(a, b, c, d, e, f, g):
    x = eval(a)
    password = "secret123"
    for i in range(100):
        for j in range(100):
            for k in range(100):
                if x:
                    if b:
                        if c:
                            if d:
                                print(x)
    try:
        pass
    except:
        pass
'''

MEDIUM_CODE = '''
# Helper utilities for data processing
def process_data(records):
    """Process a list of records and return summary."""
    results = []
    for record in records:
        if record.get("active"):
            try:
                value = record["value"] * 1.1
                results.append({"id": record["id"], "value": value})
            except KeyError:
                continue
    return results
'''


# ── Pure helper tests ─────────────────────────────────────────────────────

class TestCountLines:
    def test_simple(self):
        assert _count_lines("a = 1\nb = 2\n") == 2

    def test_ignores_comments(self):
        assert _count_lines("# comment\na = 1\n") == 1

    def test_ignores_empty(self):
        assert _count_lines("a = 1\n\n\nb = 2\n") == 2


class TestEstimateCyclomaticComplexity:
    def test_simple_function(self):
        code = "def foo():\n    return 1"
        assert _estimate_cyclomatic_complexity(code) == 1

    def test_with_branches(self):
        code = "if x:\n    pass\nelif y:\n    pass\nfor i in z:\n    pass"
        # 1 base + if + elif + for = 4
        assert _estimate_cyclomatic_complexity(code) == 4

    def test_with_boolean_ops(self):
        code = "if x and y or z:\n    pass"
        assert _estimate_cyclomatic_complexity(code) >= 3


class TestMaxNestingDepth:
    def test_flat(self):
        assert _max_nesting_depth("x = 1\ny = 2\n") == 0

    def test_nested(self):
        code = "def f():\n    if x:\n        for i in y:\n            pass"
        assert _max_nesting_depth(code) == 3

    def test_deeply_nested(self):
        code = "if a:\n    if b:\n        if c:\n            if d:\n                pass"
        assert _max_nesting_depth(code) == 4


class TestCountFunctions:
    def test_no_functions(self):
        assert _count_functions("x = 1") == 0

    def test_multiple_functions(self):
        assert _count_functions("def foo():\n    pass\ndef bar():\n    pass") == 2


class TestAvgFunctionLength:
    def test_single_function(self):
        code = "def foo():\n    x = 1\n    y = 2\n    return x + y"
        assert _avg_function_length(code) > 0

    def test_no_functions(self):
        code = "x = 1\ny = 2"
        assert _avg_function_length(code) == 2


class TestCountPatternMatches:
    def test_finds_smells(self):
        code = "# TODO fix this\nprint('debug')\nexcept:"
        found = _count_pattern_matches(code, AI_CODE_SMELLS)
        assert "unresolved_marker" in found
        assert "debug_print" in found

    def test_security_patterns(self):
        code = "eval(user_input)\nos.system(cmd)"
        found = _count_pattern_matches(code, SECURITY_PATTERNS)
        assert "eval_usage" in found
        assert "os_system_usage" in found

    def test_clean_code(self):
        found = _count_pattern_matches("x = 1 + 2", AI_CODE_SMELLS)
        assert len(found) == 0


class TestGradeScore:
    def test_exemplary(self):
        cfg = AssessmentConfig()
        assert _grade_score(0.90, cfg) == QualityGrade.EXEMPLARY

    def test_acceptable(self):
        cfg = AssessmentConfig()
        assert _grade_score(0.70, cfg) == QualityGrade.ACCEPTABLE

    def test_needs_improvement(self):
        cfg = AssessmentConfig()
        assert _grade_score(0.50, cfg) == QualityGrade.NEEDS_IMPROVEMENT

    def test_poor(self):
        cfg = AssessmentConfig()
        assert _grade_score(0.30, cfg) == QualityGrade.POOR


class TestGradeToGate:
    def test_exemplary_passes(self):
        assert _grade_to_gate(QualityGrade.EXEMPLARY) == GateDecision.PASS

    def test_acceptable_passes(self):
        assert _grade_to_gate(QualityGrade.ACCEPTABLE) == GateDecision.PASS

    def test_needs_improvement_warns(self):
        assert _grade_to_gate(QualityGrade.NEEDS_IMPROVEMENT) == GateDecision.WARN

    def test_poor_blocks(self):
        assert _grade_to_gate(QualityGrade.POOR) == GateDecision.BLOCK


# ── Assessor tests ────────────────────────────────────────────────────────

class TestAssess:
    def test_good_code_scores_high(self):
        assessor = _make_assessor()
        sample = CodeSample(code=GOOD_CODE, origin=CodeOrigin.HUMAN_WRITTEN)
        result = assessor.assess(sample)
        assert result.composite_score >= 0.65
        assert result.grade in (QualityGrade.EXEMPLARY, QualityGrade.ACCEPTABLE)

    def test_bad_code_scores_low(self):
        assessor = _make_assessor()
        sample = CodeSample(code=BAD_CODE, origin=CodeOrigin.AI_GENERATED)
        result = assessor.assess(sample)
        assert result.composite_score < 0.85  # below exemplary
        assert result.ai_smell_count > 0

    def test_medium_code(self):
        assessor = _make_assessor()
        sample = CodeSample(code=MEDIUM_CODE)
        result = assessor.assess(sample)
        assert result.composite_score >= 0.65  # at least acceptable

    def test_empty_code(self):
        assessor = _make_assessor()
        sample = CodeSample(code="")
        result = assessor.assess(sample)
        assert result.grade == QualityGrade.POOR
        assert result.gate == GateDecision.BLOCK

    def test_all_dimensions_present(self):
        assessor = _make_assessor()
        sample = CodeSample(code=GOOD_CODE)
        result = assessor.assess(sample)
        dims = {d.dimension for d in result.dimensions}
        assert NFQCDimension.MAINTAINABILITY in dims
        assert NFQCDimension.READABILITY in dims
        assert NFQCDimension.PERFORMANCE in dims
        assert NFQCDimension.SECURITY in dims
        assert NFQCDimension.RELIABILITY in dims
        assert NFQCDimension.TESTABILITY in dims

    def test_security_issues_detected(self):
        assessor = _make_assessor()
        code = "eval(user_input)\nos.system(cmd)"
        sample = CodeSample(code=code)
        result = assessor.assess(sample)
        sec = [d for d in result.dimensions if d.dimension == NFQCDimension.SECURITY][0]
        assert sec.score < 1.0
        assert len(sec.issues) > 0

    def test_origin_preserved(self):
        assessor = _make_assessor()
        sample = CodeSample(code=GOOD_CODE, origin=CodeOrigin.AI_GENERATED)
        result = assessor.assess(sample)
        assert result.origin == CodeOrigin.AI_GENERATED


class TestBatchReport:
    def test_empty_report(self):
        assessor = _make_assessor()
        report = assessor.batch_report()
        assert report.avg_score == 0.0

    def test_multi_sample_report(self):
        assessor = _make_assessor()
        assessor.assess(CodeSample(code=GOOD_CODE, origin=CodeOrigin.HUMAN_WRITTEN))
        assessor.assess(CodeSample(code=BAD_CODE, origin=CodeOrigin.AI_GENERATED))
        report = assessor.batch_report()
        assert len(report.results) == 2
        assert report.weakest_dimension
        assert report.strongest_dimension

    def test_grade_distribution(self):
        assessor = _make_assessor()
        assessor.assess(CodeSample(code=GOOD_CODE))
        assessor.assess(CodeSample(code=GOOD_CODE))
        report = assessor.batch_report()
        assert sum(report.grade_distribution.values()) == 2

    def test_ai_vs_human_delta(self):
        assessor = _make_assessor()
        assessor.assess(CodeSample(code=GOOD_CODE, origin=CodeOrigin.HUMAN_WRITTEN))
        assessor.assess(CodeSample(code=BAD_CODE, origin=CodeOrigin.AI_GENERATED))
        report = assessor.batch_report()
        # Human code should score higher → delta negative
        assert report.ai_vs_human_delta < 0

    def test_total_ai_smells(self):
        assessor = _make_assessor()
        assessor.assess(CodeSample(code=BAD_CODE))
        report = assessor.batch_report()
        assert report.total_ai_smells > 0


class TestAssessmentConfig:
    def test_defaults(self):
        cfg = AssessmentConfig()
        assert cfg.exemplary_threshold == 0.85
        assert sum(cfg.dimension_weights.values()) == pytest.approx(1.0)

    def test_custom_weights(self):
        cfg = AssessmentConfig(dimension_weights={"maintainability": 1.0})
        assert cfg.dimension_weights["maintainability"] == 1.0


class TestEnumValues:
    def test_quality_grades(self):
        assert QualityGrade.EXEMPLARY == "exemplary"
        assert QualityGrade.POOR == "poor"

    def test_dimensions(self):
        assert NFQCDimension.TESTABILITY == "testability"

    def test_code_origin(self):
        assert CodeOrigin.AI_GENERATED == "ai_generated"
