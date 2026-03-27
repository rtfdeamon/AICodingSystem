"""Tests for Regression Test Guard — regression detection in LLM-generated code."""

from __future__ import annotations

import pytest

from app.quality.regression_test_guard import (
    ChangeType,
    GateDecision,
    RegressionSeverity,
    RegressionTestGuard,
)


@pytest.fixture
def guard() -> RegressionTestGuard:
    return RegressionTestGuard()


@pytest.fixture
def strict_guard() -> RegressionTestGuard:
    return RegressionTestGuard(block_threshold=0.2, warn_threshold=0.1)


# ── Fingerprinting ──────────────────────────────────────────────────────

class TestFingerprinting:
    def test_fingerprint_basic(self, guard: RegressionTestGuard) -> None:
        code = "def hello():\n    return 'world'\n"
        fp = guard.fingerprint("v1", code)
        assert fp.version_id == "v1"
        assert fp.structural_hash
        assert fp.normalized_hash
        assert fp.line_count == 2

    def test_fingerprint_extracts_functions(self, guard: RegressionTestGuard) -> None:
        code = "def foo(x, y):\n    return x + y\n\ndef bar(z):\n    return z * 2\n"
        fp = guard.fingerprint("v1", code)
        func_names = [f.split("(")[0] for f in fp.function_signatures]
        assert "foo" in func_names
        assert "bar" in func_names

    def test_fingerprint_extracts_imports(self, guard: RegressionTestGuard) -> None:
        code = "import os\nfrom sys import path\ndef main():\n    pass\n"
        fp = guard.fingerprint("v1", code)
        assert len(fp.import_set) == 2

    def test_fingerprint_complexity_estimate(self, guard: RegressionTestGuard) -> None:
        simple = "def f():\n    return 1\n"
        complex_code = (
            "def f(x):\n    if x > 0:\n        for i in range(x):\n"
            "            if i % 2:\n                try:\n                    pass\n"
            "                except:\n                    pass\n"
        )
        fp_s = guard.fingerprint("v1", simple)
        fp_c = guard.fingerprint("v2", complex_code)
        assert fp_c.complexity_estimate > fp_s.complexity_estimate

    def test_identical_code_same_hash(self, guard: RegressionTestGuard) -> None:
        code = "def f():\n    return 1\n"
        fp1 = guard.fingerprint("v1", code)
        fp2 = guard.fingerprint("v2", code)
        assert fp1.structural_hash == fp2.structural_hash
        assert fp1.normalized_hash == fp2.normalized_hash


# ── Change classification ───────────────────────────────────────────────

class TestChangeClassification:
    def test_identical_is_cosmetic(self, guard: RegressionTestGuard) -> None:
        code = "def f():\n    return 1\n"
        fp1 = guard.fingerprint("v1", code)
        fp2 = guard.fingerprint("v2", code)
        assert guard.classify_change(fp1, fp2, code, code) == ChangeType.COSMETIC

    def test_whitespace_only_is_cosmetic(self, guard: RegressionTestGuard) -> None:
        old = "def f():\n    return 1\n"
        new = "def f():\n    return 1  \n"  # trailing space
        fp1 = guard.fingerprint("v1", old)
        fp2 = guard.fingerprint("v2", new)
        ct = guard.classify_change(fp1, fp2, old, new)
        assert ct in (ChangeType.COSMETIC, ChangeType.SEMANTIC_PRESERVING)

    def test_function_removal_is_semantic_altering(self, guard: RegressionTestGuard) -> None:
        old = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        new = "def foo():\n    pass\n"
        fp1 = guard.fingerprint("v1", old)
        fp2 = guard.fingerprint("v2", new)
        ct = guard.classify_change(fp1, fp2, old, new)
        assert ct == ChangeType.SEMANTIC_ALTERING

    def test_signature_change_is_semantic_altering(self, guard: RegressionTestGuard) -> None:
        old = "def foo(x, y):\n    return x + y\n"
        new = "def foo(x):\n    return x\n"
        fp1 = guard.fingerprint("v1", old)
        fp2 = guard.fingerprint("v2", new)
        ct = guard.classify_change(fp1, fp2, old, new)
        assert ct == ChangeType.SEMANTIC_ALTERING

    def test_import_change_is_semantic_altering(self, guard: RegressionTestGuard) -> None:
        old = "import os\ndef f():\n    return os.getcwd()\n"
        new = "import sys\ndef f():\n    return sys.argv\n"
        fp1 = guard.fingerprint("v1", old)
        fp2 = guard.fingerprint("v2", new)
        ct = guard.classify_change(fp1, fp2, old, new)
        assert ct == ChangeType.SEMANTIC_ALTERING


# ── Regression detection ────────────────────────────────────────────────

class TestRegressionDetection:
    def test_no_regressions_for_identical(self, guard: RegressionTestGuard) -> None:
        code = "def f():\n    return 1\n"
        fp1 = guard.fingerprint("v1", code)
        fp2 = guard.fingerprint("v2", code)
        regs = guard.detect_regressions(code, code, fp1, fp2)
        assert len(regs) == 0

    def test_removed_function_detected(self, guard: RegressionTestGuard) -> None:
        old = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        new = "def foo():\n    pass\n"
        fp1 = guard.fingerprint("v1", old)
        fp2 = guard.fingerprint("v2", new)
        regs = guard.detect_regressions(old, new, fp1, fp2)
        removed = [r for r in regs if "removed" in r.description.lower()]
        assert len(removed) >= 1
        assert removed[0].severity == RegressionSeverity.HIGH

    def test_changed_signature_detected(self, guard: RegressionTestGuard) -> None:
        old = "def foo(x, y):\n    return x + y\n"
        new = "def foo(x):\n    return x\n"
        fp1 = guard.fingerprint("v1", old)
        fp2 = guard.fingerprint("v2", new)
        regs = guard.detect_regressions(old, new, fp1, fp2)
        sig_change = [r for r in regs if "signature" in r.description.lower()]
        assert len(sig_change) >= 1

    def test_removed_imports_detected(self, guard: RegressionTestGuard) -> None:
        old = "import os\nimport sys\ndef f():\n    pass\n"
        new = "import os\ndef f():\n    pass\n"
        fp1 = guard.fingerprint("v1", old)
        fp2 = guard.fingerprint("v2", new)
        regs = guard.detect_regressions(old, new, fp1, fp2)
        imp_regs = [r for r in regs if "import" in r.description.lower()]
        assert len(imp_regs) >= 1

    def test_complexity_reduction_warning(self, guard: RegressionTestGuard) -> None:
        old = (
            "def f(x):\n    if x > 0:\n        for i in range(x):\n"
            "            if i % 2:\n                try:\n                    pass\n"
            "                except:\n                    pass\n            else:\n"
            "                for j in range(i):\n                    if j:\n"
            "                        while True:\n                            break\n"
        )
        new = "def f(x):\n    return x\n"
        fp1 = guard.fingerprint("v1", old)
        fp2 = guard.fingerprint("v2", new)
        regs = guard.detect_regressions(old, new, fp1, fp2)
        comp_regs = [r for r in regs if "complexity" in r.description.lower()]
        assert len(comp_regs) >= 1


# ── Full comparison ─────────────────────────────────────────────────────

class TestCompare:
    def test_compare_identical(self, guard: RegressionTestGuard) -> None:
        code = "def f():\n    return 1\n"
        result = guard.compare("v1", "v2", code, code)
        assert result.gate_decision == GateDecision.PASS
        assert result.regression_score == 0.0
        assert len(result.regressions) == 0

    def test_compare_with_regressions(self, guard: RegressionTestGuard) -> None:
        old = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        new = "def baz():\n    pass\n"
        result = guard.compare("v1", "v2", old, new)
        assert len(result.regressions) > 0
        assert result.regression_score > 0
        assert "foo" in result.functions_removed or "bar" in result.functions_removed

    def test_compare_tracks_added_functions(self, guard: RegressionTestGuard) -> None:
        old = "def foo():\n    pass\n"
        new = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        result = guard.compare("v1", "v2", old, new)
        assert "bar" in result.functions_added

    def test_compare_diff_ratio(self, guard: RegressionTestGuard) -> None:
        old = "x = 1\n"
        new = "x = 1\ny = 2\nz = 3\n"
        result = guard.compare("v1", "v2", old, new)
        assert result.diff_ratio > 0

    def test_compare_stores_history(self, guard: RegressionTestGuard) -> None:
        code = "def f():\n    return 1\n"
        guard.compare("v1", "v2", code, code)
        assert len(guard.history) == 1


# ── Gate decisions ──────────────────────────────────────────────────────

class TestGateDecisions:
    def test_pass_on_no_regressions(self, guard: RegressionTestGuard) -> None:
        code = "def f():\n    return 1\n"
        result = guard.compare("v1", "v2", code, code)
        assert result.gate_decision == GateDecision.PASS

    def test_block_on_severe_regressions(self, strict_guard: RegressionTestGuard) -> None:
        old = "def a():\n    pass\n\ndef b():\n    pass\n\ndef c():\n    pass\n"
        new = "pass\n"
        result = strict_guard.compare("v1", "v2", old, new)
        assert result.gate_decision in (GateDecision.WARN, GateDecision.BLOCK)

    def test_warn_on_moderate_regressions(self, strict_guard: RegressionTestGuard) -> None:
        old = "def foo(x, y):\n    return x + y\n"
        new = "def foo(x):\n    return x\n"
        result = strict_guard.compare("v1", "v2", old, new)
        assert result.gate_decision in (GateDecision.WARN, GateDecision.BLOCK)


# ── Batch comparison ────────────────────────────────────────────────────

class TestBatchCompare:
    def test_batch_multiple_pairs(self, guard: RegressionTestGuard) -> None:
        pairs = [
            ("v1", "v2", "def f():\n    pass\n", "def f():\n    pass\n"),
            ("v1", "v2", "def g():\n    pass\n", "def h():\n    pass\n"),
        ]
        report = guard.batch_compare(pairs)
        assert len(report.results) == 2

    def test_batch_total_regressions(self, guard: RegressionTestGuard) -> None:
        pairs = [
            ("v1", "v2", "def a():\n    pass\n\ndef b():\n    pass\n", "def a():\n    pass\n"),
            ("v1", "v2", "def c():\n    pass\n", "def c():\n    pass\n"),
        ]
        report = guard.batch_compare(pairs)
        assert report.total_regressions >= 1

    def test_batch_gate_worst(self, strict_guard: RegressionTestGuard) -> None:
        pairs = [
            ("v1", "v2", "def f():\n    pass\n", "def f():\n    pass\n"),
            ("v1", "v2", "def a():\n    pass\n\ndef b():\n    pass\n", "pass\n"),
        ]
        report = strict_guard.batch_compare(pairs)
        assert report.gate_decision in (GateDecision.WARN, GateDecision.BLOCK)

    def test_batch_avg_score(self, guard: RegressionTestGuard) -> None:
        pairs = [
            ("v1", "v2", "def f():\n    pass\n", "def f():\n    pass\n"),
        ]
        report = guard.batch_compare(pairs)
        assert report.avg_regression_score >= 0.0
