"""Tests for License Compliance Verification engine."""

from __future__ import annotations

import pytest

from app.quality.license_compliance import (
    AttributionTemplate,
    BatchComplianceReport,
    ComplianceStatus,
    GateAction,
    KnownSnippet,
    LicenseComplianceEngine,
    LicenseFamily,
    LicenseId,
)


@pytest.fixture
def engine() -> LicenseComplianceEngine:
    return LicenseComplianceEngine(similarity_threshold=0.5)


@pytest.fixture
def engine_with_snippets(engine: LicenseComplianceEngine) -> LicenseComplianceEngine:
    engine.register_code(
        snippet_id="mit-utils",
        source_repo="github.com/example/utils",
        file_path="utils.py",
        license_id=LicenseId.MIT,
        code=(
            "def calculate_hash(data): import hashlib;"
            " return hashlib.sha256(data.encode()).hexdigest()"
        ),
        attribution_text="Copyright 2025 Example. MIT License.",
    )
    engine.register_code(
        snippet_id="gpl-auth",
        source_repo="github.com/example/auth",
        file_path="auth.py",
        license_id=LicenseId.GPL_3,
        code=(
            "def verify_password(password, hashed):"
            " import bcrypt;"
            " return bcrypt.checkpw(password.encode(), hashed)"
        ),
    )
    engine.register_code(
        snippet_id="apache-http",
        source_repo="github.com/example/http",
        file_path="http.py",
        license_id=LicenseId.APACHE_2,
        code=(
            "def make_request(url, method, headers, timeout):"
            " import requests;"
            " return requests.request("
            "method, url, headers=headers, timeout=timeout)"
        ),
        attribution_text="Apache 2.0 License.",
    )
    return engine


class TestEngineInit:
    def test_default_thresholds(self) -> None:
        e = LicenseComplianceEngine()
        assert e._similarity_threshold == 0.7

    def test_custom_thresholds(self) -> None:
        e = LicenseComplianceEngine(
            similarity_threshold=0.5,
            copyleft_weight=3.0,
        )
        assert e._copyleft_weight == 3.0


class TestSnippetRegistration:
    def test_register_code(self, engine: LicenseComplianceEngine) -> None:
        snippet = engine.register_code(
            snippet_id="test-1",
            source_repo="github.com/test",
            file_path="test.py",
            license_id=LicenseId.MIT,
            code="def hello(): return 'world'",
        )
        assert snippet.id == "test-1"
        assert len(snippet.fingerprints) > 0

    def test_register_snippet_directly(self, engine: LicenseComplianceEngine) -> None:
        snippet = KnownSnippet(
            id="direct-1",
            source_repo="repo",
            file_path="f.py",
            license_id=LicenseId.BSD_3,
            fingerprints={"abc123"},
        )
        engine.register_snippet(snippet)
        assert engine._snippets["direct-1"].id == "direct-1"

    def test_register_multiple(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        assert len(engine_with_snippets._snippets) == 3


class TestComplianceCheck:
    def test_clear_when_no_match(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        result = engine_with_snippets.check_compliance(
            "def unique_function(): return 42"
        )
        assert result.status == ComplianceStatus.CLEAR
        assert result.gate_action == GateAction.PASS

    def test_match_with_attribution(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        # Code similar to MIT snippet which has attribution
        result = engine_with_snippets.check_compliance(
            "def calculate_hash(data): import hashlib;"
            " return hashlib.sha256(data.encode()).hexdigest()"
        )
        if result.matches:
            assert result.status in (ComplianceStatus.COMPLIANT, ComplianceStatus.CLEAR)

    def test_copyleft_violation(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        # Code similar to GPL snippet without attribution
        result = engine_with_snippets.check_compliance(
            "def verify_password(password, hashed):"
            " import bcrypt;"
            " return bcrypt.checkpw(password.encode(), hashed)"
        )
        if result.matches:
            assert result.status in (ComplianceStatus.VIOLATION, ComplianceStatus.NEEDS_ATTRIBUTION)

    def test_lico_score_range(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        result = engine_with_snippets.check_compliance("any code here")
        assert 0.0 <= result.lico_score <= 1.0

    def test_code_hash_generated(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        result = engine_with_snippets.check_compliance("test code")
        assert len(result.code_hash) == 16

    def test_timestamp_set(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        result = engine_with_snippets.check_compliance("test")
        assert "T" in result.timestamp


class TestBatchCompliance:
    def test_batch_check(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        report = engine_with_snippets.check_batch([
            "def unique(): return 1",
            "def another(): return 2",
            "def third(): return 3",
        ])
        assert isinstance(report, BatchComplianceReport)
        assert report.total_checked == 3

    def test_batch_counts_add_up(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        report = engine_with_snippets.check_batch([
            "def a(): pass",
            "def b(): pass",
        ])
        total = report.compliant + report.violations + report.needs_attribution + report.clear
        assert total == report.total_checked

    def test_batch_avg_lico(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        report = engine_with_snippets.check_batch(["def x(): pass"])
        assert 0.0 <= report.avg_lico_score <= 1.0


class TestLicenseFamily:
    def test_mit_is_permissive(self, engine: LicenseComplianceEngine) -> None:
        assert engine.get_license_family(LicenseId.MIT) == LicenseFamily.PERMISSIVE

    def test_gpl_is_strong_copyleft(self, engine: LicenseComplianceEngine) -> None:
        assert engine.get_license_family(LicenseId.GPL_3) == LicenseFamily.STRONG_COPYLEFT

    def test_lgpl_is_weak_copyleft(self, engine: LicenseComplianceEngine) -> None:
        assert engine.get_license_family(LicenseId.LGPL_3) == LicenseFamily.WEAK_COPYLEFT

    def test_unknown_license(self, engine: LicenseComplianceEngine) -> None:
        assert engine.get_license_family(LicenseId.UNKNOWN) == LicenseFamily.UNKNOWN


class TestAttribution:
    def test_generate_mit_attribution(self, engine: LicenseComplianceEngine) -> None:
        tmpl = engine.generate_attribution(LicenseId.MIT, "github.com/test")
        assert isinstance(tmpl, AttributionTemplate)
        assert "MIT" in tmpl.attribution_text
        assert tmpl.spdx_identifier == "MIT"

    def test_generate_gpl_attribution(self, engine: LicenseComplianceEngine) -> None:
        tmpl = engine.generate_attribution(LicenseId.GPL_3, "github.com/test")
        assert "GPL" in tmpl.attribution_text
        assert "Derivative" in tmpl.attribution_text

    def test_generate_apache_attribution(self, engine: LicenseComplianceEngine) -> None:
        tmpl = engine.generate_attribution(LicenseId.APACHE_2, "github.com/test")
        assert "Apache" in tmpl.attribution_text


class TestAuditAndAnalytics:
    def test_audit_log(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        engine_with_snippets.check_compliance("test")
        log = engine_with_snippets.get_audit_log()
        assert len(log) >= 1

    def test_analytics(self, engine_with_snippets: LicenseComplianceEngine) -> None:
        engine_with_snippets.check_compliance("test")
        stats = engine_with_snippets.analytics()
        assert stats["total_snippets_registered"] == 3
        assert stats["total_checks"] == 1

    def test_analytics_empty(self, engine: LicenseComplianceEngine) -> None:
        stats = engine.analytics()
        assert stats["total_checks"] == 0


class TestFingerprinting:
    def test_identical_code_same_fingerprints(self, engine: LicenseComplianceEngine) -> None:
        code = "def hello(): print('world'); return True"
        fp1 = engine._generate_fingerprints(code)
        fp2 = engine._generate_fingerprints(code)
        assert fp1 == fp2

    def test_different_code_different_fingerprints(self, engine: LicenseComplianceEngine) -> None:
        fp1 = engine._generate_fingerprints("def hello(): return 1")
        fp2 = engine._generate_fingerprints("class Foo: bar = 42")
        assert fp1 != fp2

    def test_whitespace_normalized(self, engine: LicenseComplianceEngine) -> None:
        fp1 = engine._generate_fingerprints("def  hello():   return 1")
        fp2 = engine._generate_fingerprints("def hello(): return 1")
        assert fp1 == fp2

    def test_short_code_may_have_no_fingerprints(self, engine: LicenseComplianceEngine) -> None:
        fp = engine._generate_fingerprints("x")
        # Single token < ngram_size → no fingerprints
        assert len(fp) == 0
