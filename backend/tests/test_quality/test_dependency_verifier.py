"""Tests for Hallucinated Dependency Detection (Anti-Slopsquatting)."""

import pytest

from app.quality.dependency_verifier import (
    DependencyVerifier,
    RiskLevel,
    VerificationStatus,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def verifier():
    return DependencyVerifier()


# ---------------------------------------------------------------------------
# Extraction tests
# ---------------------------------------------------------------------------

class TestPythonImportExtraction:
    def test_simple_import(self, verifier: DependencyVerifier):
        code = "import fastapi"
        pkgs = verifier.extract_python_imports(code)
        assert "fastapi" in pkgs

    def test_from_import(self, verifier: DependencyVerifier):
        code = "from fastapi import FastAPI"
        pkgs = verifier.extract_python_imports(code)
        assert "fastapi" in pkgs

    def test_dotted_import(self, verifier: DependencyVerifier):
        code = "from sqlalchemy.orm import Session"
        pkgs = verifier.extract_python_imports(code)
        assert "sqlalchemy" in pkgs

    def test_filters_stdlib(self, verifier: DependencyVerifier):
        code = "import os\nimport json\nimport fastapi"
        pkgs = verifier.extract_python_imports(code)
        assert "os" not in pkgs
        assert "json" not in pkgs
        assert "fastapi" in pkgs

    def test_multiple_imports(self, verifier: DependencyVerifier):
        code = "import fastapi\nimport pydantic\nfrom redis import Redis"
        pkgs = verifier.extract_python_imports(code)
        assert "fastapi" in pkgs
        assert "pydantic" in pkgs
        assert "redis" in pkgs

    def test_no_imports(self, verifier: DependencyVerifier):
        code = "x = 42\nprint(x)"
        pkgs = verifier.extract_python_imports(code)
        assert pkgs == []

    def test_indented_import(self, verifier: DependencyVerifier):
        code = "    import fastapi"
        pkgs = verifier.extract_python_imports(code)
        assert "fastapi" in pkgs


class TestNpmPackageExtraction:
    def test_import_from(self, verifier: DependencyVerifier):
        code = "import React from 'react'"
        pkgs = verifier.extract_npm_packages(code)
        assert "react" in pkgs

    def test_require(self, verifier: DependencyVerifier):
        code = "const express = require('express')"
        pkgs = verifier.extract_npm_packages(code)
        assert "express" in pkgs

    def test_scoped_package(self, verifier: DependencyVerifier):
        code = "import { render } from '@testing-library/react'"
        pkgs = verifier.extract_npm_packages(code)
        assert "@testing-library/react" in pkgs

    def test_ignores_relative(self, verifier: DependencyVerifier):
        code = "import foo from './utils'\nimport bar from '../lib'"
        pkgs = verifier.extract_npm_packages(code)
        assert pkgs == []

    def test_double_quotes(self, verifier: DependencyVerifier):
        code = 'import axios from "axios"'
        pkgs = verifier.extract_npm_packages(code)
        assert "axios" in pkgs


class TestRequirementsExtraction:
    def test_simple_requirements(self, verifier: DependencyVerifier):
        content = "fastapi>=0.100\npydantic\nuvicorn"
        pkgs = verifier.extract_requirements(content)
        assert "fastapi" in pkgs
        assert "pydantic" in pkgs
        assert "uvicorn" in pkgs

    def test_with_version_specifiers(self, verifier: DependencyVerifier):
        content = "fastapi==0.100.0\npydantic>=2.0,<3.0\nuvicorn[standard]"
        pkgs = verifier.extract_requirements(content)
        assert "fastapi" in pkgs
        assert "pydantic" in pkgs
        assert "uvicorn" in pkgs

    def test_ignores_comments(self, verifier: DependencyVerifier):
        content = "# This is a comment\nfastapi"
        pkgs = verifier.extract_requirements(content)
        assert len(pkgs) == 1
        assert "fastapi" in pkgs

    def test_ignores_flags(self, verifier: DependencyVerifier):
        content = "-r base.txt\n--index-url https://pypi.org\nfastapi"
        pkgs = verifier.extract_requirements(content)
        assert "fastapi" in pkgs
        assert len(pkgs) == 1


# ---------------------------------------------------------------------------
# Verification tests
# ---------------------------------------------------------------------------

class TestPackageVerification:
    def test_known_pypi_package(self, verifier: DependencyVerifier):
        result = verifier.verify_package("fastapi", "pypi")
        assert result.status == VerificationStatus.VERIFIED
        assert result.risk_level == RiskLevel.SAFE

    def test_known_npm_package(self, verifier: DependencyVerifier):
        result = verifier.verify_package("react", "npm")
        assert result.status == VerificationStatus.VERIFIED
        assert result.risk_level == RiskLevel.SAFE

    def test_known_hallucinated_package(self, verifier: DependencyVerifier):
        result = verifier.verify_package("python-utils-pro", "pypi")
        assert result.status == VerificationStatus.HALLUCINATED
        assert result.risk_level == RiskLevel.CRITICAL

    def test_suspicious_pattern_ai_keyword(self, verifier: DependencyVerifier):
        result = verifier.verify_package("data-ai-processor", "pypi")
        assert result.status == VerificationStatus.SUSPICIOUS
        assert result.risk_level == RiskLevel.MEDIUM

    def test_suspicious_pattern_auto_prefix(self, verifier: DependencyVerifier):
        result = verifier.verify_package("auto-formatter", "pypi")
        assert result.status == VerificationStatus.SUSPICIOUS

    def test_suspicious_pattern_helper_suffix(self, verifier: DependencyVerifier):
        result = verifier.verify_package("config-helper", "pypi")
        assert result.status == VerificationStatus.SUSPICIOUS

    def test_approved_package(self, verifier: DependencyVerifier):
        verifier.add_approved_package("my-internal-lib")
        result = verifier.verify_package("my-internal-lib")
        assert result.status == VerificationStatus.ALLOWLISTED
        assert result.risk_level == RiskLevel.SAFE

    def test_blocked_package(self, verifier: DependencyVerifier):
        verifier.add_blocked_package("evil-package")
        result = verifier.verify_package("evil-package")
        assert result.status == VerificationStatus.HALLUCINATED
        assert result.risk_level == RiskLevel.CRITICAL

    def test_unknown_package(self, verifier: DependencyVerifier):
        result = verifier.verify_package("some-obscure-real-pkg", "pypi")
        assert result.status == VerificationStatus.UNKNOWN
        assert result.risk_level == RiskLevel.LOW

    def test_auto_registry_detection_pypi(self, verifier: DependencyVerifier):
        result = verifier.verify_package("fastapi", "auto")
        assert result.registry == "pypi"
        assert result.status == VerificationStatus.VERIFIED

    def test_auto_registry_detection_npm(self, verifier: DependencyVerifier):
        result = verifier.verify_package("react", "auto")
        assert result.registry == "npm"

    def test_suggested_alternative(self, verifier: DependencyVerifier):
        result = verifier.verify_package("auto-fastapi", "pypi")
        # Should suggest "fastapi" as alternative
        assert result.status == VerificationStatus.SUSPICIOUS


class TestCodeVerification:
    def test_verify_clean_python(self, verifier: DependencyVerifier):
        code = "import fastapi\nfrom pydantic import BaseModel"
        report = verifier.verify_code(code, "python")
        assert report.hallucinated == 0
        assert report.blocked is False

    def test_verify_python_with_hallucinated(self, verifier: DependencyVerifier):
        # "ai_code_helper" is a made-up package
        verifier.add_blocked_package("ai_code_helper")
        code = "import fastapi\nimport ai_code_helper"
        report = verifier.verify_code(code, "python")
        assert report.hallucinated >= 1
        assert report.blocked is True

    def test_verify_typescript(self, verifier: DependencyVerifier):
        code = "import React from 'react'\nimport axios from 'axios'"
        report = verifier.verify_code(code, "typescript")
        assert report.hallucinated == 0

    def test_verify_report_to_dict(self, verifier: DependencyVerifier):
        code = "import fastapi"
        report = verifier.verify_code(code, "python")
        d = report.to_dict()
        assert "checked_at" in d
        assert "total_packages" in d
        assert "checks" in d

    def test_verify_requirements_file(self, verifier: DependencyVerifier):
        content = "fastapi>=0.100\npydantic\nuvicorn"
        report = verifier.verify_requirements(content)
        assert report.total_packages == 3
        assert report.verified >= 3
        assert report.blocked is False

    def test_verify_requirements_with_hallucinated(self, verifier: DependencyVerifier):
        content = "fastapi\npython-utils-pro\nuvicorn"
        report = verifier.verify_requirements(content)
        assert report.hallucinated >= 1
        assert report.blocked is True


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------

class TestStats:
    def test_empty_stats(self, verifier: DependencyVerifier):
        stats = verifier.get_stats()
        assert stats["total_scans"] == 0
        assert stats["total_packages_checked"] == 0

    def test_stats_after_scans(self, verifier: DependencyVerifier):
        verifier.verify_code("import fastapi", "python")
        verifier.verify_code("import pydantic\nimport redis", "python")
        stats = verifier.get_stats()
        assert stats["total_scans"] == 2
        assert stats["total_packages_checked"] == 3

    def test_scan_history(self, verifier: DependencyVerifier):
        verifier.verify_code("import fastapi", "python")
        assert len(verifier.scan_history) == 1


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_code(self, verifier: DependencyVerifier):
        report = verifier.verify_code("", "python")
        assert report.total_packages == 0
        assert report.blocked is False

    def test_empty_requirements(self, verifier: DependencyVerifier):
        report = verifier.verify_requirements("")
        assert report.total_packages == 0

    def test_unknown_language(self, verifier: DependencyVerifier):
        report = verifier.verify_code("fn main() {}", "rust")
        assert report.total_packages == 0

    def test_check_result_to_dict(self, verifier: DependencyVerifier):
        result = verifier.verify_package("fastapi", "pypi")
        d = result.to_dict()
        assert d["package_name"] == "fastapi"
        assert d["status"] == "verified"
        assert d["risk_level"] == "safe"
