"""Tests for the security scanner module."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ci.security_scanner import (
    ScanResult,
    Vulnerability,
    _audit_npm_deps,
    _audit_python_deps,
    _normalize_severity,
    _run_bandit,
    _run_semgrep,
    _run_subprocess,
    run_dependency_audit,
    run_sast,
)

pytestmark = pytest.mark.asyncio

_TEST_PROJECT = "/var/test/project"  # noqa: S105


# ── _normalize_severity ──────────────────────────────────────────────


def test_normalize_critical() -> None:
    assert _normalize_severity("CRITICAL") == "critical"
    assert _normalize_severity("ERROR") == "critical"


def test_normalize_high() -> None:
    assert _normalize_severity("HIGH") == "high"
    assert _normalize_severity("WARNING") == "high"


def test_normalize_medium() -> None:
    assert _normalize_severity("MEDIUM") == "medium"
    assert _normalize_severity("MODERATE") == "medium"
    assert _normalize_severity("INFO") == "medium"


def test_normalize_low() -> None:
    assert _normalize_severity("LOW") == "low"
    assert _normalize_severity("unknown") == "low"
    assert _normalize_severity("") == "low"


def test_normalize_case_insensitive() -> None:
    assert _normalize_severity("Critical") == "critical"
    assert _normalize_severity("high") == "high"
    assert _normalize_severity("Medium") == "medium"
    assert _normalize_severity("moderate") == "medium"


# ── ScanResult dataclass ─────────────────────────────────────────────


def test_scan_result_defaults() -> None:
    result = ScanResult()
    assert result.passed is True
    assert result.severity_counts == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert result.vulnerabilities == []


def test_scan_result_with_vulns() -> None:
    vuln = Vulnerability(
        file="app.py",
        line=10,
        rule="S101",
        severity="critical",
        description="Test issue",
    )
    result = ScanResult(vulnerabilities=[vuln])
    assert len(result.vulnerabilities) == 1


def test_scan_result_preserves_provided_severity_counts() -> None:
    counts = {"critical": 5, "high": 3, "medium": 1, "low": 0}
    result = ScanResult(severity_counts=counts)
    assert result.severity_counts == counts


def test_vulnerability_defaults() -> None:
    vuln = Vulnerability(
        file="x.py", line=1, rule="R1", severity="low", description="desc"
    )
    assert vuln.fix_suggestion == ""


# ── _run_subprocess ──────────────────────────────────────────────────


async def test_run_subprocess_success() -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"hello stdout", b"hello stderr")
    mock_proc.returncode = 0

    with patch("app.ci.security_scanner.asyncio.create_subprocess_exec", return_value=mock_proc):
        code, stdout, stderr = await _run_subprocess(["echo", "hi"])

    assert code == 0
    assert stdout == "hello stdout"
    assert stderr == "hello stderr"


async def test_run_subprocess_nonzero_returncode() -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"out", b"err")
    mock_proc.returncode = 1

    with patch("app.ci.security_scanner.asyncio.create_subprocess_exec", return_value=mock_proc):
        code, stdout, stderr = await _run_subprocess(["false"])

    assert code == 1
    assert stdout == "out"


async def test_run_subprocess_none_returncode_treated_as_zero() -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = None

    with patch("app.ci.security_scanner.asyncio.create_subprocess_exec", return_value=mock_proc):
        code, _, _ = await _run_subprocess(["cmd"])

    assert code == 0


async def test_run_subprocess_timeout() -> None:
    mock_proc = AsyncMock()
    # After kill, the second communicate() returns empty bytes
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.kill = MagicMock()

    async def fake_wait_for(coro, *, timeout):  # noqa: ARG001, ANN001, ANN202
        # Consume the coroutine to avoid warnings
        coro.close()
        raise TimeoutError

    with patch("app.ci.security_scanner.asyncio.wait_for", side_effect=fake_wait_for), \
         patch("app.ci.security_scanner.asyncio.create_subprocess_exec", return_value=mock_proc):
        code, stdout, stderr = await _run_subprocess(["slow"], timeout=0.1)

    assert code == -1
    assert "timed out" in stderr
    mock_proc.kill.assert_called_once()


async def test_run_subprocess_with_cwd() -> None:
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"ok", b"")
    mock_proc.returncode = 0

    with patch(
        "app.ci.security_scanner.asyncio.create_subprocess_exec", return_value=mock_proc
    ) as mock_exec:
        await _run_subprocess(["ls"], cwd="/some/dir")

    mock_exec.assert_called_once_with(
        "ls",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd="/some/dir",
    )


# ── _run_semgrep ─────────────────────────────────────────────────────


async def test_run_semgrep_parses_results() -> None:
    semgrep_output = json.dumps(
        {
            "results": [
                {
                    "path": "app.py",
                    "start": {"line": 42},
                    "check_id": "python.lang.security.eval",
                    "extra": {
                        "severity": "ERROR",
                        "message": "eval detected",
                        "fix": "use ast.literal_eval",
                    },
                }
            ]
        }
    )
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, semgrep_output, ""),
    ):
        vulns = await _run_semgrep(Path(_TEST_PROJECT))

    assert len(vulns) == 1
    assert vulns[0].file == "app.py"
    assert vulns[0].line == 42
    assert vulns[0].severity == "critical"
    assert vulns[0].fix_suggestion == "use ast.literal_eval"


async def test_run_semgrep_empty_results() -> None:
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, json.dumps({"results": []}), ""),
    ):
        vulns = await _run_semgrep(Path(_TEST_PROJECT))

    assert vulns == []


async def test_run_semgrep_invalid_json() -> None:
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(1, "not json", "error"),
    ):
        vulns = await _run_semgrep(Path(_TEST_PROJECT))

    assert vulns == []


async def test_run_semgrep_missing_fields_uses_defaults() -> None:
    output = json.dumps({"results": [{"extra": {}}]})
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, output, ""),
    ):
        vulns = await _run_semgrep(Path(_TEST_PROJECT))

    assert len(vulns) == 1
    assert vulns[0].file == "unknown"
    assert vulns[0].line == 0
    assert vulns[0].rule == "unknown"
    assert vulns[0].severity == "low"


# ── _run_bandit ──────────────────────────────────────────────────────


async def test_run_bandit_parses_results() -> None:
    bandit_output = json.dumps(
        {
            "results": [
                {
                    "filename": "secret.py",
                    "line_number": 7,
                    "test_id": "B105",
                    "issue_severity": "HIGH",
                    "issue_text": "Possible hardcoded credential",
                    "more_info": "https://bandit.readthedocs.io/...",
                }
            ]
        }
    )
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(1, bandit_output, ""),
    ):
        vulns = await _run_bandit(Path(_TEST_PROJECT))

    assert len(vulns) == 1
    assert vulns[0].file == "secret.py"
    assert vulns[0].line == 7
    assert vulns[0].severity == "high"
    assert vulns[0].rule == "B105"


async def test_run_bandit_empty_results() -> None:
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, json.dumps({"results": []}), ""),
    ):
        vulns = await _run_bandit(Path(_TEST_PROJECT))

    assert vulns == []


async def test_run_bandit_invalid_json() -> None:
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(1, "{{bad", ""),
    ):
        vulns = await _run_bandit(Path(_TEST_PROJECT))

    assert vulns == []


# ── _audit_python_deps ───────────────────────────────────────────────


async def test_audit_python_deps_with_requirements(tmp_path: Path) -> None:
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("flask==2.0.0\n")

    audit_output = json.dumps(
        {
            "dependencies": [
                {
                    "name": "flask",
                    "version": "2.0.0",
                    "vulns": [
                        {
                            "id": "CVE-2023-1234",
                            "severity": "HIGH",
                            "description": "XSS vulnerability",
                            "fix_versions": ["2.3.0"],
                        }
                    ],
                }
            ]
        }
    )
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, audit_output, ""),
    ) as mock_sub:
        vulns = await _audit_python_deps(tmp_path)

    assert len(vulns) == 1
    assert vulns[0].rule == "CVE-2023-1234"
    assert vulns[0].severity == "high"
    assert "flask==2.0.0" in vulns[0].description
    # Verify --requirement flag was included
    cmd_arg = mock_sub.call_args[0][0]
    assert "--requirement" in cmd_arg


async def test_audit_python_deps_no_requirements(tmp_path: Path) -> None:
    audit_output = json.dumps({"dependencies": []})
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, audit_output, ""),
    ) as mock_sub:
        vulns = await _audit_python_deps(tmp_path)

    assert vulns == []
    cmd_arg = mock_sub.call_args[0][0]
    assert "--requirement" not in cmd_arg


async def test_audit_python_deps_invalid_json() -> None:
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(1, "error output", ""),
    ):
        vulns = await _audit_python_deps(Path(_TEST_PROJECT))

    assert vulns == []


async def test_audit_python_deps_multiple_vulns_per_dep(tmp_path: Path) -> None:
    audit_output = json.dumps(
        {
            "dependencies": [
                {
                    "name": "requests",
                    "version": "2.20.0",
                    "vulns": [
                        {"id": "CVE-A", "severity": "CRITICAL", "description": "a"},
                        {"id": "CVE-B", "severity": "MEDIUM", "description": "b"},
                    ],
                }
            ]
        }
    )
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, audit_output, ""),
    ):
        vulns = await _audit_python_deps(tmp_path)

    assert len(vulns) == 2
    assert vulns[0].severity == "critical"
    assert vulns[1].severity == "medium"


# ── _audit_npm_deps ──────────────────────────────────────────────────


async def test_audit_npm_deps_v2_format() -> None:
    npm_output = json.dumps(
        {
            "vulnerabilities": {
                "lodash": {
                    "severity": "high",
                    "via": [{"title": "Prototype Pollution"}],
                    "fixAvailable": {"name": "lodash", "version": "4.17.21"},
                }
            }
        }
    )
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, npm_output, ""),
    ):
        vulns = await _audit_npm_deps(Path(_TEST_PROJECT))

    assert len(vulns) == 1
    assert vulns[0].severity == "high"
    assert vulns[0].rule == "npm-audit-lodash"
    assert "Prototype Pollution" in vulns[0].description
    assert vulns[0].fix_suggestion == "lodash"


async def test_audit_npm_deps_v2_via_string() -> None:
    """When 'via' contains strings instead of dicts, description should be empty."""
    npm_output = json.dumps(
        {
            "vulnerabilities": {
                "foo": {
                    "severity": "low",
                    "via": ["bar"],
                    "fixAvailable": {},
                }
            }
        }
    )
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, npm_output, ""),
    ):
        vulns = await _audit_npm_deps(Path(_TEST_PROJECT))

    assert len(vulns) == 1
    assert vulns[0].description == "foo: "
    assert vulns[0].fix_suggestion == "Update dependency"


async def test_audit_npm_deps_v2_empty_via() -> None:
    npm_output = json.dumps(
        {
            "vulnerabilities": {
                "pkg": {
                    "severity": "medium",
                    "via": [],
                }
            }
        }
    )
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, npm_output, ""),
    ):
        vulns = await _audit_npm_deps(Path(_TEST_PROJECT))

    assert len(vulns) == 1
    assert vulns[0].description == "pkg: "


async def test_audit_npm_deps_v1_format() -> None:
    npm_output = json.dumps(
        {
            "advisories": {
                "123": {
                    "severity": "moderate",
                    "module_name": "express",
                    "title": "Open redirect",
                    "cves": ["CVE-2024-9999"],
                    "recommendation": "Upgrade to >=4.18.0",
                }
            }
        }
    )
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, npm_output, ""),
    ):
        vulns = await _audit_npm_deps(Path(_TEST_PROJECT))

    assert len(vulns) == 1
    assert vulns[0].severity == "medium"
    assert vulns[0].rule == "npm-CVE-2024-9999"
    assert "express" in vulns[0].description


async def test_audit_npm_deps_v1_no_cves() -> None:
    npm_output = json.dumps(
        {
            "advisories": {
                "456": {
                    "severity": "low",
                    "module_name": "qs",
                    "title": "Denial of service",
                    "cves": [],
                    "recommendation": "Upgrade",
                }
            }
        }
    )
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(0, npm_output, ""),
    ):
        vulns = await _audit_npm_deps(Path(_TEST_PROJECT))

    assert len(vulns) == 1
    assert vulns[0].rule == "npm-unknown"


async def test_audit_npm_deps_invalid_json() -> None:
    with patch(
        "app.ci.security_scanner._run_subprocess",
        new_callable=AsyncMock,
        return_value=(1, "not-json", ""),
    ):
        vulns = await _audit_npm_deps(Path(_TEST_PROJECT))

    assert vulns == []


# ── run_sast (integration-level with mocked helpers) ─────────────────


@patch("app.ci.security_scanner._run_bandit", new_callable=AsyncMock)
@patch("app.ci.security_scanner._run_semgrep", new_callable=AsyncMock)
async def test_run_sast_python_no_findings(mock_semgrep: AsyncMock, mock_bandit: AsyncMock) -> None:
    mock_semgrep.return_value = []
    mock_bandit.return_value = []

    result = await run_sast(_TEST_PROJECT, language="python")
    assert result.passed is True
    assert result.severity_counts["critical"] == 0
    assert result.tool_name == "semgrep+bandit"
    mock_semgrep.assert_called_once()
    mock_bandit.assert_called_once()


@patch("app.ci.security_scanner._run_semgrep", new_callable=AsyncMock)
async def test_run_sast_javascript(mock_semgrep: AsyncMock) -> None:
    mock_semgrep.return_value = []
    result = await run_sast(_TEST_PROJECT, language="javascript")
    assert result.tool_name == "semgrep"
    mock_semgrep.assert_called_once()


@patch("app.ci.security_scanner._run_bandit", new_callable=AsyncMock)
@patch("app.ci.security_scanner._run_semgrep", new_callable=AsyncMock)
async def test_run_sast_with_critical_findings(
    mock_semgrep: AsyncMock, mock_bandit: AsyncMock
) -> None:
    mock_semgrep.return_value = [
        Vulnerability(
            file="app.py",
            line=5,
            rule="python.lang.security.audit.eval-detected",
            severity="critical",
            description="Use of eval() detected",
        )
    ]
    mock_bandit.return_value = []

    result = await run_sast(_TEST_PROJECT, language="python")
    assert result.passed is False
    assert result.severity_counts["critical"] == 1


@patch("app.ci.security_scanner._run_bandit", new_callable=AsyncMock)
@patch("app.ci.security_scanner._run_semgrep", new_callable=AsyncMock)
async def test_run_sast_mixed_severities(
    mock_semgrep: AsyncMock, mock_bandit: AsyncMock
) -> None:
    mock_semgrep.return_value = [
        Vulnerability(file="a.py", line=1, rule="R1", severity="high", description="h"),
        Vulnerability(file="b.py", line=2, rule="R2", severity="low", description="l"),
    ]
    mock_bandit.return_value = [
        Vulnerability(file="c.py", line=3, rule="R3", severity="medium", description="m"),
    ]

    result = await run_sast(_TEST_PROJECT, language="python")
    assert result.passed is True  # no critical findings
    assert result.severity_counts["high"] == 1
    assert result.severity_counts["medium"] == 1
    assert result.severity_counts["low"] == 1
    assert len(result.vulnerabilities) == 3
    assert result.duration_ms >= 0


@patch("app.ci.security_scanner._run_semgrep", new_callable=AsyncMock)
async def test_run_sast_typescript(mock_semgrep: AsyncMock) -> None:
    mock_semgrep.return_value = []
    result = await run_sast(_TEST_PROJECT, language="typescript")
    assert result.tool_name == "semgrep"
    mock_semgrep.assert_called_once()


# ── run_dependency_audit ──────────────────────────────────────────────


@patch("app.ci.security_scanner._audit_python_deps", new_callable=AsyncMock)
async def test_dependency_audit_python(mock_audit: AsyncMock) -> None:
    mock_audit.return_value = []
    result = await run_dependency_audit(_TEST_PROJECT, language="python")
    assert result == []
    mock_audit.assert_called_once()


@patch("app.ci.security_scanner._audit_npm_deps", new_callable=AsyncMock)
async def test_dependency_audit_javascript(mock_audit: AsyncMock) -> None:
    mock_audit.return_value = [
        Vulnerability(
            file="package.json", line=0, rule="CVE-2024-1234", severity="high", description="Test"
        )
    ]
    result = await run_dependency_audit(_TEST_PROJECT, language="javascript")
    assert len(result) == 1
    mock_audit.assert_called_once()


@patch("app.ci.security_scanner._audit_npm_deps", new_callable=AsyncMock)
async def test_dependency_audit_typescript(mock_audit: AsyncMock) -> None:
    mock_audit.return_value = []
    result = await run_dependency_audit(_TEST_PROJECT, language="typescript")
    assert result == []
    mock_audit.assert_called_once()


async def test_dependency_audit_unknown_language() -> None:
    result = await run_dependency_audit(_TEST_PROJECT, language="rust")
    assert result == []
