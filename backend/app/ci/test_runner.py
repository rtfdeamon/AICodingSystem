"""Test runner — executes various test suites and parses results."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TestSuiteResult:
    """Aggregated result from a test suite run."""

    passed: bool
    total: int = 0
    failed: int = 0
    skipped: int = 0
    coverage_pct: float | None = None
    report_json: dict[str, Any] | None = None
    log_output: str = ""
    duration_ms: int = 0
    tool_name: str = ""

    @property
    def passed_count(self) -> int:
        return self.total - self.failed - self.skipped


async def _run_subprocess(
    cmd: list[str],
    cwd: str | None = None,
    timeout: float = 600.0,
) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    logger.info("Running command: %s (cwd=%s)", " ".join(cmd), cwd)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return -1, "", f"Command timed out after {timeout}s"

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return proc.returncode or 0, stdout, stderr


def _parse_pytest_json(json_path: Path) -> dict[str, Any]:
    """Parse a pytest JSON report file."""
    if not json_path.exists():
        return {}
    try:
        return json.loads(json_path.read_text())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return {}


def _extract_pytest_metrics(report: dict[str, Any]) -> tuple[int, int, int, float | None]:
    """Extract test counts and coverage from pytest JSON report."""
    summary = report.get("summary", {})
    total = summary.get("total", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("deselected", 0) + summary.get("xfailed", 0)

    # Coverage may be in a separate field depending on plugin
    coverage_pct: float | None = None
    report.get("collectors", [])
    if "coverage" in report:
        coverage_pct = report["coverage"].get("totals", {}).get("percent_covered")

    return total, failed, skipped, coverage_pct


async def run_tests(
    project_path: str,
    test_type: str,
    branch: str = "main",
) -> TestSuiteResult:
    """Execute a test suite and return structured results.

    Parameters
    ----------
    project_path:
        Absolute path to the project root.
    test_type:
        One of: unit, integration, e2e, security.
    branch:
        Git branch being tested (informational).

    Returns
    -------
    TestSuiteResult with pass/fail counts, coverage, and raw output.
    """
    start = time.perf_counter()
    project = Path(project_path)

    if test_type in ("unit", "integration"):
        return await _run_pytest(project, test_type, start)
    elif test_type == "e2e":
        return await _run_playwright(project, start)
    elif test_type == "security":
        return await _run_semgrep_tests(project, start)
    else:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return TestSuiteResult(
            passed=False,
            log_output=f"Unknown test type: {test_type}",
            duration_ms=elapsed_ms,
            tool_name="unknown",
        )


async def _run_pytest(project: Path, test_type: str, start: float) -> TestSuiteResult:
    """Run pytest for unit or integration tests."""
    report_path = project / f".pytest_{test_type}_report.json"

    cmd = [
        "python",
        "-m",
        "pytest",
        "--json-report",
        f"--json-report-file={report_path}",
        "--cov=app",
        "--cov-report=json",
        "--tb=short",
        "-q",
    ]
    if test_type == "integration":
        cmd.extend(["-m", "integration"])
    else:
        cmd.extend(["-m", "not integration and not e2e"])

    returncode, stdout, stderr = await _run_subprocess(cmd, cwd=str(project))
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    report = _parse_pytest_json(report_path)
    total, failed, skipped, coverage_pct = _extract_pytest_metrics(report)

    # Try to get coverage from coverage.json
    if coverage_pct is None:
        cov_path = project / "coverage.json"
        if cov_path.exists():
            try:
                cov_data = json.loads(cov_path.read_text())
                coverage_pct = cov_data.get("totals", {}).get("percent_covered")
            except (json.JSONDecodeError, OSError):
                pass

    # If no report parsed, try to extract from stdout
    if total == 0 and stdout:
        for line in stdout.splitlines():
            line_stripped = line.strip()
            if "passed" in line_stripped or "failed" in line_stripped:
                import re

                nums = re.findall(r"(\d+)\s+(passed|failed|skipped|error)", line_stripped)
                for count_str, label in nums:
                    count_val = int(count_str)
                    if label == "passed":
                        total += count_val
                    elif label == "failed":
                        failed += count_val
                        total += count_val
                    elif label == "skipped":
                        skipped += count_val
                        total += count_val

    log_output = stdout[-5000:] if len(stdout) > 5000 else stdout
    if stderr:
        log_output += f"\n--- STDERR ---\n{stderr[-2000:]}"

    return TestSuiteResult(
        passed=(returncode == 0 and failed == 0),
        total=total,
        failed=failed,
        skipped=skipped,
        coverage_pct=coverage_pct,
        report_json=report if report else None,
        log_output=log_output,
        duration_ms=elapsed_ms,
        tool_name="pytest",
    )


async def _run_playwright(project: Path, start: float) -> TestSuiteResult:
    """Run Playwright end-to-end tests."""
    project / "playwright-report" / "results.json"

    cmd = [
        "npx",
        "playwright",
        "test",
        "--reporter=json",
    ]
    returncode, stdout, stderr = await _run_subprocess(cmd, cwd=str(project), timeout=900.0)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    total = 0
    failed = 0
    skipped = 0
    report: dict[str, Any] | None = None

    # Try to parse Playwright JSON output from stdout
    try:
        report = json.loads(stdout)
        stats = report.get("stats", {})
        total = stats.get("expected", 0) + stats.get("unexpected", 0) + stats.get("skipped", 0)
        failed = stats.get("unexpected", 0)
        skipped = stats.get("skipped", 0)
    except (json.JSONDecodeError, ValueError):
        # Fallback: parse text output
        import re

        for line in (stdout + stderr).splitlines():
            match = re.search(r"(\d+)\s+passed", line)
            if match:
                total += int(match.group(1))
            match = re.search(r"(\d+)\s+failed", line)
            if match:
                failed_val = int(match.group(1))
                failed += failed_val
                total += failed_val

    log_output = stdout[-5000:] if len(stdout) > 5000 else stdout
    if stderr:
        log_output += f"\n--- STDERR ---\n{stderr[-2000:]}"

    return TestSuiteResult(
        passed=(returncode == 0 and failed == 0),
        total=total,
        failed=failed,
        skipped=skipped,
        report_json=report,
        log_output=log_output,
        duration_ms=elapsed_ms,
        tool_name="playwright",
    )


async def _run_semgrep_tests(project: Path, start: float) -> TestSuiteResult:
    """Run Semgrep security tests and return as test-like results."""
    cmd = [
        "semgrep",
        "scan",
        "--config=auto",
        "--json",
        str(project),
    ]
    returncode, stdout, stderr = await _run_subprocess(cmd, cwd=str(project))
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    total_findings = 0
    critical_findings = 0
    report: dict[str, Any] | None = None

    try:
        report = json.loads(stdout)
        results = report.get("results", [])
        total_findings = len(results)
        for r in results:
            severity = r.get("extra", {}).get("severity", "").upper()
            if severity in ("ERROR", "CRITICAL"):
                critical_findings += 1
    except (json.JSONDecodeError, ValueError):
        pass

    # For security scans: "passed" means no critical findings
    return TestSuiteResult(
        passed=(critical_findings == 0),
        total=total_findings,
        failed=critical_findings,
        skipped=0,
        report_json=report,
        log_output=stdout[-5000:] if len(stdout) > 5000 else stdout,
        duration_ms=elapsed_ms,
        tool_name="semgrep",
    )
