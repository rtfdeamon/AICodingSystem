"""Tests for AI Bill of Materials (AI-BOM) tracker."""

import pytest

from app.quality.ai_bom import (
    AIBOMTracker,
    ArtifactKind,
    LicenseRisk,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tracker():
    return AIBOMTracker()


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

class TestRegisterArtifact:
    def test_register_basic_artifact(self, tracker: AIBOMTracker):
        artifact = tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="claude-3-opus",
            model_version="20240229",
            prompt="Write a hello world function",
            content="def hello():\n    print('Hello')",
            ticket_id="TICKET-1",
            file_path="hello.py",
            token_count=100,
            cost_usd=0.003,
        )
        assert artifact.artifact_id.startswith("ai-")
        assert artifact.kind == ArtifactKind.CODE
        assert artifact.model_id == "claude-3-opus"
        assert artifact.model_version == "20240229"
        assert artifact.prompt_hash != ""
        assert artifact.content_hash != ""
        assert artifact.ticket_id == "TICKET-1"
        assert artifact.file_path == "hello.py"
        assert artifact.token_count == 100
        assert artifact.cost_usd == 0.003
        assert artifact.generated_at != ""

    def test_register_multiple_artifacts(self, tracker: AIBOMTracker):
        for i in range(5):
            tracker.register_artifact(
                kind=ArtifactKind.CODE,
                model_id="gpt-4",
                model_version="0613",
                prompt=f"prompt {i}",
                content=f"code {i}",
            )
        assert len(tracker.artifacts) == 5

    def test_artifact_unique_ids(self, tracker: AIBOMTracker):
        a1 = tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="claude-3",
            model_version="v1",
            prompt="p1",
            content="c1",
        )
        a2 = tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="claude-3",
            model_version="v1",
            prompt="p2",
            content="c2",
        )
        assert a1.artifact_id != a2.artifact_id

    def test_register_different_kinds(self, tracker: AIBOMTracker):
        for kind in ArtifactKind:
            tracker.register_artifact(
                kind=kind,
                model_id="test",
                model_version="v1",
                prompt="p",
                content="c",
            )
        assert len(tracker.artifacts) == len(ArtifactKind)

    def test_prompt_hash_deterministic(self, tracker: AIBOMTracker):
        a1 = tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="same prompt",
            content="c1",
        )
        a2 = tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="same prompt",
            content="c2",
        )
        assert a1.prompt_hash == a2.prompt_hash

    def test_different_prompts_different_hash(self, tracker: AIBOMTracker):
        a1 = tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="prompt A",
            content="c",
        )
        a2 = tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="prompt B",
            content="c",
        )
        assert a1.prompt_hash != a2.prompt_hash


# ---------------------------------------------------------------------------
# License scanning tests
# ---------------------------------------------------------------------------

class TestLicenseScanning:
    def test_clean_code_no_risk(self, tracker: AIBOMTracker):
        result = tracker.scan_license_risk("def hello():\n    return 42")
        assert result["overall_risk"] == LicenseRisk.NONE
        assert result["flags"] == []

    def test_detect_gpl_marker(self, tracker: AIBOMTracker):
        code = "# Licensed under GNU General Public License v3"
        result = tracker.scan_license_risk(code)
        assert result["overall_risk"] == LicenseRisk.HIGH
        assert any("GPL" in f for f in result["flags"])

    def test_detect_agpl_marker(self, tracker: AIBOMTracker):
        code = "# AGPL-3.0 License"
        result = tracker.scan_license_risk(code)
        assert result["overall_risk"] == LicenseRisk.HIGH

    def test_detect_lgpl_marker(self, tracker: AIBOMTracker):
        code = "# LGPL-2.1"
        result = tracker.scan_license_risk(code)
        assert result["overall_risk"] == LicenseRisk.MEDIUM

    def test_detect_mpl_marker(self, tracker: AIBOMTracker):
        code = "# Mozilla Public License 2.0"
        result = tracker.scan_license_risk(code)
        assert result["overall_risk"] == LicenseRisk.MEDIUM

    def test_detect_mit_as_low(self, tracker: AIBOMTracker):
        code = "# MIT License"
        result = tracker.scan_license_risk(code)
        assert result["overall_risk"] == LicenseRisk.LOW

    def test_detect_apache_as_low(self, tracker: AIBOMTracker):
        code = "# Apache License 2.0"
        result = tracker.scan_license_risk(code)
        assert result["overall_risk"] == LicenseRisk.LOW

    def test_detect_gpl_preamble(self, tracker: AIBOMTracker):
        code = "# This program is free software; you can redistribute it"
        result = tracker.scan_license_risk(code)
        assert result["overall_risk"] == LicenseRisk.HIGH
        assert any("GPL-preamble" in f for f in result["flags"])

    def test_detect_spdx_copyleft(self, tracker: AIBOMTracker):
        code = "# SPDX-License-Identifier: GPL-3.0"
        result = tracker.scan_license_risk(code)
        assert result["overall_risk"] == LicenseRisk.HIGH

    def test_detect_fsf_copyright(self, tracker: AIBOMTracker):
        code = "# Copyright (C) Free Software Foundation, Inc."
        result = tracker.scan_license_risk(code)
        assert result["overall_risk"] == LicenseRisk.HIGH

    def test_multiple_markers_highest_risk(self, tracker: AIBOMTracker):
        code = "# MIT License\n# Also GPLv3"
        result = tracker.scan_license_risk(code)
        assert result["overall_risk"] == LicenseRisk.HIGH

    def test_custom_signature(self, tracker: AIBOMTracker):
        tracker.add_known_signature(
            r"proprietary_lib\.init\(\)", "proprietary-lib", LicenseRisk.HIGH
        )
        code = "proprietary_lib.init()"
        result = tracker.scan_license_risk(code)
        assert result["overall_risk"] == LicenseRisk.HIGH
        assert any("proprietary-lib" in f for f in result["flags"])

    def test_artifact_gets_license_risk(self, tracker: AIBOMTracker):
        artifact = tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="p",
            content="# GNU General Public License\ndef foo(): pass",
        )
        assert artifact.license_risk == LicenseRisk.HIGH
        assert len(artifact.license_flags) > 0


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------

class TestBOMReport:
    def test_generate_empty_report(self, tracker: AIBOMTracker):
        report = tracker.generate_report("proj-1")
        assert report.project_id == "proj-1"
        assert report.report_id.startswith("bom-")
        assert len(report.artifacts) == 0
        assert report.total_cost_usd == 0.0
        assert report.total_tokens == 0

    def test_generate_report_with_artifacts(self, tracker: AIBOMTracker):
        tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="claude-3",
            model_version="v1",
            prompt="p1",
            content="def foo(): pass",
            token_count=50,
            cost_usd=0.001,
        )
        tracker.register_artifact(
            kind=ArtifactKind.TEST,
            model_id="gpt-4",
            model_version="v2",
            prompt="p2",
            content="def test_foo(): pass",
            token_count=30,
            cost_usd=0.002,
        )
        report = tracker.generate_report("proj-1")
        assert len(report.artifacts) == 2
        assert report.total_cost_usd == pytest.approx(0.003)
        assert report.total_tokens == 80
        assert "claude-3" in report.models_used
        assert "gpt-4" in report.models_used

    def test_report_license_summary(self, tracker: AIBOMTracker):
        tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="p",
            content="# GPLv3\ndef foo(): pass",
        )
        tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="p",
            content="def bar(): pass",
        )
        report = tracker.generate_report("proj-1")
        assert "high" in report.license_summary
        assert "none" in report.license_summary

    def test_report_to_dict(self, tracker: AIBOMTracker):
        tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="p",
            content="c",
        )
        report = tracker.generate_report("proj-1")
        d = report.to_dict()
        assert "report_id" in d
        assert "artifacts" in d
        assert d["artifact_count"] == 1


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------

class TestQueries:
    def test_get_high_risk_artifacts(self, tracker: AIBOMTracker):
        tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="p",
            content="# GPLv3\ndef foo(): pass",
        )
        tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="p",
            content="def bar(): pass",
        )
        high_risk = tracker.get_high_risk_artifacts()
        assert len(high_risk) == 1
        assert high_risk[0].license_risk == LicenseRisk.HIGH

    def test_get_artifacts_by_model(self, tracker: AIBOMTracker):
        tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="claude-3",
            model_version="v1",
            prompt="p1",
            content="c1",
        )
        tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="gpt-4",
            model_version="v1",
            prompt="p2",
            content="c2",
        )
        by_claude = tracker.get_artifacts_by_model("claude-3")
        assert len(by_claude) == 1
        assert by_claude[0].model_id == "claude-3"

    def test_get_artifacts_by_ticket(self, tracker: AIBOMTracker):
        tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="p",
            content="c",
            ticket_id="T-1",
        )
        tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="p",
            content="c",
            ticket_id="T-2",
        )
        by_ticket = tracker.get_artifacts_by_ticket("T-1")
        assert len(by_ticket) == 1

    def test_get_stats(self, tracker: AIBOMTracker):
        tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="m",
            model_version="v",
            prompt="p",
            content="c",
            token_count=100,
            cost_usd=0.01,
        )
        stats = tracker.get_stats()
        assert stats["total_artifacts"] == 1
        assert stats["total_cost_usd"] == 0.01
        assert stats["total_tokens"] == 100


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_artifact_to_dict(self, tracker: AIBOMTracker):
        artifact = tracker.register_artifact(
            kind=ArtifactKind.CODE,
            model_id="claude-3",
            model_version="v1",
            prompt="p",
            content="def foo(): pass",
        )
        d = artifact.to_dict()
        assert d["kind"] == "code"
        assert d["model_id"] == "claude-3"
        assert "artifact_id" in d
        assert "generated_at" in d
        assert "license_risk" in d
