"""Tests for AST-Level Code Validation module."""

from __future__ import annotations

from app.quality.ast_code_validator import (
    ASTCodeValidator,
    ValidationReport,
    ValidationSeverity,
    ValidationType,
    clear_validation_history,
    get_validation_history,
    get_validation_stats,
    validate_batch,
    validate_code,
)

VT = ValidationType


def _by_type(report: ValidationReport, vt: VT) -> list:
    return [f for f in report.findings if f.finding_type == vt]


class TestASTCodeValidatorBasic:
    """Basic parsing and validation."""

    def setup_method(self) -> None:
        clear_validation_history()

    def test_valid_code_passes(self) -> None:
        report = validate_code("x = 1\ny = x + 2\nprint(y)")
        assert report.is_valid
        assert report.critical_count == 0

    def test_syntax_error_detected(self) -> None:
        report = validate_code("def foo(\n  pass")
        assert not report.is_valid
        assert report.critical_count >= 1
        assert report.findings[0].finding_type == VT.SYNTAX_ERROR

    def test_empty_code(self) -> None:
        report = validate_code("")
        assert report.is_valid
        assert report.total_findings == 0

    def test_lines_analysed(self) -> None:
        code = "a = 1\nb = 2\nc = 3"
        report = validate_code(code)
        assert report.lines_analysed == 3

    def test_report_has_id_and_timestamp(self) -> None:
        report = validate_code("x = 1")
        assert report.id
        assert report.validated_at


class TestImportChecks:
    """Import validation tests."""

    def setup_method(self) -> None:
        clear_validation_history()

    def test_stdlib_import_ok(self) -> None:
        code = "import os\nimport json\nimport sys"
        assert len(_by_type(validate_code(code), VT.INVALID_IMPORT)) == 0

    def test_known_third_party_ok(self) -> None:
        code = "import fastapi\nimport sqlalchemy"
        assert len(_by_type(validate_code(code), VT.INVALID_IMPORT)) == 0

    def test_unknown_module_flagged(self) -> None:
        r = validate_code("import nonexistent_xyz_module")
        findings = _by_type(r, VT.INVALID_IMPORT)
        assert len(findings) == 1
        assert "nonexistent_xyz_module" in findings[0].message

    def test_from_import_unknown(self) -> None:
        r = validate_code("from fake_lib import something")
        assert len(_by_type(r, VT.INVALID_IMPORT)) == 1

    def test_submodule_import_checks_root(self) -> None:
        r = validate_code("import os.path")
        assert len(_by_type(r, VT.INVALID_IMPORT)) == 0

    def test_from_import_with_alias(self) -> None:
        r = validate_code("from os import path as p")
        assert len(_by_type(r, VT.INVALID_IMPORT)) == 0


class TestAttributeChecks:
    """Fabricated attribute detection tests."""

    def setup_method(self) -> None:
        clear_validation_history()

    def test_fabricated_os_attribute(self) -> None:
        r = validate_code("import os\nos.execute_shell('ls')")
        findings = _by_type(r, VT.NONEXISTENT_ATTRIBUTE)
        assert len(findings) == 1
        assert "execute_shell" in findings[0].message

    def test_fabricated_json_parse(self) -> None:
        r = validate_code("import json\nresult = json.parse(data)")
        findings = _by_type(r, VT.NONEXISTENT_ATTRIBUTE)
        assert len(findings) == 1
        assert "parse" in findings[0].message

    def test_fabricated_json_stringify(self) -> None:
        code = "import json\nout = json.stringify({'a': 1})"
        assert len(_by_type(validate_code(code), VT.NONEXISTENT_ATTRIBUTE)) == 1

    def test_valid_json_loads(self) -> None:
        code = 'import json\nresult = json.loads(\'{"a":1}\')'
        assert len(_by_type(validate_code(code), VT.NONEXISTENT_ATTRIBUTE)) == 0

    def test_suggestion_provided(self) -> None:
        r = validate_code("import os\nos.execute_shell('ls')")
        finding = _by_type(r, VT.NONEXISTENT_ATTRIBUTE)[0]
        assert finding.suggestion
        assert "subprocess" in finding.suggestion or "os.system" in finding.suggestion

    def test_fabricated_requests_fetch(self) -> None:
        code = "import requests\nrequests.fetch('http://example.com')"
        assert len(_by_type(validate_code(code), VT.NONEXISTENT_ATTRIBUTE)) == 1


class TestNameChecks:
    """Undefined name detection tests."""

    def setup_method(self) -> None:
        clear_validation_history()

    def test_defined_variable(self) -> None:
        r = validate_code("x = 1\nprint(x)")
        assert len(_by_type(r, VT.UNDEFINED_NAME)) == 0

    def test_function_params_defined(self) -> None:
        r = validate_code("def foo(x, y):\n    return x + y")
        assert len(_by_type(r, VT.UNDEFINED_NAME)) == 0

    def test_class_name_defined(self) -> None:
        r = validate_code("class Foo:\n    pass\nobj = Foo()")
        assert len(_by_type(r, VT.UNDEFINED_NAME)) == 0

    def test_import_defines_name(self) -> None:
        r = validate_code("import os\nprint(os)")
        assert len(_by_type(r, VT.UNDEFINED_NAME)) == 0


class TestBatchValidation:
    """Batch validation tests."""

    def setup_method(self) -> None:
        clear_validation_history()

    def test_batch_returns_list(self) -> None:
        results = validate_batch(["x = 1", "y = 2", "z = 3"])
        assert len(results) == 3
        assert all(isinstance(r, ValidationReport) for r in results)

    def test_batch_mixed_validity(self) -> None:
        results = validate_batch(["x = 1", "def (broken"])
        assert results[0].is_valid
        assert not results[1].is_valid


class TestValidatorConfig:
    """Validator configuration tests."""

    def setup_method(self) -> None:
        clear_validation_history()

    def test_disable_import_checks(self) -> None:
        v = ASTCodeValidator(check_imports=False)
        r = v.validate("import nonexistent_xyz")
        assert len(_by_type(r, VT.INVALID_IMPORT)) == 0

    def test_disable_attribute_checks(self) -> None:
        v = ASTCodeValidator(check_attributes=False)
        r = v.validate("import os\nos.execute_shell('ls')")
        assert len(_by_type(r, VT.NONEXISTENT_ATTRIBUTE)) == 0

    def test_disable_name_checks(self) -> None:
        v = ASTCodeValidator(check_names=False)
        r = v.validate("print(undefined_var)")
        assert len(_by_type(r, VT.UNDEFINED_NAME)) == 0

    def test_strict_mode(self) -> None:
        v = ASTCodeValidator(strict=True)
        report = v.validate("x = 1")
        assert isinstance(report, ValidationReport)


class TestHistory:
    """History and statistics tests."""

    def setup_method(self) -> None:
        clear_validation_history()

    def test_history_recorded(self) -> None:
        validate_code("x = 1")
        validate_code("y = 2")
        assert len(get_validation_history()) == 2

    def test_clear_history(self) -> None:
        validate_code("x = 1")
        clear_validation_history()
        assert len(get_validation_history()) == 0

    def test_stats_empty(self) -> None:
        stats = get_validation_stats()
        assert stats["total_validations"] == 0

    def test_stats_computed(self) -> None:
        validate_code("x = 1")
        validate_code("def (broken")
        stats = get_validation_stats()
        assert stats["total_validations"] == 2
        assert stats["valid_count"] == 1
        assert stats["invalid_count"] == 1
        assert 0 < stats["validity_rate"] < 1


class TestSeverityScoring:
    """Severity scoring tests."""

    def setup_method(self) -> None:
        clear_validation_history()

    def test_syntax_error_is_critical(self) -> None:
        report = validate_code("def (")
        assert report.critical_count >= 1
        f = report.findings[0]
        assert f.severity == ValidationSeverity.CRITICAL

    def test_unknown_import_is_warning(self) -> None:
        r = validate_code("import fake_module_xyz")
        findings = _by_type(r, VT.INVALID_IMPORT)
        assert findings[0].severity == ValidationSeverity.WARNING

    def test_fabricated_attr_is_critical(self) -> None:
        r = validate_code("import json\njson.parse('{}')")
        findings = _by_type(r, VT.NONEXISTENT_ATTRIBUTE)
        assert findings[0].severity == ValidationSeverity.CRITICAL

    def test_critical_makes_invalid(self) -> None:
        r = validate_code("import os\nos.execute_shell('ls')")
        assert not r.is_valid
