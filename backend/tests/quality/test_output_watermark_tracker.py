"""Tests for Output Watermark Tracker."""

from __future__ import annotations

from app.quality.output_watermark_tracker import (
    AuditEntry,
    CodeOrigin,
    CoverageGrade,
    CoverageReport,
    FileAttribution,
    GateDecision,
    OutputWatermarkTracker,
    ProvenanceChain,
    Watermark,
    WatermarkConfig,
    _gate_from_coverage,
    _grade_coverage,
    _hash_content,
)

# ── _hash_content ───────────────────────────────────────────────────────

class TestHashContent:
    def test_deterministic(self):
        h1 = _hash_content("hello world")
        h2 = _hash_content("hello world")
        assert h1 == h2

    def test_different_inputs(self):
        h1 = _hash_content("hello")
        h2 = _hash_content("world")
        assert h1 != h2

    def test_length(self):
        h = _hash_content("test")
        assert len(h) == 16


# ── _grade_coverage ─────────────────────────────────────────────────────

class TestGradeCoverage:
    def test_low(self):
        cfg = WatermarkConfig()
        assert _grade_coverage(0.10, cfg) == CoverageGrade.LOW

    def test_moderate(self):
        cfg = WatermarkConfig()
        assert _grade_coverage(0.30, cfg) == CoverageGrade.MODERATE

    def test_high(self):
        cfg = WatermarkConfig()
        assert _grade_coverage(0.55, cfg) == CoverageGrade.HIGH

    def test_dominant(self):
        cfg = WatermarkConfig()
        assert _grade_coverage(0.80, cfg) == CoverageGrade.DOMINANT


# ── _gate_from_coverage ─────────────────────────────────────────────────

class TestGateFromCoverage:
    def test_low_passes(self):
        cfg = WatermarkConfig()
        assert _gate_from_coverage(0.30, cfg) == GateDecision.PASS

    def test_high_warns(self):
        cfg = WatermarkConfig()
        assert _gate_from_coverage(0.70, cfg) == GateDecision.WARN


# ── OutputWatermarkTracker ──────────────────────────────────────────────

class TestOutputWatermarkTracker:
    def test_create_watermark(self):
        tracker = OutputWatermarkTracker()
        wm = tracker.create_watermark(
            content="def foo(): pass",
            model="claude-3",
            agent="CodingAgent",
            prompt_version="v1",
            file_path="src/main.py",
            function_name="foo",
            line_start=1,
            line_end=5,
        )
        assert isinstance(wm, Watermark)
        assert wm.model == "claude-3"
        assert wm.agent == "CodingAgent"
        assert wm.line_count == 5
        assert wm.origin == CodeOrigin.AI_GENERATED

    def test_watermark_line_count(self):
        tracker = OutputWatermarkTracker()
        wm = tracker.create_watermark("code", line_start=10, line_end=20)
        assert wm.line_count == 11

    def test_watermark_creates_audit_entry(self):
        tracker = OutputWatermarkTracker()
        wm = tracker.create_watermark("code", agent="bot")
        trail = tracker.get_audit_trail(wm.watermark_id)
        assert len(trail) == 1
        assert trail[0].action == "created"

    def test_mark_reviewed(self):
        tracker = OutputWatermarkTracker()
        wm = tracker.create_watermark("code")
        entry = tracker.mark_reviewed(wm.watermark_id, "dev1", "looks good")
        assert isinstance(entry, AuditEntry)
        assert entry.action == "reviewed"
        trail = tracker.get_audit_trail(wm.watermark_id)
        assert len(trail) == 2

    def test_mark_modified(self):
        tracker = OutputWatermarkTracker()
        wm = tracker.create_watermark("code")
        tracker.mark_modified(wm.watermark_id, "dev1")
        assert wm.origin == CodeOrigin.AI_ASSISTED
        trail = tracker.get_audit_trail(wm.watermark_id)
        assert any(e.action == "modified" for e in trail)

    def test_get_provenance(self):
        tracker = OutputWatermarkTracker()
        wm = tracker.create_watermark(
            "code", model="gpt-4", agent="CodingAgent",
            prompt_version="v2", file_path="src/lib.py",
            function_name="bar",
        )
        prov = tracker.get_provenance(wm.watermark_id)
        assert isinstance(prov, ProvenanceChain)
        assert prov.model == "gpt-4"
        assert prov.agent == "CodingAgent"
        assert prov.file_path == "src/lib.py"

    def test_get_provenance_nonexistent(self):
        tracker = OutputWatermarkTracker()
        assert tracker.get_provenance("nonexistent") is None

    def test_file_attribution(self):
        tracker = OutputWatermarkTracker()
        tracker.create_watermark("code1", file_path="a.py", line_start=1, line_end=10)
        tracker.create_watermark("code2", file_path="a.py", line_start=11, line_end=15,
                                  origin=CodeOrigin.AI_ASSISTED)
        attr = tracker.get_file_attribution("a.py", total_lines=100)
        assert isinstance(attr, FileAttribution)
        assert attr.ai_generated_lines == 10
        assert attr.ai_assisted_lines == 5
        assert attr.human_written_lines == 85
        assert len(attr.watermarks) == 2

    def test_file_attribution_no_watermarks(self):
        tracker = OutputWatermarkTracker()
        attr = tracker.get_file_attribution("unknown.py", total_lines=50)
        assert attr.ai_generated_lines == 0
        assert attr.human_written_lines == 50

    def test_coverage_report(self):
        tracker = OutputWatermarkTracker()
        tracker.create_watermark("c1", model="claude", agent="CodingAgent",
                                  file_path="a.py", line_start=1, line_end=20)
        tracker.create_watermark("c2", model="gpt-4", agent="ReviewAgent",
                                  file_path="b.py", line_start=1, line_end=10)
        report = tracker.generate_coverage_report({"a.py": 100, "b.py": 50, "c.py": 200})
        assert isinstance(report, CoverageReport)
        assert report.total_files == 3
        assert report.total_lines == 350
        assert report.ai_generated_lines == 30
        assert "claude" in report.models_used
        assert "gpt-4" in report.models_used

    def test_coverage_report_empty(self):
        tracker = OutputWatermarkTracker()
        report = tracker.generate_coverage_report()
        assert report.total_files == 0
        assert report.total_lines == 0

    def test_high_ai_files(self):
        tracker = OutputWatermarkTracker(config=WatermarkConfig(max_ai_pct_per_file=0.50))
        tracker.create_watermark("code", file_path="x.py", line_start=1, line_end=90)
        report = tracker.generate_coverage_report({"x.py": 100})
        assert "x.py" in report.high_ai_files

    def test_audit_trail_all(self):
        tracker = OutputWatermarkTracker()
        wm1 = tracker.create_watermark("a")
        tracker.create_watermark("b")
        tracker.mark_reviewed(wm1.watermark_id, "dev")
        all_trail = tracker.get_audit_trail()
        assert len(all_trail) == 3  # 2 creates + 1 review

    def test_metadata(self):
        tracker = OutputWatermarkTracker()
        wm = tracker.create_watermark("code", metadata={"ticket": "PROJ-123"})
        assert wm.metadata["ticket"] == "PROJ-123"

    def test_coverage_grade_in_report(self):
        tracker = OutputWatermarkTracker()
        tracker.create_watermark("code", file_path="a.py", line_start=1, line_end=80)
        report = tracker.generate_coverage_report({"a.py": 100})
        assert report.grade == CoverageGrade.DOMINANT

    def test_custom_config_thresholds(self):
        cfg = WatermarkConfig(high_ai_threshold=0.30, require_review_above=0.20)
        tracker = OutputWatermarkTracker(config=cfg)
        tracker.create_watermark("code", file_path="a.py", line_start=1, line_end=25)
        report = tracker.generate_coverage_report({"a.py": 100})
        assert report.gate == GateDecision.WARN
