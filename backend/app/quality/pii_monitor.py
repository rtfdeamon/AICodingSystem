"""PII leakage monitoring — validates that AI agent outputs do not contain PII.

Scans agent responses for common PII patterns (emails, phone numbers, SSNs,
credit card numbers, API keys, etc.) and flags or redacts them before they
reach the user.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class PIIType(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    API_KEY = "api_key"
    AWS_KEY = "aws_key"
    PRIVATE_KEY = "private_key"
    JWT_TOKEN = "jwt_token"
    IP_ADDRESS = "ip_address"
    PASSWORD_HASH = "password_hash"


@dataclass
class PIIFinding:
    """A single PII detection."""

    pii_type: PIIType
    matched_text: str
    redacted_text: str
    start: int
    end: int
    confidence: float = 1.0


@dataclass
class PIIScanResult:
    """Result from scanning text for PII."""

    findings: list[PIIFinding] = field(default_factory=list)
    has_pii: bool = False
    redacted_text: str = ""
    original_length: int = 0

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def pii_types_found(self) -> set[str]:
        return {f.pii_type.value for f in self.findings}


# ── Pattern definitions ──────────────────────────────────────────────────

_PII_PATTERNS: list[tuple[PIIType, re.Pattern[str], float]] = [
    # Email addresses
    (
        PIIType.EMAIL,
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        0.95,
    ),
    # Phone numbers (US and international formats)
    (
        PIIType.PHONE,
        re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        0.8,
    ),
    # SSN (US)
    (
        PIIType.SSN,
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        0.9,
    ),
    # Credit card numbers (Visa, MasterCard, AmEx, Discover)
    (
        PIIType.CREDIT_CARD,
        re.compile(
            r"\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))"
            r"[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"
        ),
        0.85,
    ),
    # AWS access key IDs
    (
        PIIType.AWS_KEY,
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        0.95,
    ),
    # Generic API keys (long hex/base64 strings prefixed with key identifiers)
    (
        PIIType.API_KEY,
        re.compile(
            r"(?:sk|pk|api|key|token|secret|bearer)"
            r"[_-]?(?:[A-Za-z0-9_-]+){20,}",
            re.IGNORECASE,
        ),
        0.7,
    ),
    # Private key blocks
    (
        PIIType.PRIVATE_KEY,
        re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"),
        1.0,
    ),
    # JWT tokens
    (
        PIIType.JWT_TOKEN,
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        0.9,
    ),
    # IPv4 addresses (excluding common non-PII like 0.0.0.0, 127.0.0.1, 192.168.x.x)
    (
        PIIType.IP_ADDRESS,
        re.compile(
            r"\b(?!0\.0\.0\.0)(?!127\.0\.0\.1)(?!192\.168\.)(?!10\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)){3}\b"
        ),
        0.6,
    ),
    # Password hashes (bcrypt, argon2, sha256/512)
    (
        PIIType.PASSWORD_HASH,
        re.compile(r"\$(?:2[aby]|argon2(?:id|i|d))\$[^\s]{20,}"),
        0.85,
    ),
]

# Allowlist patterns — skip matches that are clearly not PII
_ALLOWLIST_PATTERNS = [
    re.compile(r"example\.com", re.IGNORECASE),
    re.compile(r"test@test\.com", re.IGNORECASE),
    re.compile(r"user@example\.", re.IGNORECASE),
    re.compile(r"noreply@", re.IGNORECASE),
    re.compile(r"localhost", re.IGNORECASE),
    re.compile(r"placeholder", re.IGNORECASE),
]


def _is_allowlisted(text: str) -> bool:
    """Check if matched text is a known non-PII pattern."""
    return any(pattern.search(text) for pattern in _ALLOWLIST_PATTERNS)


def _redact(text: str, pii_type: PIIType) -> str:
    """Create a redacted version of the matched text."""
    if pii_type == PIIType.EMAIL:
        parts = text.split("@")
        if len(parts) == 2:
            return f"{parts[0][0]}***@{parts[1]}"
    elif pii_type == PIIType.PHONE:
        return "***-***-" + text[-4:]
    elif pii_type == PIIType.SSN:
        return "***-**-" + text[-4:]
    elif pii_type == PIIType.CREDIT_CARD:
        return "****-****-****-" + text[-4:]
    elif pii_type in (PIIType.API_KEY, PIIType.AWS_KEY, PIIType.JWT_TOKEN):
        return text[:6] + "..." + text[-4:]
    elif pii_type == PIIType.PRIVATE_KEY:
        return "[REDACTED PRIVATE KEY]"
    elif pii_type == PIIType.PASSWORD_HASH:
        return "[REDACTED HASH]"

    # Default: show first 2 and last 2 chars
    if len(text) > 4:
        return text[:2] + "*" * (len(text) - 4) + text[-2:]
    return "****"


def scan_for_pii(
    text: str,
    *,
    min_confidence: float = 0.5,
    types_to_check: set[PIIType] | None = None,
) -> PIIScanResult:
    """Scan text for PII patterns.

    Parameters
    ----------
    text:
        The text to scan (typically an AI agent output).
    min_confidence:
        Minimum confidence threshold for reporting findings.
    types_to_check:
        If provided, only check these PII types.

    Returns
    -------
    PIIScanResult with findings and optionally redacted text.
    """
    findings: list[PIIFinding] = []

    for pii_type, pattern, confidence in _PII_PATTERNS:
        if types_to_check and pii_type not in types_to_check:
            continue
        if confidence < min_confidence:
            continue

        for match in pattern.finditer(text):
            matched_text = match.group()
            if _is_allowlisted(matched_text):
                continue

            findings.append(
                PIIFinding(
                    pii_type=pii_type,
                    matched_text=matched_text,
                    redacted_text=_redact(matched_text, pii_type),
                    start=match.start(),
                    end=match.end(),
                    confidence=confidence,
                )
            )

    # Build redacted text
    redacted = text
    # Process findings in reverse order to preserve positions
    for finding in sorted(findings, key=lambda f: f.start, reverse=True):
        redacted = redacted[: finding.start] + finding.redacted_text + redacted[finding.end :]

    has_pii = len(findings) > 0

    if has_pii:
        pii_types = {f.pii_type.value for f in findings}
        logger.warning(
            "PII detected in agent output: %d findings, types=%s",
            len(findings),
            pii_types,
        )

    return PIIScanResult(
        findings=findings,
        has_pii=has_pii,
        redacted_text=redacted,
        original_length=len(text),
    )


def validate_agent_output(text: str) -> tuple[bool, PIIScanResult]:
    """Validate that an agent output does not contain PII.

    Returns (is_clean, scan_result). If is_clean is False, the caller
    should use scan_result.redacted_text instead of the original.
    """
    result = scan_for_pii(text)
    return not result.has_pii, result
