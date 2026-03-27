"""Tests for app.agents.security_agent — security analysis."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.base import AgentResponse
from app.agents.security_agent import (
    SecurityReport,
    Vulnerability,
    _parse_security_output,
    _run_semgrep,
    analyze_security,
)

# ── _parse_security_output ───────────────────────────────────────────


class TestParseSecurityOutput:
    def test_valid_json(self) -> None:
        raw = json.dumps(
            {
                "vulnerabilities": [
                    {
                        "id": "VULN-001",
                        "title": "SQL Injection",
                        "severity": "critical",
                        "file_path": "app/db.py",
                        "line_range": [10, 15],
                        "description": "Unsanitized input in query",
                        "cwe_id": "CWE-89",
                        "remediation": "Use parameterized queries",
                    }
                ],
                "recommendations": ["Add input validation"],
            }
        )
        vulns, recs = _parse_security_output(raw)
        assert len(vulns) == 1
        assert vulns[0].id == "VULN-001"
        assert vulns[0].severity == "critical"
        assert vulns[0].cwe_id == "CWE-89"
        assert vulns[0].line_range == [10, 15]
        assert len(recs) == 1
        assert recs[0] == "Add input validation"

    def test_strips_markdown_fences(self) -> None:
        inner = json.dumps({"vulnerabilities": [], "recommendations": ["Use HTTPS"]})
        raw = f"```json\n{inner}\n```"
        vulns, recs = _parse_security_output(raw)
        assert vulns == []
        assert recs == ["Use HTTPS"]

    def test_strips_plain_fences(self) -> None:
        inner = json.dumps({"vulnerabilities": [], "recommendations": []})
        raw = f"```\n{inner}\n```"
        vulns, recs = _parse_security_output(raw)
        assert vulns == []

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid JSON"):
            _parse_security_output("not json")

    def test_missing_fields_default_gracefully(self) -> None:
        raw = json.dumps(
            {
                "vulnerabilities": [
                    {
                        "title": "XSS",
                        "severity": "high",
                        "file_path": "templates/index.html",
                    }
                ],
                "recommendations": [],
            }
        )
        vulns, _ = _parse_security_output(raw)
        assert len(vulns) == 1
        assert vulns[0].id == "UNKNOWN"
        assert vulns[0].description == ""
        assert vulns[0].cwe_id is None
        assert vulns[0].remediation == ""
        assert vulns[0].line_range is None

    def test_empty_vulnerabilities(self) -> None:
        raw = json.dumps({"vulnerabilities": [], "recommendations": []})
        vulns, recs = _parse_security_output(raw)
        assert vulns == []
        assert recs == []

    def test_multiple_vulnerabilities(self) -> None:
        raw = json.dumps(
            {
                "vulnerabilities": [
                    {"id": "V1", "title": "A", "severity": "high", "file_path": "a.py"},
                    {"id": "V2", "title": "B", "severity": "low", "file_path": "b.py"},
                ],
                "recommendations": [],
            }
        )
        vulns, _ = _parse_security_output(raw)
        assert len(vulns) == 2


# ── _run_semgrep ─────────────────────────────────────────────────────


class TestRunSemgrep:
    async def test_empty_files_returns_empty(self, tmp_path: Path) -> None:
        result = await _run_semgrep(tmp_path, [])
        assert result == []

    async def test_nonexistent_files_returns_empty(self, tmp_path: Path) -> None:
        result = await _run_semgrep(tmp_path, ["ghost.py"])
        assert result == []

    async def test_semgrep_not_installed(self, tmp_path: Path) -> None:
        (tmp_path / "test.py").write_text("x = 1")
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            result = await _run_semgrep(tmp_path, ["test.py"])
        assert result == []

    async def test_semgrep_timeout(self, tmp_path: Path) -> None:
        (tmp_path / "test.py").write_text("x = 1")
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await _run_semgrep(tmp_path, ["test.py"])
        assert result == []

    async def test_semgrep_empty_output(self, tmp_path: Path) -> None:
        (tmp_path / "test.py").write_text("x = 1")
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await _run_semgrep(tmp_path, ["test.py"])
        assert result == []

    async def test_semgrep_success_with_findings(self, tmp_path: Path) -> None:
        (tmp_path / "test.py").write_text("x = 1")
        output = json.dumps(
            {
                "results": [
                    {
                        "check_id": "python.security.eval-usage",
                        "extra": {
                            "message": "Avoid eval()",
                            "severity": "WARNING",
                        },
                        "path": "test.py",
                        "start": {"line": 5},
                        "end": {"line": 5},
                    }
                ]
            }
        )
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(output.encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await _run_semgrep(tmp_path, ["test.py"])
        assert len(result) == 1
        assert result[0]["rule_id"] == "python.security.eval-usage"
        assert result[0]["start_line"] == 5

    async def test_semgrep_invalid_json_output(self, tmp_path: Path) -> None:
        (tmp_path / "test.py").write_text("x = 1")
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"not json", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await _run_semgrep(tmp_path, ["test.py"])
        assert result == []


# ── SecurityReport ───────────────────────────────────────────────────


class TestSecurityReport:
    def test_has_critical_true(self) -> None:
        report = SecurityReport(severity_counts={"critical": 1})
        assert report.has_critical is True

    def test_has_critical_false(self) -> None:
        report = SecurityReport(severity_counts={"critical": 0})
        assert report.has_critical is False

    def test_has_critical_missing_key(self) -> None:
        report = SecurityReport(severity_counts={})
        assert report.has_critical is False

    def test_total_findings(self) -> None:
        report = SecurityReport(
            vulnerabilities=[
                Vulnerability(
                    id="V1",
                    title="A",
                    severity="high",
                    file_path="a.py",
                )
            ],
            sast_findings=[{"rule_id": "test"}],
        )
        assert report.total_findings == 2

    def test_total_findings_empty(self) -> None:
        report = SecurityReport()
        assert report.total_findings == 0


# ── Vulnerability ────────────────────────────────────────────────────


class TestVulnerability:
    def test_defaults(self) -> None:
        v = Vulnerability(id="V1", title="Test", severity="low", file_path="test.py")
        assert v.line_range is None
        assert v.description == ""
        assert v.cwe_id is None
        assert v.remediation == ""


# ── analyze_security (integration-level with mocks) ──────────────────


class TestAnalyzeSecurity:
    async def test_basic_analysis_no_sast(self) -> None:
        ai_response = AgentResponse(
            content=json.dumps(
                {
                    "vulnerabilities": [
                        {
                            "id": "VULN-001",
                            "title": "XSS",
                            "severity": "high",
                            "file_path": "template.html",
                            "description": "Reflected XSS",
                        }
                    ],
                    "recommendations": ["Escape user input"],
                }
            ),
            model_id="test-model",
            prompt_tokens=100,
            completion_tokens=200,
        )

        with (
            patch(
                "app.agents.security_agent.route_task",
                return_value=AsyncMock(name="claude"),
            ),
            patch(
                "app.agents.security_agent.execute_with_fallback",
                return_value=ai_response,
            ),
        ):
            report = await analyze_security(
                diff="+ dangerous code",
                file_contents={"template.html": "<div>{{ user_input }}</div>"},
            )

        assert isinstance(report, SecurityReport)
        assert len(report.vulnerabilities) == 1
        assert report.vulnerabilities[0].severity == "high"
        assert report.severity_counts["high"] == 1
        assert "Escape user input" in report.recommendations

    async def test_analysis_with_sast(self, tmp_path: Path) -> None:
        ai_response = AgentResponse(
            content=json.dumps({"vulnerabilities": [], "recommendations": []}),
            model_id="test-model",
        )

        sast_findings = [
            {
                "rule_id": "test-rule",
                "message": "Warning",
                "severity": "WARNING",
                "file_path": "app.py",
                "start_line": 1,
                "end_line": 1,
            }
        ]

        (tmp_path / "app.py").write_text("code")

        with (
            patch(
                "app.agents.security_agent.route_task",
                return_value=AsyncMock(name="claude"),
            ),
            patch(
                "app.agents.security_agent.execute_with_fallback",
                return_value=ai_response,
            ),
            patch(
                "app.agents.security_agent._run_semgrep",
                return_value=sast_findings,
            ),
        ):
            report = await analyze_security(
                diff="+ code",
                file_contents={"app.py": "code"},
                repo_path=tmp_path,
                changed_files=["app.py"],
            )

        assert len(report.sast_findings) == 1
        # WARNING maps to "medium"
        assert report.severity_counts["medium"] >= 1

    async def test_truncates_large_file_contents(self) -> None:
        ai_response = AgentResponse(
            content=json.dumps({"vulnerabilities": [], "recommendations": []}),
            model_id="test-model",
        )

        # Create many files that exceed the 20K char limit
        large_contents = {f"file_{i}.py": "x" * 4000 for i in range(10)}

        with (
            patch(
                "app.agents.security_agent.route_task",
                return_value=AsyncMock(name="claude"),
            ),
            patch(
                "app.agents.security_agent.execute_with_fallback",
                return_value=ai_response,
            ),
        ):
            report = await analyze_security(
                diff="+ code",
                file_contents=large_contents,
            )
        # Should not raise, report is valid
        assert isinstance(report, SecurityReport)

    async def test_empty_file_contents(self) -> None:
        ai_response = AgentResponse(
            content=json.dumps({"vulnerabilities": [], "recommendations": []}),
            model_id="test-model",
        )

        with (
            patch(
                "app.agents.security_agent.route_task",
                return_value=AsyncMock(name="claude"),
            ),
            patch(
                "app.agents.security_agent.execute_with_fallback",
                return_value=ai_response,
            ),
        ):
            report = await analyze_security(
                diff="+ code",
                file_contents={},
            )
        assert isinstance(report, SecurityReport)

    async def test_severity_counts_populated(self) -> None:
        ai_response = AgentResponse(
            content=json.dumps(
                {
                    "vulnerabilities": [
                        {"id": "V1", "title": "A", "severity": "critical", "file_path": "a.py"},
                        {"id": "V2", "title": "B", "severity": "critical", "file_path": "b.py"},
                        {"id": "V3", "title": "C", "severity": "low", "file_path": "c.py"},
                    ],
                    "recommendations": [],
                }
            ),
            model_id="test-model",
        )

        with (
            patch(
                "app.agents.security_agent.route_task",
                return_value=AsyncMock(name="claude"),
            ),
            patch(
                "app.agents.security_agent.execute_with_fallback",
                return_value=ai_response,
            ),
        ):
            report = await analyze_security(diff="+ code", file_contents={})

        assert report.severity_counts["critical"] == 2
        assert report.severity_counts["low"] == 1
        assert report.has_critical is True
