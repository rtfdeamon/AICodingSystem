"""Output Watermark Tracker — AI-generated code provenance and attribution.

As AI agents generate more production code, tracking *which* code was
AI-generated vs human-written becomes critical for audit, liability,
compliance, and security review prioritization.  This module provides
lightweight watermarking and provenance tracking for AI-generated outputs.

Based on:
- Checkmarx "Top 12 AI Developer Tools" (2026)
- OpenSSF "Security-Focused Guide for AI Code Assistant Instructions" (2026)
- CodeScene "Agentic AI Coding: Best Practice Patterns" (2026)
- Stack Overflow "Are Bugs Inevitable with AI Coding Agents?" (2026)
- Fortune "AI Agent Reliability" / Narayanan & Kapoor (2026)

Key capabilities:
- Unique watermark generation per AI output (hash-based, non-intrusive)
- Provenance chain tracking: model → prompt → agent → output
- Code origin classification: ai_generated / human_written / ai_assisted / unknown
- Per-file and per-function attribution statistics
- Coverage report: what percentage of codebase is AI-generated
- Audit trail for compliance and security review prioritization
- Quality gate based on AI-coverage thresholds
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

class CodeOrigin(StrEnum):
    AI_GENERATED = "ai_generated"
    HUMAN_WRITTEN = "human_written"
    AI_ASSISTED = "ai_assisted"  # human-edited AI output
    UNKNOWN = "unknown"


class CoverageGrade(StrEnum):
    LOW = "low"  # <25% AI
    MODERATE = "moderate"  # 25-50% AI
    HIGH = "high"  # 50-75% AI
    DOMINANT = "dominant"  # >75% AI


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class Watermark:
    """Unique watermark for an AI-generated output."""

    watermark_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content_hash: str = ""
    model: str = ""
    agent: str = ""
    prompt_version: str = ""
    origin: CodeOrigin = CodeOrigin.AI_GENERATED
    file_path: str = ""
    function_name: str = ""
    line_start: int = 0
    line_end: int = 0
    line_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict = field(default_factory=dict)


@dataclass
class WatermarkConfig:
    """Configuration for watermark tracking."""

    high_ai_threshold: float = 0.50  # >50% AI → high
    dominant_ai_threshold: float = 0.75  # >75% → dominant
    require_review_above: float = 0.60  # require extra review
    max_ai_pct_per_file: float = 0.90  # warn if single file >90% AI


@dataclass
class FileAttribution:
    """Attribution summary for a single file."""

    file_path: str
    total_lines: int
    ai_generated_lines: int
    human_written_lines: int
    ai_assisted_lines: int
    unknown_lines: int
    ai_percentage: float
    watermarks: list[str]  # watermark IDs


@dataclass
class ProvenanceChain:
    """Full provenance chain for a piece of code."""

    watermark_id: str
    model: str
    agent: str
    prompt_version: str
    origin: CodeOrigin
    file_path: str
    function_name: str
    created_at: datetime


@dataclass
class CoverageReport:
    """AI code coverage report across the codebase."""

    total_files: int
    total_lines: int
    ai_generated_lines: int
    human_written_lines: int
    ai_assisted_lines: int
    ai_pct: float
    grade: CoverageGrade
    gate: GateDecision
    file_attributions: list[FileAttribution]
    high_ai_files: list[str]  # files with >threshold AI content
    models_used: list[str]
    agents_used: list[str]


@dataclass
class AuditEntry:
    """Single audit trail entry."""

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    watermark_id: str = ""
    action: str = ""  # "created", "modified", "reviewed", "approved"
    actor: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    notes: str = ""


# ── Pure helpers ─────────────────────────────────────────────────────────

def _hash_content(content: str) -> str:
    """Generate content hash for watermark."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _grade_coverage(ai_pct: float, config: WatermarkConfig) -> CoverageGrade:
    """Grade AI coverage level."""
    if ai_pct >= config.dominant_ai_threshold:
        return CoverageGrade.DOMINANT
    if ai_pct >= config.high_ai_threshold:
        return CoverageGrade.HIGH
    if ai_pct >= 0.25:
        return CoverageGrade.MODERATE
    return CoverageGrade.LOW


def _gate_from_coverage(ai_pct: float, config: WatermarkConfig) -> GateDecision:
    """Determine gate based on AI coverage."""
    if ai_pct >= config.require_review_above:
        return GateDecision.WARN
    return GateDecision.PASS


# ── Main class ───────────────────────────────────────────────────────────

class OutputWatermarkTracker:
    """Tracks AI-generated code provenance and attribution."""

    def __init__(self, config: WatermarkConfig | None = None) -> None:
        self._config = config or WatermarkConfig()
        self._watermarks: list[Watermark] = []
        self._audit_trail: list[AuditEntry] = []

    def create_watermark(
        self,
        content: str,
        model: str = "",
        agent: str = "",
        prompt_version: str = "",
        origin: CodeOrigin = CodeOrigin.AI_GENERATED,
        file_path: str = "",
        function_name: str = "",
        line_start: int = 0,
        line_end: int = 0,
        metadata: dict | None = None,
    ) -> Watermark:
        """Create a watermark for AI-generated content."""
        line_count = max(0, line_end - line_start + 1) if line_end >= line_start else 0
        wm = Watermark(
            content_hash=_hash_content(content),
            model=model,
            agent=agent,
            prompt_version=prompt_version,
            origin=origin,
            file_path=file_path,
            function_name=function_name,
            line_start=line_start,
            line_end=line_end,
            line_count=line_count,
            metadata=metadata or {},
        )
        self._watermarks.append(wm)

        # Audit trail
        self._audit_trail.append(AuditEntry(
            watermark_id=wm.watermark_id,
            action="created",
            actor=agent or "system",
            notes=f"model={model}, origin={origin}",
        ))

        return wm

    def mark_reviewed(self, watermark_id: str, reviewer: str, notes: str = "") -> AuditEntry:
        """Record that a watermarked output was reviewed."""
        entry = AuditEntry(
            watermark_id=watermark_id,
            action="reviewed",
            actor=reviewer,
            notes=notes,
        )
        self._audit_trail.append(entry)
        return entry

    def mark_modified(self, watermark_id: str, modifier: str) -> None:
        """Mark a watermarked output as human-modified (ai_assisted)."""
        for wm in self._watermarks:
            if wm.watermark_id == watermark_id:
                wm.origin = CodeOrigin.AI_ASSISTED
                break

        self._audit_trail.append(AuditEntry(
            watermark_id=watermark_id,
            action="modified",
            actor=modifier,
            notes="origin changed to ai_assisted",
        ))

    def get_provenance(self, watermark_id: str) -> ProvenanceChain | None:
        """Get full provenance chain for a watermark."""
        wm = next(
            (w for w in self._watermarks if w.watermark_id == watermark_id),
            None,
        )
        if wm is None:
            return None

        return ProvenanceChain(
            watermark_id=wm.watermark_id,
            model=wm.model,
            agent=wm.agent,
            prompt_version=wm.prompt_version,
            origin=wm.origin,
            file_path=wm.file_path,
            function_name=wm.function_name,
            created_at=wm.created_at,
        )

    def get_file_attribution(
        self, file_path: str, total_lines: int = 0,
    ) -> FileAttribution:
        """Get attribution summary for a file."""
        file_wms = [w for w in self._watermarks if w.file_path == file_path]

        ai_lines = sum(w.line_count for w in file_wms if w.origin == CodeOrigin.AI_GENERATED)
        assisted_lines = sum(w.line_count for w in file_wms if w.origin == CodeOrigin.AI_ASSISTED)
        known_lines = ai_lines + assisted_lines
        human_lines = max(0, total_lines - known_lines) if total_lines > 0 else 0
        unknown_lines = 0 if total_lines > 0 else 0
        effective_total = total_lines if total_lines > 0 else max(1, known_lines)

        ai_pct = (ai_lines + assisted_lines) / effective_total if effective_total > 0 else 0.0

        return FileAttribution(
            file_path=file_path,
            total_lines=total_lines,
            ai_generated_lines=ai_lines,
            human_written_lines=human_lines,
            ai_assisted_lines=assisted_lines,
            unknown_lines=unknown_lines,
            ai_percentage=round(ai_pct * 100, 2),
            watermarks=[w.watermark_id for w in file_wms],
        )

    def generate_coverage_report(
        self, file_line_counts: dict[str, int] | None = None,
    ) -> CoverageReport:
        """Generate AI code coverage report."""
        file_counts = file_line_counts or {}

        # Collect all files
        all_files = set(w.file_path for w in self._watermarks if w.file_path)
        all_files.update(file_counts.keys())

        file_attrs = []
        for fp in sorted(all_files):
            total = file_counts.get(fp, 0)
            attr = self.get_file_attribution(fp, total)
            file_attrs.append(attr)

        total_lines = sum(a.total_lines for a in file_attrs)
        ai_lines = sum(a.ai_generated_lines for a in file_attrs)
        human_lines = sum(a.human_written_lines for a in file_attrs)
        assisted_lines = sum(a.ai_assisted_lines for a in file_attrs)

        ai_pct = (ai_lines + assisted_lines) / total_lines if total_lines > 0 else 0.0

        grade = _grade_coverage(ai_pct, self._config)
        gate = _gate_from_coverage(ai_pct, self._config)

        high_ai_files = [
            a.file_path for a in file_attrs
            if a.ai_percentage > self._config.max_ai_pct_per_file * 100
        ]

        models = sorted({w.model for w in self._watermarks if w.model})
        agents = sorted({w.agent for w in self._watermarks if w.agent})

        return CoverageReport(
            total_files=len(all_files),
            total_lines=total_lines,
            ai_generated_lines=ai_lines,
            human_written_lines=human_lines,
            ai_assisted_lines=assisted_lines,
            ai_pct=round(ai_pct * 100, 2),
            grade=grade,
            gate=gate,
            file_attributions=file_attrs,
            high_ai_files=high_ai_files,
            models_used=models,
            agents_used=agents,
        )

    def get_audit_trail(self, watermark_id: str = "") -> list[AuditEntry]:
        """Get audit trail, optionally filtered by watermark."""
        if watermark_id:
            return [e for e in self._audit_trail if e.watermark_id == watermark_id]
        return list(self._audit_trail)
