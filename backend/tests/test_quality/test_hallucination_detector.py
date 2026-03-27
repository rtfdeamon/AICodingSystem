"""Tests for hallucination detection pipeline."""

from __future__ import annotations

from app.quality.hallucination_detector import (
    HallucinationFinding,
    HallucinationReport,
    HallucinationType,
    check_api_usage,
    check_imports,
    check_syntax_validity,
    check_variable_consistency,
    clear_scan_history,
    compute_risk_score,
    extract_function_calls,
    extract_imports,
    get_hallucination_stats,
    get_scan_history,
    hallucination_report_to_json,
    scan_code,
)

# ── Import extraction ────────────────────────────────────────────────────


class TestExtractImports:
    def test_simple_import(self) -> None:
        code = "import os"
        assert extract_imports(code) == ["os"]

    def test_from_import(self) -> None:
        code = "from pathlib import Path"
        assert extract_imports(code) == ["pathlib"]

    def test_multiple_imports(self) -> None:
        code = "import os\nimport sys\nfrom json import loads"
        result = extract_imports(code)
        assert "os" in result
        assert "sys" in result
        assert "json" in result

    def test_dotted_import(self) -> None:
        code = "import os.path"
        assert extract_imports(code) == ["os"]

    def test_no_imports(self) -> None:
        code = "x = 1\nprint(x)"
        assert extract_imports(code) == []


# ── Known module detection ───────────────────────────────────────────────


class TestCheckImports:
    def test_stdlib_module_passes(self) -> None:
        code = "import os\nimport json\nimport pathlib"
        findings = check_imports(code)
        assert len(findings) == 0

    def test_known_package_passes(self) -> None:
        code = "import flask\nimport requests\nimport numpy"
        findings = check_imports(code)
        assert len(findings) == 0

    def test_fabricated_import_detected(self) -> None:
        code = "import superfake_nonexistent_lib"
        findings = check_imports(code)
        assert len(findings) == 1
        assert findings[0].hallucination_type == HallucinationType.FABRICATED_IMPORT
        assert "superfake_nonexistent_lib" in findings[0].description

    def test_mix_of_known_and_unknown(self) -> None:
        code = "import os\nimport not_a_real_package\nimport json"
        findings = check_imports(code)
        assert len(findings) == 1
        assert "not_a_real_package" in findings[0].description


# ── API usage checks ─────────────────────────────────────────────────────


class TestCheckAPIUsage:
    def test_fabricated_api_detected(self) -> None:
        code = "result = json.parse(data)"
        findings = check_api_usage(code)
        assert len(findings) == 1
        assert findings[0].hallucination_type == HallucinationType.NONEXISTENT_API
        assert "json.parse" in findings[0].description

    def test_valid_api_passes(self) -> None:
        code = "result = json.loads(data)"
        findings = check_api_usage(code)
        assert len(findings) == 0

    def test_os_env_detected(self) -> None:
        code = "val = os.env('HOME')"
        findings = check_api_usage(code)
        assert any("os.env" in f.description for f in findings)


# ── Function call extraction ─────────────────────────────────────────────


class TestExtractFunctionCalls:
    def test_simple_call(self) -> None:
        code = "os.path.join('a', 'b')"
        calls = extract_function_calls(code)
        # The regex picks up dotted pairs; path.join is the immediate match
        assert any(method == "join" for _, method in calls)

    def test_no_calls(self) -> None:
        code = "x = 1 + 2"
        assert extract_function_calls(code) == []


# ── Syntax validation ────────────────────────────────────────────────────


class TestCheckSyntaxValidity:
    def test_valid_syntax(self) -> None:
        code = "def foo():\n    return 42"
        findings = check_syntax_validity(code)
        assert len(findings) == 0

    def test_invalid_syntax(self) -> None:
        code = "def foo(\n    return 42"
        findings = check_syntax_validity(code)
        assert len(findings) == 1
        assert findings[0].hallucination_type == HallucinationType.INVALID_SYNTAX
        assert findings[0].confidence == 1.0


# ── Variable consistency ─────────────────────────────────────────────────


class TestCheckVariableConsistency:
    def test_clean_code_passes(self) -> None:
        code = "x = 10\ny = x + 1\nprint(y)"
        findings = check_variable_consistency(code)
        assert len(findings) == 0

    def test_phantom_variable_detected(self) -> None:
        code = "result = undefined_var + 1"
        findings = check_variable_consistency(code)
        assert any(
            f.hallucination_type == HallucinationType.PHANTOM_VARIABLE
            for f in findings
        )


# ── Risk score computation ───────────────────────────────────────────────


class TestComputeRiskScore:
    def test_no_findings_zero_score(self) -> None:
        assert compute_risk_score([]) == 0.0

    def test_single_syntax_error(self) -> None:
        findings = [
            HallucinationFinding(
                hallucination_type=HallucinationType.INVALID_SYNTAX,
                description="bad syntax",
                code_snippet="x =",
                confidence=1.0,
            )
        ]
        score = compute_risk_score(findings)
        assert score == 30.0

    def test_score_capped_at_100(self) -> None:
        findings = [
            HallucinationFinding(
                hallucination_type=HallucinationType.INVALID_SYNTAX,
                description="err",
                code_snippet="",
                confidence=1.0,
            )
            for _ in range(10)
        ]
        score = compute_risk_score(findings)
        assert score == 100.0


# ── Full code scan ───────────────────────────────────────────────────────


class TestScanCode:
    def setup_method(self) -> None:
        clear_scan_history()

    def test_safe_code_passes(self) -> None:
        code = "import os\npath = os.getcwd()\nprint(path)"
        report = scan_code(code)
        assert report.is_safe
        assert report.risk_score < 30.0
        assert report.total_checks == 4

    def test_syntax_error_flagged(self) -> None:
        code = "def foo(:\n    pass"
        report = scan_code(code)
        assert not report.is_safe
        assert any(
            f.hallucination_type == HallucinationType.INVALID_SYNTAX
            for f in report.findings
        )

    def test_multiple_hallucination_types(self) -> None:
        code = (
            "import superfake\n"
            "result = json.parse(data)\n"
        )
        report = scan_code(code)
        types_found = {f.hallucination_type for f in report.findings}
        assert HallucinationType.FABRICATED_IMPORT in types_found
        assert HallucinationType.NONEXISTENT_API in types_found

    def test_scan_populates_history(self) -> None:
        scan_code("x = 1")
        assert len(get_scan_history()) == 1

    def test_non_python_language(self) -> None:
        report = scan_code("console.log('hello');", language="javascript")
        assert report.total_checks == 1


# ── Edge cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def setup_method(self) -> None:
        clear_scan_history()

    def test_empty_code(self) -> None:
        report = scan_code("")
        assert report.is_safe
        assert len(report.findings) == 0

    def test_comments_only(self) -> None:
        code = "# This is a comment\n# Another comment\n"
        report = scan_code(code)
        assert report.is_safe
        assert len(report.findings) == 0


# ── Stats aggregation ────────────────────────────────────────────────────


class TestHallucinationStats:
    def setup_method(self) -> None:
        clear_scan_history()

    def test_empty_stats(self) -> None:
        stats = get_hallucination_stats()
        assert stats["total_scans"] == 0
        assert stats["average_risk_score"] == 0.0

    def test_stats_after_scans(self) -> None:
        scan_code("x = 1")
        scan_code("def foo(:\n    pass")
        stats = get_hallucination_stats()
        assert stats["total_scans"] == 2
        assert stats["safe_scans"] >= 1
        assert stats["total_findings"] >= 1
        assert isinstance(stats["findings_by_type"], dict)


# ── JSON serialisation ───────────────────────────────────────────────────


class TestHallucinationReportToJson:
    def setup_method(self) -> None:
        clear_scan_history()

    def test_serialise_empty_report(self) -> None:
        report = HallucinationReport()
        data = hallucination_report_to_json(report)
        assert data["findings"] == []
        assert data["risk_score"] == 0.0
        assert data["is_safe"] is True

    def test_serialise_report_with_findings(self) -> None:
        report = scan_code("import superfake_nonexistent_lib")
        data = hallucination_report_to_json(report)
        assert len(data["findings"]) >= 1
        finding = data["findings"][0]
        assert "hallucination_type" in finding
        assert "description" in finding
        assert "confidence" in finding
        assert isinstance(data["risk_score"], float)
