"""
AI Bill of Materials (AI-BOM) — tracks provenance of every AI-generated artifact.

Extends traditional SBOM to record which model generated each code block,
the model version, prompt hash, generation timestamp, and license compliance
flags.  Scans AI-generated code for similarity to known copyleft-licensed
snippets and flags potential IP violations before merge.

Industry context (2025-2026):
- EU AI Act GPAI obligations (August 2025) treat SBOM disclosure as regulatory baseline
- 0.88-2.01% of LLM output is similar to existing open-source code
- AI-BOM generation should be integrated into CI/CD so it is never skipped
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class LicenseRisk(StrEnum):
    NONE = "none"
    LOW = "low"            # permissive (MIT, Apache-2.0, BSD)
    MEDIUM = "medium"      # weak copyleft (LGPL, MPL)
    HIGH = "high"          # strong copyleft (GPL, AGPL)
    UNKNOWN = "unknown"    # unable to determine


class ArtifactKind(StrEnum):
    CODE = "code"
    TEST = "test"
    PLAN = "plan"
    REVIEW = "review"
    CONFIG = "config"
    DOCUMENTATION = "documentation"


@dataclass
class AIArtifact:
    """Single AI-generated artifact with full provenance metadata."""

    artifact_id: str
    kind: ArtifactKind
    model_id: str
    model_version: str
    prompt_hash: str
    content_hash: str
    generated_at: str  # ISO-8601
    ticket_id: str | None = None
    file_path: str | None = None
    token_count: int = 0
    cost_usd: float = 0.0
    license_risk: LicenseRisk = LicenseRisk.NONE
    license_flags: list[str] = field(default_factory=list)
    similarity_matches: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind.value,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "prompt_hash": self.prompt_hash,
            "content_hash": self.content_hash,
            "generated_at": self.generated_at,
            "ticket_id": self.ticket_id,
            "file_path": self.file_path,
            "token_count": self.token_count,
            "cost_usd": self.cost_usd,
            "license_risk": self.license_risk.value,
            "license_flags": self.license_flags,
            "similarity_matches": self.similarity_matches,
        }


@dataclass
class BOMReport:
    """Aggregate AI-BOM report for a project / release."""

    report_id: str
    project_id: str
    generated_at: str
    artifacts: list[AIArtifact] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    license_summary: dict[str, int] = field(default_factory=dict)
    models_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "project_id": self.project_id,
            "generated_at": self.generated_at,
            "artifact_count": len(self.artifacts),
            "total_cost_usd": self.total_cost_usd,
            "total_tokens": self.total_tokens,
            "license_summary": self.license_summary,
            "models_used": self.models_used,
            "artifacts": [a.to_dict() for a in self.artifacts],
        }


# ---------------------------------------------------------------------------
# Known copyleft patterns
# ---------------------------------------------------------------------------

COPYLEFT_MARKERS: list[tuple[str, LicenseRisk, str]] = [
    # Strong copyleft
    (r"GNU\s+General\s+Public\s+License", LicenseRisk.HIGH, "GPL"),
    (r"GPLv[23]", LicenseRisk.HIGH, "GPL"),
    (r"AGPL", LicenseRisk.HIGH, "AGPL"),
    (r"GNU\s+Affero", LicenseRisk.HIGH, "AGPL"),
    # Weak copyleft
    (r"LGPL", LicenseRisk.MEDIUM, "LGPL"),
    (r"Mozilla\s+Public\s+License", LicenseRisk.MEDIUM, "MPL"),
    (r"MPL-?2", LicenseRisk.MEDIUM, "MPL-2.0"),
    (r"Eclipse\s+Public\s+License", LicenseRisk.MEDIUM, "EPL"),
    # Permissive (for tracking, not blocking)
    (r"MIT\s+License", LicenseRisk.LOW, "MIT"),
    (r"Apache\s+License", LicenseRisk.LOW, "Apache-2.0"),
    (r"BSD\s+\d-Clause", LicenseRisk.LOW, "BSD"),
]

# Common code patterns that frequently appear in copyleft projects
COPYLEFT_CODE_SIGNATURES: list[tuple[str, str]] = [
    # GPL preamble
    (r"This\s+program\s+is\s+free\s+software.*redistribute", "GPL-preamble"),
    # License headers
    (r"SPDX-License-Identifier:\s*(GPL|AGPL|LGPL)", "SPDX-copyleft"),
    # Common copyleft project markers
    (r"Copyright\s+\(C\)\s+Free\s+Software\s+Foundation", "FSF-copyright"),
]


# ---------------------------------------------------------------------------
# AI-BOM Tracker
# ---------------------------------------------------------------------------

class AIBOMTracker:
    """
    Tracks provenance of AI-generated code and produces AI-BOM reports.

    Responsibilities:
    - Record every AI generation with model, prompt, and output metadata
    - Scan generated code for license compliance risks
    - Produce aggregate BOM reports for auditing and compliance
    - Detect potential copyleft contamination
    """

    def __init__(self) -> None:
        self._artifacts: list[AIArtifact] = []
        self._known_signatures: list[tuple[str, str, LicenseRisk]] = []

    # -- Registration -------------------------------------------------------

    def register_artifact(
        self,
        *,
        kind: ArtifactKind,
        model_id: str,
        model_version: str,
        prompt: str,
        content: str,
        ticket_id: str | None = None,
        file_path: str | None = None,
        token_count: int = 0,
        cost_usd: float = 0.0,
    ) -> AIArtifact:
        """Register a new AI-generated artifact with full provenance."""
        now = datetime.now(UTC).isoformat()
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        artifact_id = f"ai-{content_hash}-{len(self._artifacts)}"

        # License scan
        license_flags: list[str] = []
        license_risk = LicenseRisk.NONE
        similarity_matches: list[dict[str, Any]] = []

        scan = self.scan_license_risk(content)
        license_risk = scan["overall_risk"]
        license_flags = scan["flags"]
        similarity_matches = scan["matches"]

        artifact = AIArtifact(
            artifact_id=artifact_id,
            kind=kind,
            model_id=model_id,
            model_version=model_version,
            prompt_hash=prompt_hash,
            content_hash=content_hash,
            generated_at=now,
            ticket_id=ticket_id,
            file_path=file_path,
            token_count=token_count,
            cost_usd=cost_usd,
            license_risk=license_risk,
            license_flags=license_flags,
            similarity_matches=similarity_matches,
        )
        self._artifacts.append(artifact)
        return artifact

    # -- License scanning ---------------------------------------------------

    def scan_license_risk(self, content: str) -> dict[str, Any]:
        """Scan content for license compliance risks."""
        flags: list[str] = []
        matches: list[dict[str, Any]] = []
        max_risk = LicenseRisk.NONE

        # Check for license markers in content
        for pattern, risk, name in COPYLEFT_MARKERS:
            if re.search(pattern, content, re.IGNORECASE):
                flags.append(f"license-marker:{name}")
                matches.append({
                    "type": "license_marker",
                    "license": name,
                    "risk": risk.value,
                })
                if _risk_level(risk) > _risk_level(max_risk):
                    max_risk = risk

        # Check for copyleft code signatures
        for pattern, sig_name in COPYLEFT_CODE_SIGNATURES:
            if re.search(pattern, content, re.IGNORECASE):
                flags.append(f"code-signature:{sig_name}")
                matches.append({
                    "type": "code_signature",
                    "signature": sig_name,
                    "risk": LicenseRisk.HIGH.value,
                })
                if _risk_level(LicenseRisk.HIGH) > _risk_level(max_risk):
                    max_risk = LicenseRisk.HIGH

        # Check against registered known signatures
        for sig_pattern, sig_name, sig_risk in self._known_signatures:
            if re.search(sig_pattern, content, re.IGNORECASE):
                flags.append(f"known-signature:{sig_name}")
                matches.append({
                    "type": "known_signature",
                    "signature": sig_name,
                    "risk": sig_risk.value,
                })
                if _risk_level(sig_risk) > _risk_level(max_risk):
                    max_risk = sig_risk

        return {
            "overall_risk": max_risk,
            "flags": flags,
            "matches": matches,
        }

    def add_known_signature(
        self, pattern: str, name: str, risk: LicenseRisk
    ) -> None:
        """Register a known copyleft code signature for matching."""
        self._known_signatures.append((pattern, name, risk))

    # -- Reporting ----------------------------------------------------------

    def generate_report(self, project_id: str) -> BOMReport:
        """Generate aggregate AI-BOM report for all tracked artifacts."""
        now = datetime.now(UTC).isoformat()
        report_id = f"bom-{hashlib.sha256(now.encode()).hexdigest()[:12]}"

        total_cost = sum(a.cost_usd for a in self._artifacts)
        total_tokens = sum(a.token_count for a in self._artifacts)

        license_summary: dict[str, int] = {}
        for a in self._artifacts:
            key = a.license_risk.value
            license_summary[key] = license_summary.get(key, 0) + 1

        models_used = sorted(set(a.model_id for a in self._artifacts))

        return BOMReport(
            report_id=report_id,
            project_id=project_id,
            generated_at=now,
            artifacts=list(self._artifacts),
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            license_summary=license_summary,
            models_used=models_used,
        )

    def get_high_risk_artifacts(self) -> list[AIArtifact]:
        """Return artifacts with HIGH or UNKNOWN license risk."""
        return [
            a for a in self._artifacts
            if a.license_risk in (LicenseRisk.HIGH, LicenseRisk.UNKNOWN)
        ]

    def get_artifacts_by_model(self, model_id: str) -> list[AIArtifact]:
        """Return all artifacts generated by a specific model."""
        return [a for a in self._artifacts if a.model_id == model_id]

    def get_artifacts_by_ticket(self, ticket_id: str) -> list[AIArtifact]:
        """Return all artifacts associated with a ticket."""
        return [a for a in self._artifacts if a.ticket_id == ticket_id]

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics."""
        kind_counts: dict[str, int] = {}
        for a in self._artifacts:
            kind_counts[a.kind.value] = kind_counts.get(a.kind.value, 0) + 1

        return {
            "total_artifacts": len(self._artifacts),
            "total_cost_usd": sum(a.cost_usd for a in self._artifacts),
            "total_tokens": sum(a.token_count for a in self._artifacts),
            "by_kind": kind_counts,
            "high_risk_count": len(self.get_high_risk_artifacts()),
            "models_used": sorted(set(a.model_id for a in self._artifacts)),
        }

    @property
    def artifacts(self) -> list[AIArtifact]:
        return list(self._artifacts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RISK_ORDER = {
    LicenseRisk.NONE: 0,
    LicenseRisk.LOW: 1,
    LicenseRisk.MEDIUM: 2,
    LicenseRisk.HIGH: 3,
    LicenseRisk.UNKNOWN: 4,
}


def _risk_level(risk: LicenseRisk) -> int:
    return _RISK_ORDER.get(risk, 0)
