"""Security Agent — AI-powered security analysis with SAST integration."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.router import execute_with_fallback, route_task

logger = logging.getLogger(__name__)

# ── Prompt templates ─────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior application security engineer performing a thorough security
review of code changes.

Your output MUST be valid JSON with exactly these keys:
  - "vulnerabilities": an array of vulnerability objects.
  - "recommendations": an array of general security recommendation strings.

Each vulnerability object MUST have:
  - "id": a short identifier (e.g. "VULN-001").
  - "title": concise title.
  - "severity": one of "critical", "high", "medium", "low", "info".
  - "file_path": the affected file.
  - "line_range": [start_line, end_line] or null if unknown.
  - "description": detailed explanation of the vulnerability.
  - "cwe_id": CWE identifier if applicable (e.g. "CWE-89"), or null.
  - "remediation": how to fix it.

Respond ONLY with the JSON object.\
"""

_USER_PROMPT_TEMPLATE = """\
## Code Diff
```
{diff}
```

## File Contents (for context)
{file_contents}

---

Perform a comprehensive security review.  Look for:
- Injection vulnerabilities (SQL, command, XSS, SSTI)
- Authentication and authorization flaws
- Sensitive data exposure (API keys, credentials, PII)
- Insecure deserialization
- Path traversal and file inclusion
- Cryptographic weaknesses
- Race conditions and TOCTOU
- Dependency vulnerabilities
- Logging of sensitive data\
"""


@dataclass
class Vulnerability:
    """A single identified vulnerability."""

    id: str
    title: str
    severity: str  # "critical" | "high" | "medium" | "low" | "info"
    file_path: str
    line_range: list[int] | None = None
    description: str = ""
    cwe_id: str | None = None
    remediation: str = ""


@dataclass
class SecurityReport:
    """Aggregated security analysis report."""

    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    severity_counts: dict[str, int] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    sast_findings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return self.severity_counts.get("critical", 0) > 0

    @property
    def total_findings(self) -> int:
        return len(self.vulnerabilities) + len(self.sast_findings)


def _parse_security_output(raw: str) -> tuple[list[Vulnerability], list[str]]:
    """Parse JSON output into vulnerabilities and recommendations."""
    content = raw.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Security agent returned invalid JSON: {exc}") from exc

    vulns: list[Vulnerability] = []
    for v in data.get("vulnerabilities", []):
        vulns.append(
            Vulnerability(
                id=v.get("id", "UNKNOWN"),
                title=v.get("title", ""),
                severity=v.get("severity", "info"),
                file_path=v.get("file_path", ""),
                line_range=v.get("line_range"),
                description=v.get("description", ""),
                cwe_id=v.get("cwe_id"),
                remediation=v.get("remediation", ""),
            )
        )

    recommendations = data.get("recommendations", [])
    return vulns, recommendations


async def _run_semgrep(repo_path: Path, changed_files: list[str]) -> list[dict[str, Any]]:
    """Run semgrep SAST scanner on the changed files.

    Returns a list of finding dicts, or an empty list if semgrep is not
    installed or fails.
    """
    if not changed_files:
        return []

    target_files = [str(repo_path / f) for f in changed_files if (repo_path / f).exists()]
    if not target_files:
        return []

    cmd = [
        "semgrep",
        "scan",
        "--json",
        "--config",
        "auto",
        "--severity",
        "WARNING",
        *target_files,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        output = (stdout or b"").decode("utf-8", errors="replace")

        if not output.strip():
            return []

        result = json.loads(output)
        findings: list[dict[str, Any]] = []
        for finding in result.get("results", []):
            findings.append(
                {
                    "rule_id": finding.get("check_id", ""),
                    "message": finding.get("extra", {}).get("message", ""),
                    "severity": finding.get("extra", {}).get("severity", "WARNING"),
                    "file_path": finding.get("path", ""),
                    "start_line": finding.get("start", {}).get("line"),
                    "end_line": finding.get("end", {}).get("line"),
                }
            )
        return findings

    except FileNotFoundError:
        logger.info("semgrep not installed — skipping SAST scan")
        return []
    except TimeoutError:
        logger.warning("semgrep timed out after 120s")
        return []
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("semgrep produced unparsable output: %s", exc)
        return []


async def analyze_security(
    diff: str,
    file_contents: dict[str, str],
    *,
    repo_path: Path | None = None,
    changed_files: list[str] | None = None,
    **kwargs: Any,
) -> SecurityReport:
    """Run a comprehensive security analysis on code changes.

    Combines AI-powered review (Claude preferred for security depth) with
    semgrep SAST if available.

    Parameters
    ----------
    diff:
        Unified diff of the changes.
    file_contents:
        Mapping of ``{file_path: full_content}`` for additional context.
    repo_path:
        Repository root for running semgrep.
    changed_files:
        List of changed file paths (relative) for semgrep.
    **kwargs:
        Forwarded to ``execute_with_fallback`` (e.g. ``db``, ``ticket_id``).
    """
    # Format file contents for the prompt (truncate to avoid token overflow)
    contents_section_parts: list[str] = []
    total_chars = 0
    max_total_chars = 20_000
    for path, content in file_contents.items():
        if total_chars >= max_total_chars:
            remaining = len(file_contents) - len(contents_section_parts)
            contents_section_parts.append(f"... ({remaining} more files truncated)")
            break
        snippet = content[:3_000]
        contents_section_parts.append(f"### {path}\n```\n{snippet}\n```")
        total_chars += len(snippet)
    contents_section = (
        "\n\n".join(contents_section_parts)
        if contents_section_parts
        else "(no file contents provided)"
    )

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        diff=diff[:12_000],
        file_contents=contents_section,
    )

    # Run AI review and SAST in parallel
    ai_task = _ai_review(user_prompt, **kwargs)

    if repo_path and changed_files:
        ai_result, sast_findings = await asyncio.gather(
            ai_task,
            _run_semgrep(repo_path, changed_files),
        )
    else:
        ai_result = await ai_task
        sast_findings = []

    vulns, recommendations = ai_result

    # Compute severity counts
    severity_counts: dict[str, int] = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }
    for v in vulns:
        sev = v.severity.lower()
        if sev in severity_counts:
            severity_counts[sev] += 1

    # Add SAST severity counts
    for finding in sast_findings:
        sev = finding.get("severity", "info").lower()
        mapped_sev = {"error": "high", "warning": "medium"}.get(sev, "info")
        severity_counts[mapped_sev] = severity_counts.get(mapped_sev, 0) + 1

    report = SecurityReport(
        vulnerabilities=vulns,
        severity_counts=severity_counts,
        recommendations=recommendations,
        sast_findings=sast_findings,
    )

    logger.info(
        "Security analysis complete: %d AI findings, %d SAST findings, severity=%s",
        len(vulns),
        len(sast_findings),
        severity_counts,
    )
    return report


async def _ai_review(
    user_prompt: str,
    **kwargs: Any,
) -> tuple[list[Vulnerability], list[str]]:
    """Run the AI security review portion."""
    agent = route_task("security_review")
    response = await execute_with_fallback(
        agent,
        prompt=user_prompt,
        context="",
        system_prompt=_SYSTEM_PROMPT,
        temperature=0.1,
        max_tokens=8192,
        action_type="security_review",
        **kwargs,
    )
    return _parse_security_output(response.content)
