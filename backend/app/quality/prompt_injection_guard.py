"""Prompt Injection Guard — detects prompt injection attacks in user inputs.

Scans user inputs for common prompt injection patterns before they reach AI
agents: system prompt overrides, role manipulation, instruction injection,
delimiter injection, encoding attacks (base64), and context switching.
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class InjectionType(StrEnum):
    SYSTEM_OVERRIDE = "system_override"
    ROLE_MANIPULATION = "role_manipulation"
    INSTRUCTION_INJECTION = "instruction_injection"
    DELIMITER_INJECTION = "delimiter_injection"
    ENCODING_ATTACK = "encoding_attack"
    CONTEXT_SWITCH = "context_switch"


@dataclass
class InjectionFinding:
    """A single prompt injection detection."""

    injection_type: InjectionType
    matched_pattern: str
    risk_level: float
    start: int
    end: int
    description: str = ""


@dataclass
class InjectionScanResult:
    """Result from scanning text for prompt injection attempts."""

    findings: list[InjectionFinding] = field(default_factory=list)
    risk_score: float = 0.0
    is_safe: bool = True
    input_length: int = 0

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def injection_types_found(self) -> set[str]:
        return {f.injection_type.value for f in self.findings}


# ── Risk weights per injection type ──────────────────────────────────────

_TYPE_WEIGHTS: dict[InjectionType, float] = {
    InjectionType.SYSTEM_OVERRIDE: 30.0,
    InjectionType.ROLE_MANIPULATION: 25.0,
    InjectionType.INSTRUCTION_INJECTION: 20.0,
    InjectionType.DELIMITER_INJECTION: 15.0,
    InjectionType.ENCODING_ATTACK: 25.0,
    InjectionType.CONTEXT_SWITCH: 20.0,
}

_SAFE_THRESHOLD = 40.0

# ── Pattern definitions ──────────────────────────────────────────────────

_INJECTION_PATTERNS: dict[InjectionType, list[tuple[re.Pattern[str], str]]] = {
    InjectionType.SYSTEM_OVERRIDE: [
        (
            re.compile(
                r"ignore\s+(?:all\s+)?previous\s+"
                r"(?:instructions|prompts?|rules)",
                re.IGNORECASE,
            ),
            "Attempt to override previous instructions",
        ),
        (
            re.compile(
                r"disregard\s+(?:all\s+)?(?:above|previous|prior)"
                r"\s+(?:instructions|context|text)",
                re.IGNORECASE,
            ),
            "Attempt to disregard prior context",
        ),
        (
            re.compile(r"new\s+system\s+prompt", re.IGNORECASE),
            "Attempt to inject a new system prompt",
        ),
        (
            re.compile(r"override\s+(?:your\s+)?instructions", re.IGNORECASE),
            "Attempt to override instructions",
        ),
    ],
    InjectionType.ROLE_MANIPULATION: [
        (
            re.compile(r"you\s+are\s+now\s+(?:a|an|the)\b", re.IGNORECASE),
            "Attempt to redefine the AI's role",
        ),
        (
            re.compile(r"act\s+as\s+(?:a|an|the|if)\b", re.IGNORECASE),
            "Attempt to make AI act as a different entity",
        ),
        (
            re.compile(r"pretend\s+(?:to\s+be|you\s+are)\b", re.IGNORECASE),
            "Attempt to make AI pretend to be something else",
        ),
        (
            re.compile(
                r"switch\s+to\s+(?:a\s+)?(?:new\s+)?"
                r"(?:role|persona|mode|character)",
                re.IGNORECASE,
            ),
            "Attempt to switch AI role or persona",
        ),
        (
            re.compile(r"your\s+new\s+role\s+is\b", re.IGNORECASE),
            "Attempt to assign a new role to the AI",
        ),
    ],
    InjectionType.INSTRUCTION_INJECTION: [
        (
            re.compile(r"execute\s+the\s+following\b", re.IGNORECASE),
            "Attempt to inject executable instructions",
        ),
        (
            re.compile(r"run\s+this\s+command\b", re.IGNORECASE),
            "Attempt to inject a command",
        ),
        (
            re.compile(r"perform\s+these\s+steps\b", re.IGNORECASE),
            "Attempt to inject multi-step instructions",
        ),
    ],
    InjectionType.DELIMITER_INJECTION: [
        (
            re.compile(r"```system\b", re.IGNORECASE),
            "Delimiter injection using code block with system tag",
        ),
        (
            re.compile(r"###\s*SYSTEM\s*###", re.IGNORECASE),
            "Delimiter injection using hash-delimited SYSTEM block",
        ),
        (
            re.compile(r"---\s*BEGIN\s+SYSTEM\s*---", re.IGNORECASE),
            "Delimiter injection using dash-delimited SYSTEM block",
        ),
        (
            re.compile(r"\[INST\]", re.IGNORECASE),
            "Delimiter injection using [INST] tag",
        ),
        (
            re.compile(r"</s>"),
            "Delimiter injection using </s> end-of-sequence token",
        ),
    ],
    InjectionType.CONTEXT_SWITCH: [
        (
            re.compile(r"forget\s+everything\b", re.IGNORECASE),
            "Attempt to clear AI context",
        ),
        (
            re.compile(r"reset\s+(?:your\s+)?context\b", re.IGNORECASE),
            "Attempt to reset AI context",
        ),
        (
            re.compile(r"start\s+fresh\b", re.IGNORECASE),
            "Attempt to start a fresh conversation context",
        ),
        (
            re.compile(r"new\s+conversation\b", re.IGNORECASE),
            "Attempt to start a new conversation context",
        ),
    ],
}

# Base64 pattern: at least 20 chars of valid base64, optionally with padding
_BASE64_RE = re.compile(r"(?:[A-Za-z0-9+/]{4}){5,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")

# Suspicious decoded content keywords
_SUSPICIOUS_DECODED_KEYWORDS = [
    "ignore", "override", "system prompt", "disregard", "forget",
    "you are now", "act as", "pretend", "execute", "run this",
]


# ── Prompt Injection Guard ───────────────────────────────────────────────


class PromptInjectionGuard:
    """Scans user inputs for prompt injection patterns.

    Parameters
    ----------
    safe_threshold:
        Risk score below which an input is considered safe (default 40).
    """

    def __init__(self, *, safe_threshold: float = _SAFE_THRESHOLD) -> None:
        self._safe_threshold = safe_threshold
        self._allowlist: list[re.Pattern[str]] = []
        self._scan_history: list[InjectionScanResult] = []
        self._patterns: dict[InjectionType, list[tuple[re.Pattern[str], str]]] = {
            itype: list(patterns) for itype, patterns in _INJECTION_PATTERNS.items()
        }

    # ── Public API ────────────────────────────────────────────────────

    def scan(self, text: str) -> InjectionScanResult:
        """Scan *text* for prompt injection patterns.

        Returns an :class:`InjectionScanResult` with findings and a composite
        risk score (0-100).  Inputs scoring below the safe threshold are
        marked ``is_safe=True``.
        """
        findings: list[InjectionFinding] = []

        if text:
            # Check regex-based patterns
            for injection_type, patterns in self._patterns.items():
                for pattern, description in patterns:
                    for match in pattern.finditer(text):
                        matched = match.group()
                        if self._is_allowlisted(matched):
                            continue
                        findings.append(
                            InjectionFinding(
                                injection_type=injection_type,
                                matched_pattern=matched,
                                risk_level=_TYPE_WEIGHTS[injection_type],
                                start=match.start(),
                                end=match.end(),
                                description=description,
                            )
                        )

            # Check base64 encoding attacks
            findings.extend(self._check_encoding_attacks(text))

        risk_score = self._compute_risk_score(findings)
        is_safe = risk_score < self._safe_threshold

        result = InjectionScanResult(
            findings=findings,
            risk_score=risk_score,
            is_safe=is_safe,
            input_length=len(text),
        )

        self._scan_history.append(result)

        if findings:
            types_found = {f.injection_type.value for f in findings}
            logger.warning(
                "Prompt injection detected: %d findings, risk_score=%.1f, types=%s",
                len(findings),
                risk_score,
                types_found,
            )

        return result

    def add_allowlist_pattern(self, pattern: str) -> None:
        """Add a regex *pattern* to the allowlist.

        Matches against this pattern will be skipped during scanning.
        """
        self._allowlist.append(re.compile(pattern, re.IGNORECASE))

    def get_stats(self) -> dict:
        """Return aggregate statistics from scan history."""
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
        safe = sum(1 for r in self._scan_history if r.is_safe)
        all_findings = [f for r in self._scan_history for f in r.findings]
        by_type: dict[str, int] = {}
        for f in all_findings:
            by_type[f.injection_type.value] = by_type.get(f.injection_type.value, 0) + 1

        return {
            "total_scans": total,
            "safe_scans": safe,
            "unsafe_scans": total - safe,
            "average_risk_score": sum(r.risk_score for r in self._scan_history) / total,
            "total_findings": len(all_findings),
            "findings_by_type": by_type,
        }

    def clear_history(self) -> None:
        """Clear the in-memory scan history (useful for tests)."""
        self._scan_history.clear()

    # ── Private helpers ───────────────────────────────────────────────

    def _is_allowlisted(self, text: str) -> bool:
        """Check if matched text is in the allowlist."""
        return any(pattern.search(text) for pattern in self._allowlist)

    def _check_encoding_attacks(self, text: str) -> list[InjectionFinding]:
        """Detect base64-encoded strings that decode to suspicious content."""
        findings: list[InjectionFinding] = []

        for match in _BASE64_RE.finditer(text):
            candidate = match.group()
            if self._is_allowlisted(candidate):
                continue

            try:
                decoded = base64.b64decode(candidate).decode("utf-8", errors="ignore").lower()
            except Exception:  # noqa: S112
                continue

            for keyword in _SUSPICIOUS_DECODED_KEYWORDS:
                if keyword in decoded:
                    findings.append(
                        InjectionFinding(
                            injection_type=InjectionType.ENCODING_ATTACK,
                            matched_pattern=candidate,
                            risk_level=_TYPE_WEIGHTS[InjectionType.ENCODING_ATTACK],
                            start=match.start(),
                            end=match.end(),
                            description=(
                                f"Base64 string decodes to "
                                f"suspicious content: '{keyword}'"
                            ),
                        )
                    )
                    break  # One finding per base64 blob is enough

        return findings

    @staticmethod
    def _compute_risk_score(findings: list[InjectionFinding]) -> float:
        """Compute a weighted risk score in the range 0-100."""
        if not findings:
            return 0.0
        total = sum(f.risk_level for f in findings)
        return min(total, 100.0)
