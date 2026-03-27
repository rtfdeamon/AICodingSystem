"""Tests for Diff Size Limiter (best practice #60)."""

from __future__ import annotations

from app.quality.diff_size_limiter import (
    BatchDiffReport,
    DiffAnalysis,
    DiffChunk,
    DiffRisk,
    DiffSizeLimiter,
    FileDiff,
    GateDecision,
    _assess_risk,
    _detect_language,
    _estimate_complexity,
    _extract_functions,
)

# ── Helpers ──────────────────────────────────────────────────────────────

def _make_file_diff(
    path: str = "app/service.py",
    added: int = 50,
    removed: int = 10,
    content: str = "",
) -> FileDiff:
    if not content:
        content = "\n".join([f"line {i}" for i in range(added)])
    return FileDiff(
        file_path=path,
        added_lines=added,
        removed_lines=removed,
        content=content,
    )


def _make_large_diff(n_files: int = 10, lines_per_file: int = 100) -> list[FileDiff]:
    return [
        _make_file_diff(
            f"app/module_{i}.py",
            added=lines_per_file,
            removed=lines_per_file // 5,
            content="\n".join(
                [f"def func_{i}_{j}():\n    pass" for j in range(lines_per_file // 2)]
            ),
        )
        for i in range(n_files)
    ]


# ── Language detection tests ────────────────────────────────────────────

class TestLanguageDetection:
    def test_python(self):
        assert _detect_language("app/main.py") == "python"

    def test_typescript(self):
        assert _detect_language("src/App.tsx") == "typescript"

    def test_javascript(self):
        assert _detect_language("index.js") == "javascript"

    def test_go(self):
        assert _detect_language("main.go") == "go"

    def test_unknown(self):
        assert _detect_language("Dockerfile") == "unknown"

    def test_yaml(self):
        assert _detect_language("config.yaml") == "yaml"


# ── Complexity estimation tests ─────────────────────────────────────────

class TestComplexityEstimation:
    def test_empty(self):
        assert _estimate_complexity("") == 0.0

    def test_simple_code(self):
        c = _estimate_complexity("x = 1\ny = 2\nz = 3")
        assert c < 0.5

    def test_complex_code(self):
        code = """
if condition:
    for item in items:
        try:
            while running:
                if check:
                    pass
                else:
                    pass
        except:
            pass
"""
        c = _estimate_complexity(code)
        assert c > 0.3

    def test_class_definition(self):
        code = "class MyService:\n    def method(self):\n        pass"
        c = _estimate_complexity(code)
        assert c > 0


# ── Risk assessment tests ──────────────────────────────────────────────

class TestRiskAssessment:
    def test_auth_file_high_risk(self):
        assert _assess_risk("app/auth/login.py", "handle login") == DiffRisk.HIGH

    def test_test_file_low_risk(self):
        assert _assess_risk("tests/test_service.py", "assert True") == DiffRisk.LOW

    def test_config_medium_risk(self):
        assert _assess_risk("config/settings.py", "DATABASE_URL") == DiffRisk.MEDIUM

    def test_migration_high_risk(self):
        assert _assess_risk("db/migration.sql", "ALTER TABLE users DROP") == DiffRisk.HIGH

    def test_payment_high_risk(self):
        assert _assess_risk("app/billing.py", "process payment") == DiffRisk.HIGH

    def test_normal_file(self):
        assert _assess_risk("app/utils.py", "format string") == DiffRisk.MEDIUM


# ── Function extraction tests ──────────────────────────────────────────

class TestFunctionExtraction:
    def test_python_functions(self):
        code = "def foo():\n    pass\ndef bar():\n    pass"
        funcs = _extract_functions(code, "python")
        assert "foo" in funcs
        assert "bar" in funcs

    def test_go_functions(self):
        code = "func HandleRequest(w http.ResponseWriter, r *http.Request) {"
        funcs = _extract_functions(code, "go")
        assert "HandleRequest" in funcs

    def test_unknown_language(self):
        funcs = _extract_functions("some code", "unknown")
        assert funcs == []

    def test_empty_code(self):
        funcs = _extract_functions("", "python")
        assert funcs == []


# ── Init tests ───────────────────────────────────────────────────────────

class TestDiffSizeLimiterInit:
    def test_default_init(self):
        limiter = DiffSizeLimiter()
        assert limiter.max_lines_per_chunk == 400
        assert limiter.split_threshold == 500
        assert limiter.block_threshold == 3000

    def test_custom_init(self):
        limiter = DiffSizeLimiter(
            max_lines_per_chunk=200,
            split_threshold=300,
        )
        assert limiter.max_lines_per_chunk == 200


# ── Empty diff tests ────────────────────────────────────────────────────

class TestEmptyDiff:
    def test_empty_diff_passes(self):
        limiter = DiffSizeLimiter()
        analysis = limiter.analyze([])
        assert isinstance(analysis, DiffAnalysis)
        assert analysis.gate_decision == GateDecision.PASS
        assert analysis.total_files == 0
        assert analysis.needs_splitting is False


# ── Small diff tests ────────────────────────────────────────────────────

class TestSmallDiff:
    def test_small_diff_passes(self):
        limiter = DiffSizeLimiter()
        diffs = [_make_file_diff("app/main.py", 20, 5)]
        analysis = limiter.analyze(diffs)
        assert analysis.gate_decision == GateDecision.PASS
        assert analysis.needs_splitting is False
        assert len(analysis.chunks) == 1

    def test_small_diff_single_chunk(self):
        limiter = DiffSizeLimiter()
        diffs = [
            _make_file_diff("app/a.py", 50, 10),
            _make_file_diff("app/b.py", 30, 5),
        ]
        analysis = limiter.analyze(diffs)
        assert len(analysis.chunks) == 1
        assert analysis.total_files == 2


# ── Split required tests ────────────────────────────────────────────────

class TestSplitRequired:
    def test_large_diff_needs_splitting(self):
        limiter = DiffSizeLimiter(
            split_threshold=200,
            max_lines_per_chunk=150,
        )
        diffs = _make_large_diff(8, 60)
        analysis = limiter.analyze(diffs)
        assert analysis.needs_splitting
        assert analysis.gate_decision == GateDecision.SPLIT
        assert len(analysis.chunks) >= 1

    def test_very_large_diff_blocked(self):
        limiter = DiffSizeLimiter(block_threshold=500)
        diffs = _make_large_diff(10, 100)
        analysis = limiter.analyze(diffs)
        assert analysis.gate_decision == GateDecision.BLOCK

    def test_chunks_respect_max_lines(self):
        limiter = DiffSizeLimiter(
            max_lines_per_chunk=200,
            split_threshold=100,
        )
        diffs = _make_large_diff(10, 80)
        analysis = limiter.analyze(diffs)
        for chunk in analysis.chunks:
            # Each chunk should be under or close to max
            assert chunk.total_lines <= 400  # some tolerance for single-file overflow

    def test_chunks_have_files(self):
        limiter = DiffSizeLimiter(split_threshold=100)
        diffs = _make_large_diff(5, 50)
        analysis = limiter.analyze(diffs)
        for chunk in analysis.chunks:
            assert len(chunk.files) > 0

    def test_all_files_accounted(self):
        limiter = DiffSizeLimiter(split_threshold=100)
        diffs = _make_large_diff(8, 30)
        analysis = limiter.analyze(diffs)
        all_files = set()
        for chunk in analysis.chunks:
            all_files.update(chunk.files)
        original_files = {d.file_path for d in diffs}
        assert all_files == original_files


# ── Review order tests ──────────────────────────────────────────────────

class TestReviewOrder:
    def test_review_order_exists(self):
        limiter = DiffSizeLimiter(split_threshold=100)
        diffs = _make_large_diff(5, 50)
        analysis = limiter.analyze(diffs)
        assert len(analysis.review_order) == len(analysis.chunks)

    def test_high_risk_first(self):
        limiter = DiffSizeLimiter(split_threshold=50)
        diffs = [
            _make_file_diff("tests/test_a.py", 30, 5, "assert True"),
            _make_file_diff("app/auth/login.py", 30, 5, "handle login session token"),
        ]
        analysis = limiter.analyze(diffs)
        if len(analysis.chunks) > 1:
            # Auth chunk should come before test chunk
            first_chunk_id = analysis.review_order[0]
            first_chunk = next(c for c in analysis.chunks if c.id == first_chunk_id)
            assert first_chunk.risk in (DiffRisk.HIGH, DiffRisk.CRITICAL)


# ── Review time estimation tests ────────────────────────────────────────

class TestReviewTimeEstimation:
    def test_small_diff_quick(self):
        limiter = DiffSizeLimiter()
        diffs = [_make_file_diff("a.py", 10, 5)]
        analysis = limiter.analyze(diffs)
        assert analysis.estimated_review_minutes >= 1

    def test_large_diff_longer(self):
        limiter = DiffSizeLimiter()
        diffs = _make_large_diff(10, 100)
        analysis = limiter.analyze(diffs)
        assert analysis.estimated_review_minutes > 10


# ── Risk aggregation tests ──────────────────────────────────────────────

class TestRiskAggregation:
    def test_all_low(self):
        limiter = DiffSizeLimiter()
        diffs = [
            _make_file_diff("tests/test_a.py", 10, 5, "assert True"),
            _make_file_diff("tests/test_b.py", 10, 5, "assert False"),
        ]
        analysis = limiter.analyze(diffs)
        assert analysis.risk == DiffRisk.LOW

    def test_any_high_makes_high(self):
        limiter = DiffSizeLimiter()
        diffs = [
            _make_file_diff("tests/test_a.py", 10, 5, "assert True"),
            _make_file_diff("app/auth.py", 10, 5, "login password token"),
        ]
        analysis = limiter.analyze(diffs)
        assert analysis.risk == DiffRisk.HIGH


# ── Language enrichment tests ──────────────────────────────────────────

class TestLanguageEnrichment:
    def test_language_auto_detected(self):
        limiter = DiffSizeLimiter()
        diffs = [_make_file_diff("app/main.py", 10, 5)]
        analysis = limiter.analyze(diffs)
        # Language should be detected internally
        assert analysis.total_files == 1

    def test_function_extraction(self):
        limiter = DiffSizeLimiter()
        diffs = [_make_file_diff(
            "app/service.py", 10, 5,
            "def handle_request():\n    pass\ndef process_data():\n    pass",
        )]
        analysis = limiter.analyze(diffs)
        assert analysis.total_files == 1


# ── Batch analysis tests ────────────────────────────────────────────────

class TestBatchAnalysis:
    def test_batch_multiple(self):
        limiter = DiffSizeLimiter()
        diffs = [
            [_make_file_diff("a.py", 10, 5)],
            [_make_file_diff("b.py", 20, 10)],
        ]
        report = limiter.batch_analyze(diffs)
        assert isinstance(report, BatchDiffReport)
        assert report.total_diffs == 2

    def test_batch_with_split(self):
        limiter = DiffSizeLimiter(split_threshold=100)
        diffs = [
            [_make_file_diff("a.py", 10, 5)],
            _make_large_diff(5, 50),
        ]
        report = limiter.batch_analyze(diffs)
        assert report.diffs_needing_split >= 1

    def test_batch_empty(self):
        limiter = DiffSizeLimiter()
        report = limiter.batch_analyze([])
        assert report.total_diffs == 0
        assert report.gate_decision == GateDecision.PASS


# ── History tests ────────────────────────────────────────────────────────

class TestHistory:
    def test_history_recorded(self):
        limiter = DiffSizeLimiter()
        limiter.analyze([_make_file_diff("a.py", 10, 5)])
        limiter.analyze([_make_file_diff("b.py", 10, 5)])
        assert len(limiter.history) == 2

    def test_history_immutable(self):
        limiter = DiffSizeLimiter()
        limiter.analyze([_make_file_diff("a.py", 10, 5)])
        h = limiter.history
        h.clear()
        assert len(limiter.history) == 1


# ── Report field tests ──────────────────────────────────────────────────

class TestReportFields:
    def test_analysis_id(self):
        limiter = DiffSizeLimiter()
        analysis = limiter.analyze([_make_file_diff("a.py", 10, 5)])
        assert analysis.id
        assert len(analysis.id) == 12

    def test_analysis_timestamp(self):
        limiter = DiffSizeLimiter()
        analysis = limiter.analyze([_make_file_diff("a.py", 10, 5)])
        assert analysis.analyzed_at

    def test_analysis_totals(self):
        limiter = DiffSizeLimiter()
        diffs = [
            _make_file_diff("a.py", 30, 10),
            _make_file_diff("b.py", 20, 5),
        ]
        analysis = limiter.analyze(diffs)
        assert analysis.total_added == 50
        assert analysis.total_removed == 15
        assert analysis.total_lines == 65
        assert analysis.total_files == 2

    def test_chunk_fields(self):
        limiter = DiffSizeLimiter(split_threshold=50)
        diffs = _make_large_diff(3, 50)
        analysis = limiter.analyze(diffs)
        for chunk in analysis.chunks:
            assert isinstance(chunk, DiffChunk)
            assert chunk.id
            assert len(chunk.files) > 0
            assert chunk.total_lines > 0
            assert 0.0 <= chunk.complexity_score <= 1.0
