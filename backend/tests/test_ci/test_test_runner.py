"""Tests for the CI test runner module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.ci.test_runner import (
    TestSuiteResult,
    _extract_pytest_metrics,
    _parse_pytest_json,
    run_tests,
)

_TEST_PROJECT = "/var/test/project"  # noqa: S105


# ── TestSuiteResult dataclass ─────────────────────────────────────────


def test_passed_count() -> None:
    result = TestSuiteResult(passed=True, total=10, failed=2, skipped=1)
    assert result.passed_count == 7


def test_passed_count_all_pass() -> None:
    result = TestSuiteResult(passed=True, total=5, failed=0, skipped=0)
    assert result.passed_count == 5


# ── _parse_pytest_json ────────────────────────────────────────────────


def test_parse_pytest_json_nonexistent(tmp_path: Path) -> None:
    result = _parse_pytest_json(tmp_path / "nonexistent.json")
    assert result == {}


def test_parse_pytest_json_valid(tmp_path: Path) -> None:
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps({"summary": {"total": 10, "failed": 1}}))
    result = _parse_pytest_json(report_file)
    assert result["summary"]["total"] == 10


def test_parse_pytest_json_invalid(tmp_path: Path) -> None:
    report_file = tmp_path / "report.json"
    report_file.write_text("not json")
    result = _parse_pytest_json(report_file)
    assert result == {}


# ── _extract_pytest_metrics ───────────────────────────────────────────


def test_extract_metrics_empty_report() -> None:
    total, failed, skipped, coverage = _extract_pytest_metrics({})
    assert total == 0
    assert failed == 0
    assert skipped == 0
    assert coverage is None


def test_extract_metrics_with_summary() -> None:
    report = {
        "summary": {"total": 20, "failed": 3, "deselected": 2, "xfailed": 1},
    }
    total, failed, skipped, coverage = _extract_pytest_metrics(report)
    assert total == 20
    assert failed == 3
    assert skipped == 3


def test_extract_metrics_with_coverage() -> None:
    report = {
        "summary": {"total": 10, "failed": 0},
        "coverage": {"totals": {"percent_covered": 85.5}},
    }
    _, _, _, coverage = _extract_pytest_metrics(report)
    assert coverage == 85.5


# ── run_tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.ci.test_runner._run_subprocess", new_callable=AsyncMock)
async def test_run_tests_unit(mock_subprocess: AsyncMock) -> None:
    mock_subprocess.return_value = (0, "10 passed in 5.0s", "")
    result = await run_tests(_TEST_PROJECT, "unit")
    assert result.tool_name == "pytest"
    assert result.passed is True


@pytest.mark.asyncio
@patch("app.ci.test_runner._run_subprocess", new_callable=AsyncMock)
async def test_run_tests_integration(mock_subprocess: AsyncMock) -> None:
    mock_subprocess.return_value = (0, "5 passed in 10.0s", "")
    result = await run_tests(_TEST_PROJECT, "integration")
    assert result.tool_name == "pytest"


@pytest.mark.asyncio
@patch("app.ci.test_runner._run_subprocess", new_callable=AsyncMock)
async def test_run_tests_e2e(mock_subprocess: AsyncMock) -> None:
    mock_subprocess.return_value = (0, '{"stats":{"expected":3,"unexpected":0,"skipped":1}}', "")
    result = await run_tests(_TEST_PROJECT, "e2e")
    assert result.tool_name == "playwright"
    assert result.total == 4
    assert result.skipped == 1


@pytest.mark.asyncio
@patch("app.ci.test_runner._run_subprocess", new_callable=AsyncMock)
async def test_run_tests_security(mock_subprocess: AsyncMock) -> None:
    mock_subprocess.return_value = (0, '{"results":[]}', "")
    result = await run_tests(_TEST_PROJECT, "security")
    assert result.tool_name == "semgrep"
    assert result.passed is True


@pytest.mark.asyncio
async def test_run_tests_unknown_type() -> None:
    result = await run_tests(_TEST_PROJECT, "unknown_type")
    assert result.passed is False
    assert result.tool_name == "unknown"
    assert "Unknown test type" in result.log_output


@pytest.mark.asyncio
@patch("app.ci.test_runner._run_subprocess", new_callable=AsyncMock)
async def test_run_tests_with_failures(mock_subprocess: AsyncMock) -> None:
    mock_subprocess.return_value = (1, "8 passed, 2 failed in 5.0s", "")
    result = await run_tests(_TEST_PROJECT, "unit")
    assert result.passed is False
    assert result.failed == 2


@pytest.mark.asyncio
@patch("app.ci.test_runner._run_subprocess", new_callable=AsyncMock)
async def test_run_tests_e2e_json_parse_error(mock_subprocess: AsyncMock) -> None:
    """When Playwright output is not valid JSON, falls back to text parsing."""
    mock_subprocess.return_value = (0, "3 passed, 1 failed", "")
    result = await run_tests(_TEST_PROJECT, "e2e")
    assert result.tool_name == "playwright"
    assert result.total == 4
    assert result.failed == 1
