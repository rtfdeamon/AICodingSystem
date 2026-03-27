"""Tests for Code Attribution Tracker.

Covers: attribution recording, review management, queries,
summaries, compliance reporting, and license risk assessment.
"""

from __future__ import annotations

from app.quality.code_attribution import (
    AttributionRecord,
    AuthorshipType,
    CodeAttributionTracker,
    LicenseRisk,
    ReviewStatus,
)

# ── AttributionRecord ───────────────────────────────────────────────────

class TestAttributionRecord:
    def test_default_values(self):
        r = AttributionRecord()
        assert r.id != ""
        assert r.authorship == AuthorshipType.UNKNOWN
        assert r.review_status == ReviewStatus.UNREVIEWED

    def test_custom_values(self):
        r = AttributionRecord(
            file_path="src/main.py",
            authorship=AuthorshipType.AI_GENERATED,
            model_id="claude-sonnet-4",
        )
        assert r.file_path == "src/main.py"
        assert r.model_id == "claude-sonnet-4"


# ── Recording ────────────────────────────────────────────────────────────

class TestRecording:
    def test_record_basic(self):
        tracker = CodeAttributionTracker()
        rec = tracker.record(
            file_path="src/app.py",
            authorship=AuthorshipType.AI_GENERATED,
            model_id="claude-sonnet-4",
            model_provider="anthropic",
        )
        assert rec.file_path == "src/app.py"
        assert rec.authorship == AuthorshipType.AI_GENERATED
        assert tracker.record_count == 1

    def test_record_with_content_hash(self):
        tracker = CodeAttributionTracker()
        rec = tracker.record(
            file_path="src/lib.py",
            authorship=AuthorshipType.AI_ASSISTED,
            content="def hello(): pass",
        )
        assert rec.content_hash != ""

    def test_record_with_lines(self):
        tracker = CodeAttributionTracker()
        rec = tracker.record(
            file_path="src/utils.py",
            authorship=AuthorshipType.HUMAN_WRITTEN,
            line_start=10,
            line_end=25,
            function_name="process_data",
        )
        assert rec.line_start == 10
        assert rec.line_end == 25
        assert rec.function_name == "process_data"

    def test_record_with_tags(self):
        tracker = CodeAttributionTracker()
        rec = tracker.record(
            file_path="src/x.py",
            authorship=AuthorshipType.AI_GENERATED,
            tags={"agent": "coding", "iteration": "3"},
        )
        assert rec.tags["agent"] == "coding"

    def test_record_license_risk_auto(self):
        tracker = CodeAttributionTracker()
        rec = tracker.record(
            file_path="src/x.py",
            authorship=AuthorshipType.AI_GENERATED,
            content="# Copyright (c) 2024 Some Corp. All rights reserved.",
        )
        assert rec.license_risk == LicenseRisk.HIGH


# ── Review management ────────────────────────────────────────────────────

class TestReviewManagement:
    def test_mark_reviewed(self):
        tracker = CodeAttributionTracker()
        rec = tracker.record(
            file_path="x.py",
            authorship=AuthorshipType.AI_GENERATED,
        )
        assert tracker.mark_reviewed(
            rec.id, "alice", ReviewStatus.HUMAN_REVIEWED
        )
        assert rec.review_status == ReviewStatus.HUMAN_REVIEWED
        assert rec.reviewer == "alice"
        assert rec.reviewed_at is not None

    def test_mark_approved(self):
        tracker = CodeAttributionTracker()
        rec = tracker.record(
            file_path="x.py",
            authorship=AuthorshipType.AI_GENERATED,
        )
        tracker.mark_reviewed(rec.id, "bob", ReviewStatus.APPROVED)
        assert rec.review_status == ReviewStatus.APPROVED

    def test_mark_nonexistent(self):
        tracker = CodeAttributionTracker()
        assert not tracker.mark_reviewed("fake-id", "alice")


# ── Queries ──────────────────────────────────────────────────────────────

class TestQueries:
    def _setup_tracker(self):
        tracker = CodeAttributionTracker()
        tracker.record(
            file_path="src/a.py", authorship=AuthorshipType.AI_GENERATED,
            ticket_id="T-1", project_id="P-1",
        )
        tracker.record(
            file_path="src/a.py", authorship=AuthorshipType.HUMAN_WRITTEN,
            ticket_id="T-1", project_id="P-1",
        )
        tracker.record(
            file_path="src/b.py", authorship=AuthorshipType.AI_ASSISTED,
            ticket_id="T-2", project_id="P-1",
        )
        return tracker

    def test_by_file(self):
        tracker = self._setup_tracker()
        records = tracker.by_file("src/a.py")
        assert len(records) == 2

    def test_by_ticket(self):
        tracker = self._setup_tracker()
        records = tracker.by_ticket("T-1")
        assert len(records) == 2

    def test_by_project(self):
        tracker = self._setup_tracker()
        records = tracker.by_project("P-1")
        assert len(records) == 3

    def test_unreviewed(self):
        tracker = self._setup_tracker()
        unreview = tracker.unreviewed()
        assert len(unreview) == 2

    def test_high_risk(self):
        tracker = CodeAttributionTracker()
        tracker.record(
            file_path="x.py",
            authorship=AuthorshipType.AI_GENERATED,
            content="# GPL License header here",
        )
        assert len(tracker.high_risk()) >= 1


# ── Summary ──────────────────────────────────────────────────────────────

class TestSummary:
    def test_empty_summary(self):
        tracker = CodeAttributionTracker()
        s = tracker.summary()
        assert s.total_records == 0

    def test_summary_counts(self):
        tracker = CodeAttributionTracker()
        tracker.record("a.py", AuthorshipType.AI_GENERATED)
        tracker.record("b.py", AuthorshipType.AI_GENERATED)
        tracker.record("c.py", AuthorshipType.HUMAN_WRITTEN)
        s = tracker.summary()
        assert s.total_records == 3
        assert s.ai_generated_count == 2
        assert s.human_written_count == 1
        assert s.ai_percentage > 0

    def test_summary_by_project(self):
        tracker = CodeAttributionTracker()
        tracker.record("a.py", AuthorshipType.AI_GENERATED, project_id="P-1")
        tracker.record("b.py", AuthorshipType.AI_GENERATED, project_id="P-2")
        s = tracker.summary(project_id="P-1")
        assert s.total_records == 1

    def test_summary_models_used(self):
        tracker = CodeAttributionTracker()
        tracker.record(
            "a.py", AuthorshipType.AI_GENERATED,
            model_id="claude-sonnet-4",
        )
        tracker.record(
            "b.py", AuthorshipType.AI_GENERATED,
            model_id="gpt-4o",
        )
        s = tracker.summary()
        assert "claude-sonnet-4" in s.models_used
        assert "gpt-4o" in s.models_used

    def test_summary_reviewed_count(self):
        tracker = CodeAttributionTracker()
        rec = tracker.record("a.py", AuthorshipType.AI_GENERATED)
        tracker.mark_reviewed(rec.id, "alice")
        s = tracker.summary()
        assert s.reviewed_count == 1
        assert s.unreviewed_count == 0


# ── Compliance report ────────────────────────────────────────────────────

class TestComplianceReport:
    def test_compliant_project(self):
        tracker = CodeAttributionTracker()
        rec = tracker.record(
            "a.py", AuthorshipType.AI_GENERATED, project_id="P-1"
        )
        tracker.mark_reviewed(rec.id, "alice", ReviewStatus.APPROVED)
        report = tracker.compliance_report("P-1")
        assert report.compliant
        assert len(report.issues) == 0

    def test_non_compliant_unreviewed(self):
        tracker = CodeAttributionTracker()
        tracker.record(
            "a.py", AuthorshipType.AI_GENERATED, project_id="P-1"
        )
        report = tracker.compliance_report("P-1", require_review=True)
        assert not report.compliant
        assert any("review" in i.lower() for i in report.issues)

    def test_non_compliant_ai_percentage(self):
        tracker = CodeAttributionTracker()
        rec = tracker.record(
            "a.py", AuthorshipType.AI_GENERATED, project_id="P-1"
        )
        tracker.mark_reviewed(rec.id, "alice")
        report = tracker.compliance_report(
            "P-1", require_review=True, max_ai_percentage=50.0
        )
        assert not report.compliant

    def test_non_compliant_license_risk(self):
        tracker = CodeAttributionTracker()
        rec = tracker.record(
            "a.py", AuthorshipType.AI_GENERATED,
            project_id="P-1",
            content="# Copyright GPL v3",
        )
        tracker.mark_reviewed(rec.id, "alice")
        report = tracker.compliance_report("P-1")
        assert not report.compliant
        assert len(report.high_risk_records) >= 1

    def test_empty_project(self):
        tracker = CodeAttributionTracker()
        report = tracker.compliance_report("P-empty")
        assert report.compliant


# ── License risk ─────────────────────────────────────────────────────────

class TestLicenseRisk:
    def test_human_written_no_risk(self):
        risk = CodeAttributionTracker._assess_license_risk(
            AuthorshipType.HUMAN_WRITTEN, None, None
        )
        assert risk == LicenseRisk.NONE

    def test_unknown_medium_risk(self):
        risk = CodeAttributionTracker._assess_license_risk(
            AuthorshipType.UNKNOWN, None, None
        )
        assert risk == LicenseRisk.MEDIUM

    def test_gpl_content_high_risk(self):
        risk = CodeAttributionTracker._assess_license_risk(
            AuthorshipType.AI_GENERATED, "claude-sonnet-4",
            "This code is under GPL license",
        )
        assert risk == LicenseRisk.HIGH

    def test_old_model_medium_risk(self):
        risk = CodeAttributionTracker._assess_license_risk(
            AuthorshipType.AI_GENERATED, "code-davinci-002", None
        )
        assert risk == LicenseRisk.MEDIUM

    def test_modern_model_low_risk(self):
        risk = CodeAttributionTracker._assess_license_risk(
            AuthorshipType.AI_GENERATED, "claude-sonnet-4", "def hello(): pass"
        )
        assert risk == LicenseRisk.LOW


# ── Clear ────────────────────────────────────────────────────────────────

class TestClear:
    def test_clear(self):
        tracker = CodeAttributionTracker()
        tracker.record("a.py", AuthorshipType.AI_GENERATED)
        tracker.clear()
        assert tracker.record_count == 0
