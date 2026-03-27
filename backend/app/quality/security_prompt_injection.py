"""Security-Aware Prompt Injection for AI Agents.

Enriches every AI agent prompt with security-focused system instructions that
remind the model to write secure code.  Research (Veracode 2026) shows that a
generic security reminder raises the secure-and-correct code rate from 56 % to
66 % on Claude Opus 4.5 Thinking, and domain-specific rules push it higher.

The module provides:
- Security system-prompt fragments (general + per-language)
- OWASP Top-10 checklist reminders scoped to the code context
- Sensitive-zone detection: if code touches auth, crypto, or payments the
  prompt is upgraded to a stricter level
- Prompt composition: merge security instructions into the agent's
  existing system prompt without breaking its structure
- Audit: every enrichment is logged with the security level applied
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class SecurityLevel(StrEnum):
    STANDARD = "standard"
    ELEVATED = "elevated"
    CRITICAL = "critical"


class CodeDomain(StrEnum):
    GENERAL = "general"
    AUTH = "auth"
    CRYPTO = "crypto"
    PAYMENTS = "payments"
    DATABASE = "database"
    FILE_IO = "file_io"
    NETWORK = "network"
    USER_INPUT = "user_input"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class SecurityEnrichment:
    """Record of a prompt security enrichment."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    security_level: SecurityLevel = SecurityLevel.STANDARD
    domains_detected: list[CodeDomain] = field(default_factory=list)
    rules_injected: int = 0
    original_prompt_length: int = 0
    enriched_prompt_length: int = 0
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


# ── Security prompt fragments ────────────────────────────────────────────

_GENERAL_SECURITY_PROMPT = """
SECURITY REQUIREMENTS — You MUST follow these rules for all generated code:
1. Never hardcode secrets, API keys, passwords, or tokens.
2. Validate and sanitize ALL user input before processing.
3. Use parameterized queries — never string-concatenate SQL.
4. Escape output for the target context (HTML, JSON, shell).
5. Use constant-time comparison for security-sensitive values.
6. Handle errors without leaking internal details to users.
7. Apply the principle of least privilege for all operations.
8. Use secure defaults (HTTPS, secure cookies, strict CORS).
""".strip()

_DOMAIN_PROMPTS: dict[CodeDomain, str] = {
    CodeDomain.AUTH: (
        "AUTH-SPECIFIC: Use bcrypt/argon2 for password hashing (never MD5/SHA). "
        "Implement rate limiting on login endpoints. Use short-lived JWTs with "
        "refresh tokens. Never store passwords in plain text or reversible encryption."
    ),
    CodeDomain.CRYPTO: (
        "CRYPTO-SPECIFIC: Use well-tested libraries (cryptography, PyCryptodome). "
        "Never implement your own crypto primitives. Use AES-256-GCM for symmetric "
        "encryption. Generate IVs/nonces with os.urandom(), never reuse them."
    ),
    CodeDomain.PAYMENTS: (
        "PAYMENTS-SPECIFIC: Never log full card numbers or CVVs. Use PCI-compliant "
        "libraries for payment processing. Validate amounts server-side. "
        "Implement idempotency keys for all payment operations."
    ),
    CodeDomain.DATABASE: (
        "DATABASE-SPECIFIC: Always use parameterized queries or ORM methods. "
        "Apply column-level encryption for PII. Use read-only replicas where possible. "
        "Never expose raw database errors to the API consumer."
    ),
    CodeDomain.FILE_IO: (
        "FILE-IO-SPECIFIC: Validate file paths to prevent traversal attacks. "
        "Set size limits on uploads. Check MIME types, not just extensions. "
        "Store uploaded files outside the web root."
    ),
    CodeDomain.NETWORK: (
        "NETWORK-SPECIFIC: Validate and sanitize URLs to prevent SSRF. "
        "Set timeouts on all outgoing HTTP calls. Verify TLS certificates. "
        "Never follow redirects to internal/private IP ranges."
    ),
    CodeDomain.USER_INPUT: (
        "INPUT-SPECIFIC: Whitelist-validate where possible (regex, enum). "
        "Reject input that exceeds expected length. Encode output for the "
        "destination context. Implement CSRF tokens for state-changing forms."
    ),
}

# ── Domain detection ─────────────────────────────────────────────────────

_DOMAIN_PATTERNS: list[tuple[CodeDomain, list[str]]] = [
    (CodeDomain.AUTH, [
        r"password", r"login", r"auth", r"jwt", r"token", r"session",
        r"bcrypt", r"passlib", r"oauth", r"permission", r"credentials",
    ]),
    (CodeDomain.CRYPTO, [
        r"encrypt", r"decrypt", r"cipher", r"aes", r"rsa", r"hmac",
        r"cryptography", r"hashlib\.(?!md5)", r"signing", r"private_key",
    ]),
    (CodeDomain.PAYMENTS, [
        r"payment", r"stripe", r"charge", r"invoice", r"billing",
        r"credit_card", r"card_number", r"checkout",
    ]),
    (CodeDomain.DATABASE, [
        r"SELECT\s", r"INSERT\s", r"UPDATE\s", r"DELETE\s", r"sqlalchemy",
        r"execute\(", r"cursor", r"\.query\(", r"\.filter\(",
    ]),
    (CodeDomain.FILE_IO, [
        r"open\(", r"Path\(", r"os\.path", r"shutil", r"upload",
        r"file_path", r"write_bytes", r"read_bytes",
    ]),
    (CodeDomain.NETWORK, [
        r"requests\.", r"httpx\.", r"aiohttp", r"urllib",
        r"fetch\(", r"\.get\(.*url", r"\.post\(.*url",
    ]),
    (CodeDomain.USER_INPUT, [
        r"request\.form", r"request\.json", r"request\.args",
        r"body\.", r"params\.", r"query\.",
        r"Form\(", r"Body\(", r"Query\(",
    ]),
]


def detect_domains(code_or_prompt: str) -> list[CodeDomain]:
    """Detect which security domains are relevant to the given code/prompt."""
    detected: set[CodeDomain] = set()
    for domain, patterns in _DOMAIN_PATTERNS:
        for pat in patterns:
            if re.search(pat, code_or_prompt, re.IGNORECASE):
                detected.add(domain)
                break
    return sorted(detected, key=lambda d: d.value)


def determine_security_level(domains: list[CodeDomain]) -> SecurityLevel:
    """Determine security level based on detected domains."""
    critical_domains = {CodeDomain.AUTH, CodeDomain.CRYPTO, CodeDomain.PAYMENTS}
    elevated_domains = {CodeDomain.DATABASE, CodeDomain.FILE_IO, CodeDomain.NETWORK}

    if critical_domains & set(domains):
        return SecurityLevel.CRITICAL
    if elevated_domains & set(domains):
        return SecurityLevel.ELEVATED
    return SecurityLevel.STANDARD


# ── Prompt enricher ──────────────────────────────────────────────────────

_enrichment_history: list[SecurityEnrichment] = []


def enrich_prompt(
    original_prompt: str,
    *,
    code_context: str = "",
    force_level: SecurityLevel | None = None,
) -> tuple[str, SecurityEnrichment]:
    """Inject security instructions into an agent prompt.

    Returns the enriched prompt and an enrichment record.
    """
    # Detect domains from both prompt and code context
    combined = f"{original_prompt}\n{code_context}"
    domains = detect_domains(combined)
    level = force_level or determine_security_level(domains)

    # Build security block
    parts: list[str] = [_GENERAL_SECURITY_PROMPT]
    rules_count = 8  # general rules

    for domain in domains:
        domain_prompt = _DOMAIN_PROMPTS.get(domain)
        if domain_prompt:
            parts.append(domain_prompt)
            rules_count += 1

    if level == SecurityLevel.CRITICAL:
        parts.append(
            "CRITICAL SECURITY CONTEXT: This code handles highly sensitive "
            "operations. Every change MUST be reviewed by a security engineer. "
            "Add security-relevant comments explaining your defensive choices."
        )
        rules_count += 1

    security_block = "\n\n".join(parts)

    # Compose final prompt
    enriched = f"{security_block}\n\n---\n\n{original_prompt}"

    record = SecurityEnrichment(
        security_level=level,
        domains_detected=domains,
        rules_injected=rules_count,
        original_prompt_length=len(original_prompt),
        enriched_prompt_length=len(enriched),
    )
    _enrichment_history.append(record)

    logger.info(
        "Enriched prompt: level=%s, domains=%s, +%d rules",
        level, domains, rules_count,
    )
    return enriched, record


# ── Analytics ────────────────────────────────────────────────────────────

def get_enrichment_history() -> list[SecurityEnrichment]:
    return list(_enrichment_history)


def get_enrichment_stats() -> dict[str, Any]:
    """Aggregate statistics across all enrichments."""
    if not _enrichment_history:
        return {"total_enrichments": 0}

    total = len(_enrichment_history)
    by_level: dict[str, int] = {}
    domain_freq: dict[str, int] = {}
    total_rules = 0

    for e in _enrichment_history:
        by_level[e.security_level] = by_level.get(e.security_level, 0) + 1
        total_rules += e.rules_injected
        for d in e.domains_detected:
            domain_freq[d] = domain_freq.get(d, 0) + 1

    return {
        "total_enrichments": total,
        "by_level": by_level,
        "domain_frequency": domain_freq,
        "avg_rules_per_enrichment": round(total_rules / total, 1),
    }


def clear_enrichment_history() -> None:
    _enrichment_history.clear()
