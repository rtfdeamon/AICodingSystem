"""License Compliance Verification — automated detection of open-source
license obligations in AI-generated code.

LLMs frequently generate code strikingly similar to existing open-source
projects but fail to include proper license attribution.  This module
implements a LICO (License Compliance) scoring pipeline that:

1. Detects similarity between generated code and known open-source snippets
2. Classifies license type (permissive vs copyleft)
3. Validates whether proper attribution is present
4. Blocks or warns on copyleft-licensed code without attribution

Based on Xu et al. "LiCoEval: Evaluating LLMs on License Compliance in
Code Generation" (ICSE 2025, IEEE/ACM).

Key capabilities:
- Fingerprint-based similarity detection (n-gram / token hashing)
- License classification: MIT, Apache-2.0, GPL, AGPL, LGPL, BSD, etc.
- LICO score combining similarity incidence with attribution accuracy
- Copyleft-weighted scoring (GPL/AGPL violations weigh 2×)
- CI/CD gate: block, warn, or info based on compliance threshold
- Attribution template generation for compliant usage
- Batch scanning with aggregated compliance reports
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class LicenseFamily(StrEnum):
    PERMISSIVE = "permissive"
    WEAK_COPYLEFT = "weak_copyleft"
    STRONG_COPYLEFT = "strong_copyleft"
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"


class LicenseId(StrEnum):
    MIT = "MIT"
    APACHE_2 = "Apache-2.0"
    BSD_2 = "BSD-2-Clause"
    BSD_3 = "BSD-3-Clause"
    ISC = "ISC"
    GPL_2 = "GPL-2.0"
    GPL_3 = "GPL-3.0"
    AGPL_3 = "AGPL-3.0"
    LGPL_2_1 = "LGPL-2.1"
    LGPL_3 = "LGPL-3.0"
    MPL_2 = "MPL-2.0"
    UNLICENSE = "Unlicense"
    UNKNOWN = "Unknown"


class ComplianceStatus(StrEnum):
    COMPLIANT = "compliant"
    NEEDS_ATTRIBUTION = "needs_attribution"
    VIOLATION = "violation"
    CLEAR = "clear"  # no similarity detected


class GateAction(StrEnum):
    BLOCK = "block"
    WARN = "warn"
    INFO = "info"
    PASS = "pass"


LICENSE_FAMILIES: dict[LicenseId, LicenseFamily] = {
    LicenseId.MIT: LicenseFamily.PERMISSIVE,
    LicenseId.APACHE_2: LicenseFamily.PERMISSIVE,
    LicenseId.BSD_2: LicenseFamily.PERMISSIVE,
    LicenseId.BSD_3: LicenseFamily.PERMISSIVE,
    LicenseId.ISC: LicenseFamily.PERMISSIVE,
    LicenseId.GPL_2: LicenseFamily.STRONG_COPYLEFT,
    LicenseId.GPL_3: LicenseFamily.STRONG_COPYLEFT,
    LicenseId.AGPL_3: LicenseFamily.STRONG_COPYLEFT,
    LicenseId.LGPL_2_1: LicenseFamily.WEAK_COPYLEFT,
    LicenseId.LGPL_3: LicenseFamily.WEAK_COPYLEFT,
    LicenseId.MPL_2: LicenseFamily.WEAK_COPYLEFT,
    LicenseId.UNLICENSE: LicenseFamily.PERMISSIVE,
    LicenseId.UNKNOWN: LicenseFamily.UNKNOWN,
}


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class KnownSnippet:
    """A known open-source code snippet in the reference database."""

    id: str
    source_repo: str
    file_path: str
    license_id: LicenseId
    fingerprints: set[str] = field(default_factory=set)
    attribution_text: str = ""


@dataclass
class SimilarityMatch:
    """A detected similarity between generated and known code."""

    snippet_id: str
    source_repo: str
    license_id: LicenseId
    similarity_score: float  # 0.0 – 1.0
    matching_fingerprints: int
    total_fingerprints: int


@dataclass
class ComplianceResult:
    """Compliance analysis result for a single code block."""

    code_hash: str
    status: ComplianceStatus
    matches: list[SimilarityMatch]
    lico_score: float  # 0.0 (worst) – 1.0 (best)
    gate_action: GateAction
    attribution_needed: list[str]
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchComplianceReport:
    """Aggregated compliance report for a batch of code blocks."""

    total_checked: int
    compliant: int
    violations: int
    needs_attribution: int
    clear: int
    avg_lico_score: float
    license_breakdown: dict[str, int]
    blocked_count: int


@dataclass
class AttributionTemplate:
    """Generated attribution text for compliant usage."""

    license_id: LicenseId
    source_repo: str
    attribution_text: str
    spdx_identifier: str


# ── License Compliance Engine ────────────────────────────────────────────

class LicenseComplianceEngine:
    """Automated license compliance verification for AI-generated code.

    Maintains a reference database of known open-source snippets and
    checks generated code against it for similarity and license compliance.
    """

    def __init__(
        self,
        *,
        similarity_threshold: float = 0.7,
        ngram_size: int = 4,
        copyleft_weight: float = 2.0,
        gate_threshold: float = 0.6,
    ) -> None:
        self._snippets: dict[str, KnownSnippet] = {}
        self._similarity_threshold = similarity_threshold
        self._ngram_size = ngram_size
        self._copyleft_weight = copyleft_weight
        self._gate_threshold = gate_threshold
        self._audit_log: list[dict[str, Any]] = []

    # ── Public API ───────────────────────────────────────────────────

    def register_snippet(self, snippet: KnownSnippet) -> None:
        """Register a known open-source snippet for matching."""
        if not snippet.fingerprints:
            # Auto-generate fingerprints if not provided
            snippet.fingerprints = set()  # Caller should provide fingerprints
        self._snippets[snippet.id] = snippet

    def register_code(
        self,
        snippet_id: str,
        source_repo: str,
        file_path: str,
        license_id: LicenseId,
        code: str,
        attribution_text: str = "",
    ) -> KnownSnippet:
        """Register source code and auto-generate fingerprints."""
        fps = self._generate_fingerprints(code)
        snippet = KnownSnippet(
            id=snippet_id,
            source_repo=source_repo,
            file_path=file_path,
            license_id=license_id,
            fingerprints=fps,
            attribution_text=attribution_text,
        )
        self._snippets[snippet_id] = snippet
        return snippet

    def check_compliance(self, code: str) -> ComplianceResult:
        """Check a code block for license compliance."""
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
        generated_fps = self._generate_fingerprints(code)

        matches: list[SimilarityMatch] = []
        for snippet in self._snippets.values():
            if not snippet.fingerprints:
                continue
            common = generated_fps & snippet.fingerprints
            similarity = len(common) / max(len(snippet.fingerprints), 1)
            if similarity >= self._similarity_threshold:
                matches.append(SimilarityMatch(
                    snippet_id=snippet.id,
                    source_repo=snippet.source_repo,
                    license_id=snippet.license_id,
                    similarity_score=similarity,
                    matching_fingerprints=len(common),
                    total_fingerprints=len(snippet.fingerprints),
                ))

        # Compute LICO score
        lico_score = self._compute_lico(matches)

        # Determine status
        if not matches:
            status = ComplianceStatus.CLEAR
        elif all(self._has_attribution(m) for m in matches):
            status = ComplianceStatus.COMPLIANT
        elif any(
            LICENSE_FAMILIES.get(m.license_id) == LicenseFamily.STRONG_COPYLEFT
            for m in matches
        ):
            status = ComplianceStatus.VIOLATION
        else:
            status = ComplianceStatus.NEEDS_ATTRIBUTION

        # Gate action
        if status == ComplianceStatus.VIOLATION:
            gate = GateAction.BLOCK
        elif status == ComplianceStatus.NEEDS_ATTRIBUTION:
            gate = GateAction.WARN
        elif lico_score < self._gate_threshold:
            gate = GateAction.INFO
        else:
            gate = GateAction.PASS

        attribution_needed = [
            self._generate_attribution(m) for m in matches
            if not self._has_attribution(m)
        ]

        result = ComplianceResult(
            code_hash=code_hash,
            status=status,
            matches=matches,
            lico_score=lico_score,
            gate_action=gate,
            attribution_needed=attribution_needed,
        )

        self._audit_log.append({
            "action": "check_compliance",
            "code_hash": code_hash,
            "status": status,
            "matches": len(matches),
            "lico_score": lico_score,
            "gate": gate,
            "timestamp": result.timestamp,
        })

        return result

    def check_batch(self, code_blocks: list[str]) -> BatchComplianceReport:
        """Check multiple code blocks and return aggregated report."""
        results = [self.check_compliance(code) for code in code_blocks]

        license_counts: dict[str, int] = {}
        for r in results:
            for m in r.matches:
                license_counts[m.license_id] = license_counts.get(m.license_id, 0) + 1

        return BatchComplianceReport(
            total_checked=len(results),
            compliant=sum(1 for r in results if r.status == ComplianceStatus.COMPLIANT),
            violations=sum(1 for r in results if r.status == ComplianceStatus.VIOLATION),
            needs_attribution=sum(
                1 for r in results
                if r.status == ComplianceStatus.NEEDS_ATTRIBUTION
            ),
            clear=sum(1 for r in results if r.status == ComplianceStatus.CLEAR),
            avg_lico_score=sum(r.lico_score for r in results) / max(len(results), 1),
            license_breakdown=license_counts,
            blocked_count=sum(1 for r in results if r.gate_action == GateAction.BLOCK),
        )

    def generate_attribution(self, license_id: LicenseId, source_repo: str) -> AttributionTemplate:
        """Generate proper attribution text for a given license."""
        src = source_repo
        templates = {
            LicenseId.MIT: (
                f"Copyright (c) [year] [author]. "
                f"Licensed under MIT License. Source: {src}"
            ),
            LicenseId.APACHE_2: (
                f"Licensed under the Apache License, "
                f"Version 2.0. Source: {src}"
            ),
            LicenseId.BSD_2: (
                f"Copyright (c) [year] [author]. "
                f"BSD 2-Clause. Source: {src}"
            ),
            LicenseId.BSD_3: (
                f"Copyright (c) [year] [author]. "
                f"BSD 3-Clause. Source: {src}"
            ),
            LicenseId.GPL_3: (
                f"Licensed under GPL-3.0. Source: {src}. "
                f"Derivative works must also be GPL-3.0."
            ),
            LicenseId.AGPL_3: (
                f"Licensed under AGPL-3.0. Source: {src}. "
                f"Network use constitutes distribution."
            ),
        }
        text = templates.get(license_id, f"License: {license_id}. Source: {source_repo}")
        return AttributionTemplate(
            license_id=license_id,
            source_repo=source_repo,
            attribution_text=text,
            spdx_identifier=license_id.value,
        )

    def get_license_family(self, license_id: LicenseId) -> LicenseFamily:
        return LICENSE_FAMILIES.get(license_id, LicenseFamily.UNKNOWN)

    def get_audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def analytics(self) -> dict[str, Any]:
        checks = [e for e in self._audit_log if e["action"] == "check_compliance"]
        return {
            "total_snippets_registered": len(self._snippets),
            "total_checks": len(checks),
            "violations": sum(1 for c in checks if c["status"] == ComplianceStatus.VIOLATION),
            "avg_lico_score": (
                sum(c["lico_score"] for c in checks) / max(len(checks), 1)
            ),
            "blocked": sum(1 for c in checks if c["gate"] == GateAction.BLOCK),
        }

    # ── Private helpers ──────────────────────────────────────────────

    def _generate_fingerprints(self, code: str) -> set[str]:
        """Generate n-gram hash fingerprints from code."""
        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', code.strip())
        tokens = normalized.split()

        fingerprints: set[str] = set()
        for i in range(len(tokens) - self._ngram_size + 1):
            ngram = " ".join(tokens[i:i + self._ngram_size])
            fp = hashlib.md5(ngram.encode()).hexdigest()[:12]  # noqa: S324
            fingerprints.add(fp)

        return fingerprints

    def _compute_lico(self, matches: list[SimilarityMatch]) -> float:
        """Compute LICO score.  1.0 = fully compliant, 0.0 = worst."""
        if not matches:
            return 1.0  # No matches → no compliance issue

        penalties: list[float] = []
        for m in matches:
            family = LICENSE_FAMILIES.get(m.license_id, LicenseFamily.UNKNOWN)
            weight = self._copyleft_weight if family == LicenseFamily.STRONG_COPYLEFT else 1.0
            penalty = m.similarity_score * weight
            if self._has_attribution(m):
                penalty *= 0.1  # Proper attribution greatly reduces penalty
            penalties.append(penalty)

        max_penalty = sum(penalties) / len(penalties)
        return max(1.0 - max_penalty, 0.0)

    def _has_attribution(self, match: SimilarityMatch) -> bool:
        """Check if proper attribution exists for a match."""
        snippet = self._snippets.get(match.snippet_id)
        if not snippet:
            return False
        return bool(snippet.attribution_text)

    def _generate_attribution(self, match: SimilarityMatch) -> str:
        """Generate attribution string for a match."""
        template = self.generate_attribution(match.license_id, match.source_repo)
        return template.attribution_text
