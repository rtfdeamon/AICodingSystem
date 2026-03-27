"""Sensitive Code Zone Policy -- restrict AI in security-critical areas.

Not all code should be AI-generated.  This module enforces policies that
restrict, flag, or require extra review for AI-generated code touching
security-sensitive areas such as authentication, cryptography, payment
processing, and regulatory logic.

Key features:
- File/path pattern matching for sensitive zone detection
- Content-based heuristic detection (crypto imports, auth patterns, etc.)
- Zone classification: forbidden, requires-review, warn-only
- Per-zone policy enforcement with configurable actions
- Exemption management for pre-approved changes
- Audit log of policy decisions
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

class ZoneType(StrEnum):
    AUTH = "authentication"
    CRYPTO = "cryptography"
    PAYMENT = "payment"
    PII_HANDLING = "pii_handling"
    REGULATORY = "regulatory"
    INFRASTRUCTURE = "infrastructure"
    SECRETS = "secrets_management"
    CUSTOM = "custom"


class PolicyAction(StrEnum):
    BLOCK = "block"
    REQUIRE_REVIEW = "require_review"
    WARN = "warn"
    ALLOW = "allow"


class DetectionMethod(StrEnum):
    PATH_PATTERN = "path_pattern"
    CONTENT_HEURISTIC = "content_heuristic"
    BOTH = "both"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class SensitiveZone:
    """Definition of a sensitive code zone."""
    zone_type: ZoneType
    name: str
    path_patterns: list[str] = field(default_factory=list)
    content_patterns: list[str] = field(default_factory=list)
    action: PolicyAction = PolicyAction.REQUIRE_REVIEW
    description: str = ""


@dataclass
class ZoneMatch:
    """A detected match of code against a sensitive zone."""
    zone: SensitiveZone
    file_path: str
    detection_method: DetectionMethod
    matched_patterns: list[str] = field(default_factory=list)
    line_numbers: list[int] = field(default_factory=list)


@dataclass
class PolicyDecision:
    """Result of evaluating code against the sensitive zone policy."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_path: str = ""
    allowed: bool = True
    action: PolicyAction = PolicyAction.ALLOW
    matches: list[ZoneMatch] = field(default_factory=list)
    exemption_used: str | None = None
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class Exemption:
    """Pre-approved exemption for a specific file/zone."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_pattern: str = ""
    zone_type: ZoneType | None = None
    approved_by: str = ""
    reason: str = ""
    expires_at: str | None = None


# ── Policy Engine ────────────────────────────────────────────────────────

class SensitiveZonePolicy:
    """Enforces restrictions on AI-generated code in sensitive areas."""

    DEFAULT_ZONES: list[SensitiveZone] = [
        SensitiveZone(
            zone_type=ZoneType.AUTH,
            name="Authentication & Authorization",
            path_patterns=[
                r"auth[/_\-]",
                r"login",
                r"oauth",
                r"session[/_\-]",
                r"permission",
                r"rbac",
                r"acl",
            ],
            content_patterns=[
                r"password",
                r"bcrypt|argon2|scrypt",
                r"jwt\.encode|jwt\.decode",
                r"verify_password|check_password|hash_password",
                r"set_cookie.*session",
                r"@login_required|@requires_auth",
            ],
            action=PolicyAction.REQUIRE_REVIEW,
            description="Authentication, authorization, and session management code",
        ),
        SensitiveZone(
            zone_type=ZoneType.CRYPTO,
            name="Cryptography",
            path_patterns=[
                r"crypt",
                r"encrypt",
                r"signing",
                r"certificate",
                r"ssl",
                r"tls",
            ],
            content_patterns=[
                r"from\s+cryptography",
                r"import\s+hashlib",
                r"import\s+hmac",
                r"AES|RSA|ECDSA|Ed25519",
                r"private_key|public_key|secret_key",
                r"cipher|encrypt|decrypt",
                r"Fernet|PBKDF2",
            ],
            action=PolicyAction.BLOCK,
            description="Cryptographic operations and key management",
        ),
        SensitiveZone(
            zone_type=ZoneType.PAYMENT,
            name="Payment Processing",
            path_patterns=[
                r"payment",
                r"billing",
                r"checkout",
                r"stripe",
                r"paypal",
                r"transaction",
            ],
            content_patterns=[
                r"credit_card|card_number|cvv|cvc",
                r"stripe\.|paypal\.",
                r"charge|refund|subscription",
                r"bank_account|routing_number",
            ],
            action=PolicyAction.BLOCK,
            description="Payment processing and financial transaction logic",
        ),
        SensitiveZone(
            zone_type=ZoneType.PII_HANDLING,
            name="PII Data Handling",
            path_patterns=[
                r"pii",
                r"gdpr",
                r"privacy",
                r"personal_data",
                r"data_subject",
            ],
            content_patterns=[
                r"social_security|ssn",
                r"date_of_birth|dob",
                r"passport_number",
                r"medical_record",
                r"biometric",
                r"anonymize|pseudonymize|redact_pii",
            ],
            action=PolicyAction.REQUIRE_REVIEW,
            description="Code handling personally identifiable information",
        ),
        SensitiveZone(
            zone_type=ZoneType.SECRETS,
            name="Secrets Management",
            path_patterns=[
                r"secret",
                r"vault",
                r"keystore",
                r"\.env",
                r"credential",
            ],
            content_patterns=[
                r"API_KEY|SECRET_KEY|ACCESS_TOKEN",
                r"os\.environ\.get.*(?:KEY|SECRET|TOKEN|PASSWORD)",
                r"vault\.read|vault\.write",
                r"getSecret|putSecret",
            ],
            action=PolicyAction.REQUIRE_REVIEW,
            description="Secrets storage and retrieval logic",
        ),
        SensitiveZone(
            zone_type=ZoneType.INFRASTRUCTURE,
            name="Infrastructure & Deployment",
            path_patterns=[
                r"terraform",
                r"cloudformation",
                r"k8s|kubernetes",
                r"docker",
                r"infra/",
                r"deploy",
            ],
            content_patterns=[
                r"security_group|firewall_rule",
                r"iam_policy|iam_role",
                r"network_acl|subnet",
                r"privileged.*true|host_network",
            ],
            action=PolicyAction.WARN,
            description="Infrastructure-as-code and deployment configurations",
        ),
    ]

    def __init__(
        self,
        *,
        zones: list[SensitiveZone] | None = None,
        use_defaults: bool = True,
    ) -> None:
        self._zones: list[SensitiveZone] = []
        if use_defaults:
            self._zones.extend(self.DEFAULT_ZONES)
        if zones:
            self._zones.extend(zones)
        self._exemptions: list[Exemption] = []
        self._decisions: list[PolicyDecision] = []

    # ── Zone management ──────────────────────────────────────────────

    def add_zone(self, zone: SensitiveZone) -> None:
        self._zones.append(zone)

    def remove_zone(self, zone_type: ZoneType) -> int:
        before = len(self._zones)
        self._zones = [z for z in self._zones if z.zone_type != zone_type]
        return before - len(self._zones)

    @property
    def zones(self) -> list[SensitiveZone]:
        return list(self._zones)

    # ── Exemptions ───────────────────────────────────────────────────

    def add_exemption(self, exemption: Exemption) -> str:
        self._exemptions.append(exemption)
        return exemption.id

    def remove_exemption(self, exemption_id: str) -> bool:
        before = len(self._exemptions)
        self._exemptions = [e for e in self._exemptions if e.id != exemption_id]
        return len(self._exemptions) < before

    def _find_exemption(self, file_path: str, zone_type: ZoneType) -> Exemption | None:
        now = datetime.now(UTC).isoformat()
        for ex in self._exemptions:
            if ex.expires_at and ex.expires_at < now:
                continue
            if ex.zone_type and ex.zone_type != zone_type:
                continue
            if ex.file_pattern and re.search(ex.file_pattern, file_path):
                return ex
        return None

    # ── Evaluation ───────────────────────────────────────────────────

    def check_file(self, file_path: str, content: str = "") -> PolicyDecision:
        matches: list[ZoneMatch] = []

        for zone in self._zones:
            match = self._match_zone(zone, file_path, content)
            if match:
                matches.append(match)

        if not matches:
            decision = PolicyDecision(
                file_path=file_path,
                allowed=True,
                action=PolicyAction.ALLOW,
                reason="No sensitive zone matched",
            )
            self._decisions.append(decision)
            return decision

        # Find strictest action
        action_priority = {
            PolicyAction.BLOCK: 3,
            PolicyAction.REQUIRE_REVIEW: 2,
            PolicyAction.WARN: 1,
            PolicyAction.ALLOW: 0,
        }
        strictest = max(matches, key=lambda m: action_priority.get(m.zone.action, 0))
        action = strictest.zone.action

        # Check exemptions
        exemption = self._find_exemption(file_path, strictest.zone.zone_type)
        if exemption:
            decision = PolicyDecision(
                file_path=file_path,
                allowed=True,
                action=PolicyAction.ALLOW,
                matches=matches,
                exemption_used=exemption.id,
                reason=f"Exempted: {exemption.reason}",
            )
            self._decisions.append(decision)
            return decision

        allowed = action in (PolicyAction.ALLOW, PolicyAction.WARN)
        zones_desc = ", ".join(m.zone.name for m in matches)
        decision = PolicyDecision(
            file_path=file_path,
            allowed=allowed,
            action=action,
            matches=matches,
            reason=f"Matched sensitive zones: {zones_desc}",
        )
        self._decisions.append(decision)
        return decision

    def check_batch(self, files: dict[str, str]) -> list[PolicyDecision]:
        return [self.check_file(path, content) for path, content in files.items()]

    def _match_zone(
        self, zone: SensitiveZone, file_path: str, content: str
    ) -> ZoneMatch | None:
        path_matches: list[str] = []
        content_matches: list[str] = []
        line_numbers: list[int] = []

        for pattern in zone.path_patterns:
            if re.search(pattern, file_path, re.IGNORECASE):
                path_matches.append(pattern)

        if content:
            for pattern in zone.content_patterns:
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        content_matches.append(pattern)
                        line_numbers.append(i)

        if not path_matches and not content_matches:
            return None

        if path_matches and content_matches:
            method = DetectionMethod.BOTH
        elif path_matches:
            method = DetectionMethod.PATH_PATTERN
        else:
            method = DetectionMethod.CONTENT_HEURISTIC

        return ZoneMatch(
            zone=zone,
            file_path=file_path,
            detection_method=method,
            matched_patterns=path_matches + content_matches,
            line_numbers=sorted(set(line_numbers)),
        )

    # ── Analytics ────────────────────────────────────────────────────

    @property
    def decisions(self) -> list[PolicyDecision]:
        return list(self._decisions)

    def clear_decisions(self) -> int:
        count = len(self._decisions)
        self._decisions.clear()
        return count

    def blocked_files(self) -> list[str]:
        return [d.file_path for d in self._decisions if d.action == PolicyAction.BLOCK]

    def summary(self) -> dict[str, Any]:
        total = len(self._decisions)
        by_action: dict[str, int] = {}
        by_zone: dict[str, int] = {}
        for d in self._decisions:
            by_action[d.action] = by_action.get(d.action, 0) + 1
            for m in d.matches:
                by_zone[m.zone.zone_type] = by_zone.get(m.zone.zone_type, 0) + 1

        return {
            "total_checks": total,
            "by_action": by_action,
            "by_zone_type": by_zone,
            "blocked_count": sum(1 for d in self._decisions if d.action == PolicyAction.BLOCK),
            "review_required_count": sum(
                1 for d in self._decisions if d.action == PolicyAction.REQUIRE_REVIEW
            ),
            "exemptions_used": sum(
                1 for d in self._decisions if d.exemption_used
            ),
            "zones_configured": len(self._zones),
            "exemptions_configured": len(self._exemptions),
        }
