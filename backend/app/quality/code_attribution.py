"""Code Attribution Tracker -- provenance tracking for AI vs human code.

Tracks which portions of code were AI-generated vs. human-written,
recording model, confidence, prompt context, and review status.
Supports compliance reporting and IP governance.

Key features:
- Per-file and per-function attribution records
- Confidence-level tracking (auto-generated, assisted, human-reviewed)
- Model and prompt hash recording for reproducibility
- Attribution report generation per project/ticket
- License risk flagging based on training data concerns
- Human review status tracking for compliance
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class AuthorshipType(StrEnum):
    AI_GENERATED = "ai_generated"
    AI_ASSISTED = "ai_assisted"
    HUMAN_WRITTEN = "human_written"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    HUMAN_REVIEWED = "human_reviewed"
    AUTO_REVIEWED = "auto_reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class LicenseRisk(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass
class AttributionRecord:
    """Attribution metadata for a code unit."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_path: str = ""
    function_name: str | None = None
    line_start: int = 0
    line_end: int = 0
    authorship: AuthorshipType = AuthorshipType.UNKNOWN
    model_id: str | None = None
    model_provider: str | None = None
    prompt_hash: str | None = None
    confidence: float = 0.0  # 0.0-1.0 confidence this is correct
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    reviewer: str | None = None
    ticket_id: str | None = None
    project_id: str | None = None
    license_risk: LicenseRisk = LicenseRisk.NONE
    content_hash: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reviewed_at: datetime | None = None
    tags: dict = field(default_factory=dict)


@dataclass
class AttributionSummary:
    """Summary of code attribution for a project or ticket."""

    total_files: int = 0
    total_records: int = 0
    ai_generated_count: int = 0
    ai_assisted_count: int = 0
    human_written_count: int = 0
    mixed_count: int = 0
    unknown_count: int = 0
    reviewed_count: int = 0
    unreviewed_count: int = 0
    high_risk_count: int = 0
    avg_confidence: float = 0.0
    ai_percentage: float = 0.0
    models_used: list[str] = field(default_factory=list)


@dataclass
class ComplianceReport:
    """Compliance report for AI code attribution."""

    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    project_id: str = ""
    summary: AttributionSummary = field(default_factory=AttributionSummary)
    high_risk_records: list[AttributionRecord] = field(default_factory=list)
    unreviewed_records: list[AttributionRecord] = field(default_factory=list)
    compliant: bool = True
    issues: list[str] = field(default_factory=list)


# ── Attribution Tracker ──────────────────────────────────────────────────

class CodeAttributionTracker:
    """Tracks and reports on code authorship (AI vs. human)."""

    def __init__(self):
        self._records: list[AttributionRecord] = []

    # ── Recording ───────────────────────────────────────────────────

    def record(
        self,
        file_path: str,
        authorship: AuthorshipType,
        line_start: int = 0,
        line_end: int = 0,
        function_name: str | None = None,
        model_id: str | None = None,
        model_provider: str | None = None,
        prompt_hash: str | None = None,
        confidence: float = 1.0,
        ticket_id: str | None = None,
        project_id: str | None = None,
        content: str | None = None,
        tags: dict | None = None,
    ) -> AttributionRecord:
        """Record authorship attribution for a code unit."""
        content_hash = ""
        if content:
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Assess license risk
        license_risk = self._assess_license_risk(
            authorship, model_id, content
        )

        record = AttributionRecord(
            file_path=file_path,
            function_name=function_name,
            line_start=line_start,
            line_end=line_end,
            authorship=authorship,
            model_id=model_id,
            model_provider=model_provider,
            prompt_hash=prompt_hash,
            confidence=confidence,
            ticket_id=ticket_id,
            project_id=project_id,
            license_risk=license_risk,
            content_hash=content_hash,
            tags=tags or {},
        )
        self._records.append(record)
        logger.debug(
            "Attribution: %s %s (%s, confidence=%.2f, risk=%s)",
            file_path,
            function_name or "",
            authorship,
            confidence,
            license_risk,
        )
        return record

    def mark_reviewed(
        self,
        record_id: str,
        reviewer: str,
        status: ReviewStatus = ReviewStatus.HUMAN_REVIEWED,
    ) -> bool:
        """Mark an attribution record as reviewed."""
        rec = next(
            (r for r in self._records if r.id == record_id), None
        )
        if not rec:
            return False
        rec.review_status = status
        rec.reviewer = reviewer
        rec.reviewed_at = datetime.now(UTC)
        return True

    # ── Queries ─────────────────────────────────────────────────────

    def by_file(self, file_path: str) -> list[AttributionRecord]:
        """Get all records for a specific file."""
        return [r for r in self._records if r.file_path == file_path]

    def by_ticket(self, ticket_id: str) -> list[AttributionRecord]:
        """Get all records for a specific ticket."""
        return [r for r in self._records if r.ticket_id == ticket_id]

    def by_project(self, project_id: str) -> list[AttributionRecord]:
        """Get all records for a specific project."""
        return [r for r in self._records if r.project_id == project_id]

    def unreviewed(self) -> list[AttributionRecord]:
        """Get all unreviewed AI-generated records."""
        return [
            r for r in self._records
            if r.authorship in (
                AuthorshipType.AI_GENERATED,
                AuthorshipType.AI_ASSISTED,
            )
            and r.review_status == ReviewStatus.UNREVIEWED
        ]

    def high_risk(self) -> list[AttributionRecord]:
        """Get records with high license risk."""
        return [
            r for r in self._records
            if r.license_risk in (LicenseRisk.HIGH, LicenseRisk.MEDIUM)
        ]

    # ── Summary ─────────────────────────────────────────────────────

    def summary(
        self,
        project_id: str | None = None,
        ticket_id: str | None = None,
    ) -> AttributionSummary:
        """Generate attribution summary."""
        records = self._records
        if project_id:
            records = [r for r in records if r.project_id == project_id]
        if ticket_id:
            records = [r for r in records if r.ticket_id == ticket_id]

        if not records:
            return AttributionSummary()

        files = set(r.file_path for r in records)
        models = set(
            r.model_id for r in records
            if r.model_id is not None
        )
        ai_gen = sum(
            1 for r in records
            if r.authorship == AuthorshipType.AI_GENERATED
        )
        ai_assist = sum(
            1 for r in records
            if r.authorship == AuthorshipType.AI_ASSISTED
        )
        human = sum(
            1 for r in records
            if r.authorship == AuthorshipType.HUMAN_WRITTEN
        )
        mixed = sum(
            1 for r in records
            if r.authorship == AuthorshipType.MIXED
        )
        unknown = sum(
            1 for r in records
            if r.authorship == AuthorshipType.UNKNOWN
        )
        reviewed = sum(
            1 for r in records
            if r.review_status != ReviewStatus.UNREVIEWED
        )
        high_risk = sum(
            1 for r in records
            if r.license_risk in (LicenseRisk.HIGH, LicenseRisk.MEDIUM)
        )
        total = len(records)
        ai_total = ai_gen + ai_assist

        return AttributionSummary(
            total_files=len(files),
            total_records=total,
            ai_generated_count=ai_gen,
            ai_assisted_count=ai_assist,
            human_written_count=human,
            mixed_count=mixed,
            unknown_count=unknown,
            reviewed_count=reviewed,
            unreviewed_count=total - reviewed,
            high_risk_count=high_risk,
            avg_confidence=round(
                sum(r.confidence for r in records) / total, 3
            ),
            ai_percentage=round(ai_total / total * 100, 1) if total else 0,
            models_used=sorted(models),
        )

    # ── Compliance ──────────────────────────────────────────────────

    def compliance_report(
        self,
        project_id: str,
        require_review: bool = True,
        max_ai_percentage: float = 100.0,
    ) -> ComplianceReport:
        """Generate a compliance report for a project."""
        records = self.by_project(project_id)
        s = self.summary(project_id=project_id)
        issues: list[str] = []
        compliant = True

        hr = [
            r for r in records
            if r.license_risk in (LicenseRisk.HIGH, LicenseRisk.MEDIUM)
        ]
        unrev = [
            r for r in records
            if r.authorship in (
                AuthorshipType.AI_GENERATED,
                AuthorshipType.AI_ASSISTED,
            )
            and r.review_status == ReviewStatus.UNREVIEWED
        ]

        if require_review and unrev:
            compliant = False
            issues.append(
                f"{len(unrev)} AI-generated code units lack human review"
            )

        if s.ai_percentage > max_ai_percentage:
            compliant = False
            issues.append(
                f"AI code percentage ({s.ai_percentage}%) exceeds "
                f"maximum ({max_ai_percentage}%)"
            )

        if hr:
            compliant = False
            issues.append(
                f"{len(hr)} code units have medium/high license risk"
            )

        return ComplianceReport(
            project_id=project_id,
            summary=s,
            high_risk_records=hr,
            unreviewed_records=unrev,
            compliant=compliant,
            issues=issues,
        )

    # ── License risk assessment ─────────────────────────────────────

    @staticmethod
    def _assess_license_risk(
        authorship: AuthorshipType,
        model_id: str | None,
        content: str | None,
    ) -> LicenseRisk:
        """Assess license risk based on authorship and content."""
        if authorship == AuthorshipType.HUMAN_WRITTEN:
            return LicenseRisk.NONE

        if authorship == AuthorshipType.UNKNOWN:
            return LicenseRisk.MEDIUM

        # Check content for license markers
        if content:
            lower = content.lower()
            high_risk_markers = [
                "copyright", "all rights reserved",
                "gpl", "agpl", "proprietary",
            ]
            medium_risk_markers = [
                "license", "spdx", "lgpl", "mpl",
            ]
            for marker in high_risk_markers:
                if marker in lower:
                    return LicenseRisk.HIGH
            for marker in medium_risk_markers:
                if marker in lower:
                    return LicenseRisk.MEDIUM

        # Older models have higher risk (larger training data overlap)
        if model_id and any(
            old in (model_id or "")
            for old in ["gpt-3", "codex", "code-davinci"]
        ):
            return LicenseRisk.MEDIUM

        return LicenseRisk.LOW

    # ── Stats ───────────────────────────────────────────────────────

    @property
    def record_count(self) -> int:
        return len(self._records)

    def clear(self):
        """Clear all records."""
        self._records.clear()
