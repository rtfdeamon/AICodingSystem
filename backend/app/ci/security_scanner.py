"""Security scanner — SAST and dependency auditing across languages."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Vulnerability:
    """A single vulnerability finding."""

    file: str
    line: int
    rule: str
    severity: str  # critical | high | medium | low
    description: str
    fix_suggestion: str = ""


@dataclass
class ScanResult:
    """Aggregated result from a security scan."""

    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    severity_counts: dict[str, int] = field(default_factory=dict)
    passed: bool = True  # True when no critical or high severity findings
    tool_name: str = ""
    duration_ms: int = 0

    def __post_init__(self) -> None:
        if not self.severity_counts:
            self.severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}


async def _run_subprocess(
    cmd: list[str],
    cwd: str | None = None,
    timeout: float = 300.0,
) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    logger.info("Running security scan: %s", " ".join(cmd))
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


def _normalize_severity(raw: str) -> str:
    """Normalize severity strings from various tools to our standard set."""
    raw_upper = raw.upper()
    if raw_upper in ("CRITICAL", "ERROR"):
        return "critical"
    elif raw_upper in ("HIGH", "WARNING"):
        return "high"
    elif raw_upper in ("MEDIUM", "MODERATE", "INFO"):
        return "medium"
    else:
        return "low"


async def run_sast(
    project_path: str,
    language: str = "python",
) -> ScanResult:
    """Run static application security testing (SAST) on a project.

    Uses semgrep for all languages, plus bandit for Python.

    Parameters
    ----------
    project_path:
        Absolute path to the project root.
    language:
        Primary language: python, javascript, typescript.

    Returns
    -------
    ScanResult with vulnerabilities and severity counts.
    """
    start = time.perf_counter()
    project = Path(project_path)
    all_vulns: list[Vulnerability] = []

    # Run semgrep (works for all languages)
    semgrep_vulns = await _run_semgrep(project)
    all_vulns.extend(semgrep_vulns)

    # Run language-specific SAST
    if language == "python":
        bandit_vulns = await _run_bandit(project)
        all_vulns.extend(bandit_vulns)

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    # Count severities
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for v in all_vulns:
        severity_counts[v.severity] = severity_counts.get(v.severity, 0) + 1

    passed = severity_counts["critical"] == 0

    return ScanResult(
        vulnerabilities=all_vulns,
        severity_counts=severity_counts,
        passed=passed,
        tool_name="semgrep+bandit" if language == "python" else "semgrep",
        duration_ms=elapsed_ms,
    )


async def _run_semgrep(project: Path) -> list[Vulnerability]:
    """Run semgrep and parse JSON output."""
    cmd = [
        "semgrep",
        "scan",
        "--config=auto",
        "--json",
        "--quiet",
        str(project),
    ]
    returncode, stdout, stderr = await _run_subprocess(cmd, cwd=str(project))

    vulnerabilities: list[Vulnerability] = []
    try:
        data = json.loads(stdout)
        for result in data.get("results", []):
            path = result.get("path", "unknown")
            line = result.get("start", {}).get("line", 0)
            rule_id = result.get("check_id", "unknown")
            extra = result.get("extra", {})
            severity = _normalize_severity(extra.get("severity", "low"))
            message = extra.get("message", result.get("extra", {}).get("message", ""))
            fix = extra.get("fix", "")

            vulnerabilities.append(
                Vulnerability(
                    file=path,
                    line=line,
                    rule=rule_id,
                    severity=severity,
                    description=message,
                    fix_suggestion=fix,
                )
            )
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse semgrep output: %s", exc)

    return vulnerabilities


async def _run_bandit(project: Path) -> list[Vulnerability]:
    """Run bandit (Python SAST) and parse JSON output."""
    cmd = [
        "bandit",
        "-r",
        str(project),
        "-f",
        "json",
        "--quiet",
        "-ll",  # medium severity and above
    ]
    returncode, stdout, stderr = await _run_subprocess(cmd, cwd=str(project))

    vulnerabilities: list[Vulnerability] = []
    try:
        data = json.loads(stdout)
        for result in data.get("results", []):
            severity = _normalize_severity(result.get("issue_severity", "LOW"))
            vulnerabilities.append(
                Vulnerability(
                    file=result.get("filename", "unknown"),
                    line=result.get("line_number", 0),
                    rule=result.get("test_id", "unknown"),
                    severity=severity,
                    description=result.get("issue_text", ""),
                    fix_suggestion=result.get("more_info", ""),
                )
            )
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse bandit output: %s", exc)

    return vulnerabilities


async def run_dependency_audit(
    project_path: str,
    language: str = "python",
) -> list[Vulnerability]:
    """Audit project dependencies for known vulnerabilities.

    Parameters
    ----------
    project_path:
        Absolute path to the project root.
    language:
        Primary language: python, javascript, typescript.

    Returns
    -------
    List of Vulnerability objects for each known CVE.
    """
    project = Path(project_path)
    vulnerabilities: list[Vulnerability] = []

    if language == "python":
        vulnerabilities = await _audit_python_deps(project)
    elif language in ("javascript", "typescript"):
        vulnerabilities = await _audit_npm_deps(project)

    return vulnerabilities


async def _audit_python_deps(project: Path) -> list[Vulnerability]:
    """Run pip-audit for Python dependency vulnerabilities."""
    cmd = [
        "pip-audit",
        "--format=json",
        "--desc",
    ]
    # Check if requirements.txt exists
    req_file = project / "requirements.txt"
    if req_file.exists():
        cmd.extend(["--requirement", str(req_file)])

    returncode, stdout, stderr = await _run_subprocess(cmd, cwd=str(project))

    vulnerabilities: list[Vulnerability] = []
    try:
        data = json.loads(stdout)
        for dep in data.get("dependencies", []):
            for vuln in dep.get("vulns", []):
                severity = _normalize_severity(vuln.get("severity", "medium"))
                vulnerabilities.append(
                    Vulnerability(
                        file="requirements.txt",
                        line=0,
                        rule=vuln.get("id", "CVE-unknown"),
                        severity=severity,
                        description=(
                            f"{dep.get('name')}=={dep.get('version')}: "
                            f"{vuln.get('description', '')}"
                        ),
                        fix_suggestion=(f"Upgrade to {vuln.get('fix_versions', ['latest'])}"),
                    )
                )
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse pip-audit output: %s", exc)

    return vulnerabilities


async def _audit_npm_deps(project: Path) -> list[Vulnerability]:
    """Run npm audit for JavaScript/TypeScript dependency vulnerabilities."""
    cmd = ["npm", "audit", "--json"]
    returncode, stdout, stderr = await _run_subprocess(cmd, cwd=str(project))

    vulnerabilities: list[Vulnerability] = []
    try:
        data = json.loads(stdout)
        advisories = data.get("advisories", {})
        # npm audit v2 format
        if not advisories and "vulnerabilities" in data:
            for name, info in data["vulnerabilities"].items():
                severity = _normalize_severity(info.get("severity", "low"))
                via = info.get("via", [])
                desc = ""
                if via and isinstance(via[0], dict):
                    desc = via[0].get("title", "")
                vulnerabilities.append(
                    Vulnerability(
                        file="package.json",
                        line=0,
                        rule=f"npm-audit-{name}",
                        severity=severity,
                        description=f"{name}: {desc}",
                        fix_suggestion=info.get("fixAvailable", {}).get(
                            "name", "Update dependency"
                        ),
                    )
                )
        else:
            # npm audit v1 format
            for _id, advisory in advisories.items():
                severity = _normalize_severity(advisory.get("severity", "low"))
                vulnerabilities.append(
                    Vulnerability(
                        file="package.json",
                        line=0,
                        rule=(
                            f"npm-{advisory.get('cves', ['unknown'])[0]}"
                            if advisory.get("cves")
                            else "npm-unknown"
                        ),
                        severity=severity,
                        description=f"{advisory.get('module_name')}: {advisory.get('title', '')}",
                        fix_suggestion=advisory.get("recommendation", ""),
                    )
                )
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse npm audit output: %s", exc)

    return vulnerabilities
