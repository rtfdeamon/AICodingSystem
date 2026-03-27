"""Agent Entropy Collector — detect and reduce accumulated cruft in
long-running AI agent sessions.

Long-running agent sessions accumulate "entropy": stale context, orphaned
variables, contradictory state, and redundant instructions that degrade
output quality over time. Harness Engineering (2026) prescribes periodic
"garbage collection" to prune this entropy.

Based on agent-engineering.dev "Harness Engineering in 2026: The Discipline
That Makes AI Agents Production-Ready" and OpenAI internal experiments
on agent session entropy management (2025-2026).

Key capabilities:
- Session state tracking: monitor context size, variable staleness, instruction count
- Entropy scoring: composite metric of context bloat, staleness, and contradiction
- Contradiction detection: find conflicting instructions in context
- Stale reference detection: identify variables/refs not used recently
- Pruning recommendations: suggest what to remove from context
- Auto-compaction: merge and deduplicate similar context entries
- Quality gate: configurable entropy thresholds
- Batch analysis across multiple agent sessions
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

class EntropySeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EntropyType(StrEnum):
    CONTEXT_BLOAT = "context_bloat"
    STALE_REFERENCE = "stale_reference"
    CONTRADICTION = "contradiction"
    DUPLICATION = "duplication"
    ORPHANED_STATE = "orphaned_state"
    INSTRUCTION_OVERLOAD = "instruction_overload"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    COMPACT = "compact"  # Session needs compaction


class PruneAction(StrEnum):
    REMOVE = "remove"
    MERGE = "merge"
    ARCHIVE = "archive"
    REFRESH = "refresh"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class ContextEntry:
    """A single entry in the agent's context/memory."""

    id: str
    content: str
    entry_type: str = "instruction"  # instruction, variable, fact, reference
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    last_accessed: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    access_count: int = 0
    tokens_estimate: int = 0


@dataclass
class EntropyFinding:
    """A single entropy finding."""

    id: str
    entropy_type: EntropyType
    severity: EntropySeverity
    description: str
    affected_entries: list[str]  # entry IDs
    recommended_action: PruneAction
    entropy_contribution: float  # 0-1, how much this adds to total entropy


@dataclass
class PruneRecommendation:
    """Recommendation for pruning a context entry."""

    entry_id: str
    action: PruneAction
    reason: str
    entropy_reduction: float  # how much entropy this would reduce
    merge_target: str | None = None  # for MERGE actions


@dataclass
class SessionEntropyReport:
    """Entropy analysis for a single agent session."""

    session_id: str
    findings: list[EntropyFinding]
    prune_recommendations: list[PruneRecommendation]
    total_entries: int
    total_tokens: int
    unique_content_ratio: float  # 0-1, lower = more duplication
    stale_ratio: float  # fraction of stale entries
    entropy_score: float  # 0-1
    severity: EntropySeverity
    gate_decision: GateDecision
    analyzed_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )


@dataclass
class BatchEntropyReport:
    """Report across multiple sessions."""

    reports: list[SessionEntropyReport]
    total_sessions: int
    avg_entropy: float
    sessions_needing_compaction: int
    gate_decision: GateDecision


# ── Main class ──────────────────────────────────────────────────────────

class AgentEntropyCollector:
    """Detect and reduce entropy in agent sessions.

    Analyzes context entries for bloat, staleness, contradictions,
    and duplication. Produces actionable pruning recommendations.
    """

    def __init__(
        self,
        max_context_tokens: int = 100_000,
        stale_threshold_accesses: int = 0,
        bloat_threshold: float = 0.7,  # % of max tokens
        duplication_threshold: float = 0.85,  # similarity threshold
        warn_entropy: float = 0.4,
        compact_entropy: float = 0.7,
    ) -> None:
        self.max_context_tokens = max_context_tokens
        self.stale_threshold_accesses = stale_threshold_accesses
        self.bloat_threshold = bloat_threshold
        self.duplication_threshold = duplication_threshold
        self.warn_entropy = warn_entropy
        self.compact_entropy = compact_entropy
        self._history: list[SessionEntropyReport] = []

    # ── Content fingerprinting ──────────────────────────────────────────

    @staticmethod
    def _fingerprint(text: str) -> str:
        """Create content fingerprint for deduplication."""
        normalized = " ".join(text.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """Simple word-overlap similarity between two texts."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate (~4 chars per token)."""
        return max(len(text) // 4, 1)

    # ── Analysis ────────────────────────────────────────────────────────

    def analyze(
        self,
        session_id: str,
        entries: list[ContextEntry],
    ) -> SessionEntropyReport:
        """Analyze a session's context entries for entropy."""
        if not entries:
            report = SessionEntropyReport(
                session_id=session_id,
                findings=[],
                prune_recommendations=[],
                total_entries=0,
                total_tokens=0,
                unique_content_ratio=1.0,
                stale_ratio=0.0,
                entropy_score=0.0,
                severity=EntropySeverity.LOW,
                gate_decision=GateDecision.PASS,
            )
            self._history.append(report)
            return report

        # Compute token estimates
        for e in entries:
            if e.tokens_estimate == 0:
                e.tokens_estimate = self._estimate_tokens(e.content)

        total_tokens = sum(e.tokens_estimate for e in entries)
        findings: list[EntropyFinding] = []
        recommendations: list[PruneRecommendation] = []

        # 1. Context bloat
        bloat_finding = self._check_bloat(entries, total_tokens)
        if bloat_finding:
            findings.append(bloat_finding)

        # 2. Duplication
        dup_findings, dup_recs = self._check_duplication(entries)
        findings.extend(dup_findings)
        recommendations.extend(dup_recs)

        # 3. Stale references
        stale_findings, stale_recs = self._check_staleness(entries)
        findings.extend(stale_findings)
        recommendations.extend(stale_recs)

        # 4. Contradictions
        contra_findings = self._check_contradictions(entries)
        findings.extend(contra_findings)

        # 5. Instruction overload
        overload_finding = self._check_instruction_overload(entries)
        if overload_finding:
            findings.append(overload_finding)

        # Compute metrics
        fingerprints = {self._fingerprint(e.content) for e in entries}
        unique_ratio = len(fingerprints) / len(entries) if entries else 1.0

        stale_count = sum(
            1 for e in entries
            if e.access_count <= self.stale_threshold_accesses
        )
        stale_ratio = stale_count / len(entries) if entries else 0.0

        # Entropy score
        bloat_component = min(total_tokens / self.max_context_tokens, 1.0)
        dup_component = 1.0 - unique_ratio
        stale_component = stale_ratio
        findings_component = min(len(findings) / 10.0, 1.0)

        entropy_score = round(
            0.3 * bloat_component
            + 0.25 * dup_component
            + 0.25 * stale_component
            + 0.2 * findings_component,
            4,
        )

        # Severity and gate
        if entropy_score >= self.compact_entropy:
            severity = EntropySeverity.CRITICAL
            gate = GateDecision.COMPACT
        elif entropy_score >= self.warn_entropy:
            severity = EntropySeverity.HIGH
            gate = GateDecision.WARN
        elif entropy_score >= 0.2:
            severity = EntropySeverity.MEDIUM
            gate = GateDecision.PASS
        else:
            severity = EntropySeverity.LOW
            gate = GateDecision.PASS

        report = SessionEntropyReport(
            session_id=session_id,
            findings=findings,
            prune_recommendations=recommendations,
            total_entries=len(entries),
            total_tokens=total_tokens,
            unique_content_ratio=round(unique_ratio, 4),
            stale_ratio=round(stale_ratio, 4),
            entropy_score=entropy_score,
            severity=severity,
            gate_decision=gate,
        )
        self._history.append(report)
        return report

    def _check_bloat(
        self,
        entries: list[ContextEntry],
        total_tokens: int,
    ) -> EntropyFinding | None:
        """Check for context token bloat."""
        ratio = total_tokens / self.max_context_tokens
        if ratio >= self.bloat_threshold:
            # Find largest entries for recommendation
            sorted_entries = sorted(entries, key=lambda e: e.tokens_estimate, reverse=True)
            largest_ids = [e.id for e in sorted_entries[:5]]
            return EntropyFinding(
                id=uuid.uuid4().hex[:12],
                entropy_type=EntropyType.CONTEXT_BLOAT,
                severity=EntropySeverity.HIGH if ratio >= 0.9 else EntropySeverity.MEDIUM,
                description=(
                    f"Context uses {ratio:.0%} of max tokens "
                    f"({total_tokens}/{self.max_context_tokens})"
                ),
                affected_entries=largest_ids,
                recommended_action=PruneAction.ARCHIVE,
                entropy_contribution=min(ratio - self.bloat_threshold, 0.3),
            )
        return None

    def _check_duplication(
        self,
        entries: list[ContextEntry],
    ) -> tuple[list[EntropyFinding], list[PruneRecommendation]]:
        """Check for duplicate/near-duplicate entries."""
        findings: list[EntropyFinding] = []
        recommendations: list[PruneRecommendation] = []
        seen: dict[str, str] = {}  # fingerprint → entry_id

        for entry in entries:
            fp = self._fingerprint(entry.content)
            if fp in seen:
                findings.append(EntropyFinding(
                    id=uuid.uuid4().hex[:12],
                    entropy_type=EntropyType.DUPLICATION,
                    severity=EntropySeverity.MEDIUM,
                    description=f"Entry '{entry.id}' duplicates '{seen[fp]}'",
                    affected_entries=[entry.id, seen[fp]],
                    recommended_action=PruneAction.REMOVE,
                    entropy_contribution=0.1,
                ))
                recommendations.append(PruneRecommendation(
                    entry_id=entry.id,
                    action=PruneAction.REMOVE,
                    reason=f"Exact duplicate of {seen[fp]}",
                    entropy_reduction=0.1,
                ))
            else:
                seen[fp] = entry.id

        # Check near-duplicates
        entry_list = list(entries)
        for i in range(len(entry_list)):
            for j in range(i + 1, min(i + 20, len(entry_list))):
                fp_i = self._fingerprint(entry_list[i].content)
                fp_j = self._fingerprint(entry_list[j].content)
                if fp_i == fp_j:
                    continue
                sim = self._similarity(entry_list[i].content, entry_list[j].content)
                if sim >= self.duplication_threshold:
                    findings.append(EntropyFinding(
                        id=uuid.uuid4().hex[:12],
                        entropy_type=EntropyType.DUPLICATION,
                        severity=EntropySeverity.LOW,
                        description=(
                            f"Entries '{entry_list[i].id}' and '{entry_list[j].id}' "
                            f"are {sim:.0%} similar"
                        ),
                        affected_entries=[entry_list[i].id, entry_list[j].id],
                        recommended_action=PruneAction.MERGE,
                        entropy_contribution=0.05,
                    ))
                    recommendations.append(PruneRecommendation(
                        entry_id=entry_list[j].id,
                        action=PruneAction.MERGE,
                        reason=f"Near-duplicate of {entry_list[i].id} ({sim:.0%} similar)",
                        entropy_reduction=0.05,
                        merge_target=entry_list[i].id,
                    ))

        return findings, recommendations

    def _check_staleness(
        self,
        entries: list[ContextEntry],
    ) -> tuple[list[EntropyFinding], list[PruneRecommendation]]:
        """Check for stale context entries."""
        findings: list[EntropyFinding] = []
        recommendations: list[PruneRecommendation] = []

        stale = [e for e in entries if e.access_count <= self.stale_threshold_accesses]
        if len(stale) >= 3:
            stale_ids = [e.id for e in stale]
            findings.append(EntropyFinding(
                id=uuid.uuid4().hex[:12],
                entropy_type=EntropyType.STALE_REFERENCE,
                severity=EntropySeverity.MEDIUM,
                description=f"{len(stale)} entries have never been accessed",
                affected_entries=stale_ids[:10],
                recommended_action=PruneAction.ARCHIVE,
                entropy_contribution=min(len(stale) * 0.03, 0.3),
            ))
            for e in stale:
                recommendations.append(PruneRecommendation(
                    entry_id=e.id,
                    action=PruneAction.ARCHIVE,
                    reason=f"Never accessed (access_count={e.access_count})",
                    entropy_reduction=0.02,
                ))

        return findings, recommendations

    def _check_contradictions(
        self,
        entries: list[ContextEntry],
    ) -> list[EntropyFinding]:
        """Check for contradictory instructions."""
        findings: list[EntropyFinding] = []

        # Simple heuristic: look for negation patterns
        instructions = [e for e in entries if e.entry_type == "instruction"]
        for i, e1 in enumerate(instructions):
            for e2 in instructions[i + 1:]:
                if self._are_contradictory(e1.content, e2.content):
                    findings.append(EntropyFinding(
                        id=uuid.uuid4().hex[:12],
                        entropy_type=EntropyType.CONTRADICTION,
                        severity=EntropySeverity.HIGH,
                        description=f"Entries '{e1.id}' and '{e2.id}' may contradict each other",
                        affected_entries=[e1.id, e2.id],
                        recommended_action=PruneAction.REFRESH,
                        entropy_contribution=0.15,
                    ))

        return findings

    @staticmethod
    def _are_contradictory(text1: str, text2: str) -> bool:
        """Simple heuristic for contradiction detection."""
        t1 = text1.lower()
        t2 = text2.lower()

        negation_pairs = [
            ("always", "never"),
            ("enable", "disable"),
            ("allow", "block"),
            ("include", "exclude"),
            ("must", "must not"),
            ("do ", "do not"),
            ("use", "avoid"),
            ("add", "remove"),
        ]
        for pos, neg in negation_pairs:
            if (pos in t1 and neg in t2) or (neg in t1 and pos in t2):
                # Check if they share a common topic word
                stop = {"always", "never", "must", "not", "do", "the", "a", "an"}
                words1 = set(t1.split()) - stop
                words2 = set(t2.split()) - stop
                overlap = words1 & words2
                if len(overlap) >= 2:
                    return True
        return False

    def _check_instruction_overload(
        self,
        entries: list[ContextEntry],
    ) -> EntropyFinding | None:
        """Check for too many instructions."""
        instructions = [e for e in entries if e.entry_type == "instruction"]
        if len(instructions) > 50:
            return EntropyFinding(
                id=uuid.uuid4().hex[:12],
                entropy_type=EntropyType.INSTRUCTION_OVERLOAD,
                severity=EntropySeverity.HIGH,
                description=f"Session has {len(instructions)} instructions (recommended <50)",
                affected_entries=[e.id for e in instructions[-10:]],
                recommended_action=PruneAction.MERGE,
                entropy_contribution=min((len(instructions) - 50) * 0.01, 0.3),
            )
        return None

    # ── Batch ───────────────────────────────────────────────────────────

    def batch_analyze(
        self,
        sessions: list[tuple[str, list[ContextEntry]]],
    ) -> BatchEntropyReport:
        """Analyze entropy across multiple sessions."""
        reports = [self.analyze(sid, entries) for sid, entries in sessions]
        avg = (
            sum(r.entropy_score for r in reports) / len(reports)
            if reports else 0.0
        )
        compactions = sum(1 for r in reports if r.gate_decision == GateDecision.COMPACT)

        gates = [r.gate_decision for r in reports]
        if GateDecision.COMPACT in gates:
            gate = GateDecision.COMPACT
        elif GateDecision.WARN in gates:
            gate = GateDecision.WARN
        else:
            gate = GateDecision.PASS

        return BatchEntropyReport(
            reports=reports,
            total_sessions=len(reports),
            avg_entropy=round(avg, 4),
            sessions_needing_compaction=compactions,
            gate_decision=gate,
        )

    @property
    def history(self) -> list[SessionEntropyReport]:
        return list(self._history)
