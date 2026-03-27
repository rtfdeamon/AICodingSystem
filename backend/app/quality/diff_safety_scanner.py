"""Diff Safety Scanner — scans AI-generated code diffs for dangerous patterns.

Analyses unified diffs and raw file content for dangerous operations,
security anti-patterns, hardcoded secrets, dependency tampering,
privilege escalation, and data exfiltration before code is merged.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class DiffRiskType(StrEnum):
    DANGEROUS_OPERATION = "dangerous_operation"
    SECURITY_ANTIPATTERN = "security_antipattern"
    HARDCODED_SECRET = "hardcoded_secret"
    DEPENDENCY_TAMPERING = "dependency_tampering"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXFILTRATION = "data_exfiltration"


@dataclass
class DiffFinding:
    """A single finding from scanning a diff or file."""

    risk_type: DiffRiskType
    pattern_matched: str
    file_path: str
    line_number: int | None = None
    code_snippet: str = ""
    severity: float = 0.5
    recommendation: str = ""


@dataclass
class DiffScanResult:
    """Result of scanning a diff or file for dangerous patterns."""

    findings: list[DiffFinding] = field(default_factory=list)
    risk_score: float = 0.0
    is_safe: bool = True
    files_scanned: int = 0
    lines_scanned: int = 0


# ── Risk weights per type ──────────────────────────────────────────

_RISK_WEIGHTS: dict[DiffRiskType, float] = {
    DiffRiskType.DANGEROUS_OPERATION: 25.0,
    DiffRiskType.SECURITY_ANTIPATTERN: 30.0,
    DiffRiskType.HARDCODED_SECRET: 35.0,
    DiffRiskType.DEPENDENCY_TAMPERING: 20.0,
    DiffRiskType.PRIVILEGE_ESCALATION: 30.0,
    DiffRiskType.DATA_EXFILTRATION: 35.0,
}

_SAFE_THRESHOLD = 40.0

# ── Detection patterns ─────────────────────────────────────────────
# Each entry: (compiled regex, label, recommendation)

_DANGEROUS_OPS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\bos\.remove\s*\("),
        "os.remove",
        "Use safe file deletion with error handling",
    ),
    (
        re.compile(r"\bshutil\.rmtree\s*\("),
        "shutil.rmtree",
        "Avoid recursive directory deletion",
    ),
    (
        re.compile(r"\bos\.system\s*\("),
        "os.system",
        "Use subprocess.run with explicit args",
    ),
    (
        re.compile(r"\bsubprocess\.call\s*\("),
        "subprocess.call",
        "Use subprocess.run for better control",
    ),
    (
        re.compile(r"\bos\.chmod\s*\("),
        "os.chmod",
        "Review permission changes carefully",
    ),
    (
        re.compile(r"\bos\.chown\s*\("),
        "os.chown",
        "Review ownership changes carefully",
    ),
]

_SECURITY_ANTIPATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\beval\s*\("),
        "eval(",
        "Never use eval on untrusted input",
    ),
    (
        re.compile(r"\bexec\s*\("),
        "exec(",
        "Avoid exec(); use safer alternatives",
    ),
    (
        re.compile(r"\b__import__\s*\("),
        "__import__(",
        "Use importlib.import_module instead",
    ),
    (
        re.compile(r"\bpickle\.loads?\s*\("),
        "pickle.loads",
        "Pickle is unsafe; use JSON instead",
    ),
    (
        re.compile(r"\byaml\.load\s*\("),
        "yaml.load(",
        "Use yaml.safe_load instead",
    ),
    (
        re.compile(r"\bcompile\s*\(.+['\"]exec['\"]"),
        "compile(…exec)",
        "Avoid compile with exec mode",
    ),
    (
        re.compile(r"\bsubprocess\.\w+\(.*shell\s*=\s*True"),
        "subprocess(shell=True)",
        "Avoid shell=True; pass command as list",
    ),
]

_SECRET_RE_FLAGS = re.IGNORECASE

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(
            r"""(?:password|passwd|pwd)\s*=\s*['"][^'"]+['"]""",
            _SECRET_RE_FLAGS,
        ),
        "password=",
        "Do not hardcode passwords; use env vars",
    ),
    (
        re.compile(
            r"""(?:api_key|apikey)\s*=\s*['"][^'"]+['"]""",
            _SECRET_RE_FLAGS,
        ),
        "api_key=",
        "Do not hardcode API keys; use env vars",
    ),
    (
        re.compile(
            r"""(?:secret|secret_key)\s*=\s*['"][^'"]+['"]""",
            _SECRET_RE_FLAGS,
        ),
        "secret=",
        "Do not hardcode secrets; use a vault",
    ),
    (
        re.compile(
            r"""(?:token|auth_token|access_token)\s*=\s*['"][^'"]+['"]""",
            _SECRET_RE_FLAGS,
        ),
        "token=",
        "Do not hardcode tokens; use env vars",
    ),
    (
        re.compile(
            r"""AWS_SECRET(?:_ACCESS_KEY)?\s*=\s*['"][^'"]+['"]""",
        ),
        "AWS_SECRET",
        "Do not hardcode AWS secrets; use IAM",
    ),
    (
        re.compile(r"""PRIVATE_KEY\s*=\s*['"][^'"]+['"]"""),
        "PRIVATE_KEY",
        "Do not hardcode private keys",
    ),
]

_DEPENDENCY_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"git\+https?://"),
        "git+http(s) dependency",
        "Pin versions from PyPI instead",
    ),
    (
        re.compile(r"https?://.*\.whl"),
        "remote .whl URL",
        "Use PyPI packages instead of URLs",
    ),
    (
        re.compile(
            r"https?://(?!pypi\.org|registry\.npmjs\.org)",
        ),
        "suspicious URL in dependency",
        "Verify URL is from trusted registry",
    ),
]

_PRIVILEGE_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\bsudo\b"),
        "sudo",
        "Avoid sudo in application code",
    ),
    (
        re.compile(r"\bchmod\s+777\b"),
        "chmod 777",
        "Never use chmod 777; use minimal perms",
    ),
    (
        re.compile(r"\bsetuid\b"),
        "setuid",
        "Avoid setuid; use capabilities",
    ),
    (
        re.compile(r"\bSUID\b"),
        "SUID",
        "Avoid SUID bits; use capabilities",
    ),
]

_EXFILTRATION_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\brequests\.post\s*\(.*(?:data|json)\s*="),
        "requests.post with data",
        "Review outbound POST requests",
    ),
    (
        re.compile(r"\burllib\..*\.urlopen\s*\(.*encode"),
        "urllib with encode",
        "Review URL-encoded outbound requests",
    ),
    (
        re.compile(
            r"\bbase64\.b64encode\b.*(?:send|post|request|urlopen)",
        ),
        "base64 encode + send",
        "Review base64-encoded outbound data",
    ),
]

_ALL_PATTERNS: list[
    tuple[DiffRiskType, list[tuple[re.Pattern[str], str, str]]]
] = [
    (DiffRiskType.DANGEROUS_OPERATION, _DANGEROUS_OPS),
    (DiffRiskType.SECURITY_ANTIPATTERN, _SECURITY_ANTIPATTERNS),
    (DiffRiskType.HARDCODED_SECRET, _SECRET_PATTERNS),
    (DiffRiskType.PRIVILEGE_ESCALATION, _PRIVILEGE_PATTERNS),
    (DiffRiskType.DATA_EXFILTRATION, _EXFILTRATION_PATTERNS),
]

# Severity defaults per risk type
_SEVERITY: dict[DiffRiskType, float] = {
    DiffRiskType.DANGEROUS_OPERATION: 0.6,
    DiffRiskType.SECURITY_ANTIPATTERN: 0.8,
    DiffRiskType.HARDCODED_SECRET: 0.9,
    DiffRiskType.DEPENDENCY_TAMPERING: 0.7,
    DiffRiskType.PRIVILEGE_ESCALATION: 0.8,
    DiffRiskType.DATA_EXFILTRATION: 0.9,
}


# ── Diff parsing ───────────────────────────────────────────────────

_DIFF_HUNK_RE = re.compile(
    r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@",
    re.MULTILINE,
)


def _parse_diff(
    diff_text: str,
) -> list[tuple[str, list[tuple[int, str]]]]:
    """Parse a unified diff into (file, [(line_no, added_line)]).

    Only added lines (``+``, excluding ``+++``) are returned.
    """
    files: list[tuple[str, list[tuple[int, str]]]] = []
    current_file: str = ""
    current_lines: list[tuple[int, str]] = []
    line_counter = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ b/") or line.startswith("+++ a/"):
            if current_file and current_lines:
                files.append((current_file, current_lines))
            current_file = line[6:]
            current_lines = []
            continue

        if line.startswith("--- "):
            continue

        hunk_match = _DIFF_HUNK_RE.match(line)
        if hunk_match:
            line_counter = int(hunk_match.group(1))
            continue

        if line.startswith("+"):
            current_lines.append((line_counter, line[1:]))
            line_counter += 1
        elif line.startswith("-"):
            pass
        else:
            line_counter += 1

    if current_file and current_lines:
        files.append((current_file, current_lines))

    return files


# ── Scanner class ──────────────────────────────────────────────────


class DiffSafetyScanner:
    """Scans diffs and file content for dangerous patterns."""

    def __init__(self) -> None:
        self._safe_patterns: list[re.Pattern[str]] = []
        self._scan_history: list[DiffScanResult] = []

    def scan_diff(self, diff_text: str) -> DiffScanResult:
        """Scan a unified diff for dangerous patterns."""
        parsed = _parse_diff(diff_text)
        findings: list[DiffFinding] = []
        files_scanned = len(parsed)
        lines_scanned = 0

        for file_path, added_lines in parsed:
            lines_scanned += len(added_lines)
            if _is_dependency_file(file_path):
                findings.extend(
                    self._check_dependency_lines(
                        file_path, added_lines,
                    )
                )
            findings.extend(
                self._check_lines(file_path, added_lines)
            )

        risk_score = self._compute_risk_score(findings)
        result = DiffScanResult(
            findings=findings,
            risk_score=risk_score,
            is_safe=risk_score < _SAFE_THRESHOLD,
            files_scanned=files_scanned,
            lines_scanned=lines_scanned,
        )

        self._scan_history.append(result)
        if findings:
            logger.warning(
                "Diff scan: %d findings, score=%.1f, safe=%s",
                len(findings),
                risk_score,
                result.is_safe,
            )
        return result

    def scan_file_content(
        self, content: str, file_path: str,
    ) -> DiffScanResult:
        """Scan raw file content for dangerous patterns."""
        lines = content.splitlines()
        numbered = [
            (i + 1, line) for i, line in enumerate(lines)
        ]
        findings: list[DiffFinding] = []

        if _is_dependency_file(file_path):
            findings.extend(
                self._check_dependency_lines(
                    file_path, numbered,
                )
            )

        findings.extend(self._check_lines(file_path, numbered))

        risk_score = self._compute_risk_score(findings)
        result = DiffScanResult(
            findings=findings,
            risk_score=risk_score,
            is_safe=risk_score < _SAFE_THRESHOLD,
            files_scanned=1,
            lines_scanned=len(lines),
        )

        self._scan_history.append(result)
        if findings:
            logger.warning(
                "File scan (%s): %d findings, score=%.1f",
                file_path,
                len(findings),
                risk_score,
            )
        return result

    def add_safe_pattern(self, pattern: str) -> None:
        """Add a regex to the allowlist."""
        self._safe_patterns.append(re.compile(pattern))

    def get_stats(self) -> dict:
        """Return aggregate scan statistics."""
        if not self._scan_history:
            return {
                "total_scans": 0,
                "safe_scans": 0,
                "unsafe_scans": 0,
                "average_risk_score": 0.0,
                "total_findings": 0,
                "findings_by_type": {},
            }

        total = len(self._scan_history)
        safe = sum(
            1 for r in self._scan_history if r.is_safe
        )
        all_findings = [
            f for r in self._scan_history for f in r.findings
        ]
        by_type: dict[str, int] = {}
        for f in all_findings:
            key = f.risk_type.value
            by_type[key] = by_type.get(key, 0) + 1

        avg = sum(
            r.risk_score for r in self._scan_history
        ) / total
        return {
            "total_scans": total,
            "safe_scans": safe,
            "unsafe_scans": total - safe,
            "average_risk_score": avg,
            "total_findings": len(all_findings),
            "findings_by_type": by_type,
        }

    def clear_history(self) -> None:
        """Clear scan history."""
        self._scan_history.clear()

    # ── Internal helpers ─────────────────────────────────────────

    def _is_safe_listed(self, line: str) -> bool:
        return any(p.search(line) for p in self._safe_patterns)

    def _check_lines(
        self,
        file_path: str,
        lines: list[tuple[int, str]],
    ) -> list[DiffFinding]:
        findings: list[DiffFinding] = []
        for line_no, line_text in lines:
            if self._is_safe_listed(line_text):
                continue
            for risk_type, patterns in _ALL_PATTERNS:
                for regex, label, rec in patterns:
                    if regex.search(line_text):
                        findings.append(
                            DiffFinding(
                                risk_type=risk_type,
                                pattern_matched=label,
                                file_path=file_path,
                                line_number=line_no,
                                code_snippet=line_text.strip(),
                                severity=_SEVERITY.get(
                                    risk_type, 0.5,
                                ),
                                recommendation=rec,
                            )
                        )
        return findings

    def _check_dependency_lines(
        self,
        file_path: str,
        lines: list[tuple[int, str]],
    ) -> list[DiffFinding]:
        findings: list[DiffFinding] = []
        for line_no, line_text in lines:
            if self._is_safe_listed(line_text):
                continue
            for regex, label, rec in _DEPENDENCY_PATTERNS:
                if regex.search(line_text):
                    findings.append(
                        DiffFinding(
                            risk_type=DiffRiskType.DEPENDENCY_TAMPERING,
                            pattern_matched=label,
                            file_path=file_path,
                            line_number=line_no,
                            code_snippet=line_text.strip(),
                            severity=_SEVERITY[
                                DiffRiskType.DEPENDENCY_TAMPERING
                            ],
                            recommendation=rec,
                        )
                    )
        return findings

    @staticmethod
    def _compute_risk_score(
        findings: list[DiffFinding],
    ) -> float:
        if not findings:
            return 0.0
        total = sum(
            _RISK_WEIGHTS.get(f.risk_type, 10.0) * f.severity
            for f in findings
        )
        return min(total, 100.0)


# ── Helpers ────────────────────────────────────────────────────────

_DEPENDENCY_FILES = {
    "requirements.txt",
    "requirements-dev.txt",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "Pipfile",
    "package.json",
    "package-lock.json",
    "yarn.lock",
}


def _is_dependency_file(file_path: str) -> bool:
    """Check if file path refers to a dependency manifest."""
    basename = (
        file_path.rsplit("/", 1)[-1]
        if "/" in file_path
        else file_path
    )
    return basename in _DEPENDENCY_FILES
