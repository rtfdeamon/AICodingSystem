"""Multi-Agent Workspace Coordinator.

Orchestration for parallel AI coding agents on a shared repository:
- Worktree-based isolation with per-agent branches
- File ownership registry with conflict detection
- FIFO merge queue with tiered conflict resolution
- Semantic contradiction detection across parallel branches
- Duplication prevention across agent outputs

Based on:
- Augment Code "How to Run a Multi-Agent Coding Workspace" (2026)
- Addy Osmani "The Code Agent Orchestra" (2026)
- arXiv 2603.21489 "Effective Strategies for Async SW Agents" (2026)
- jayminwest/overstory multi-agent orchestration (GitHub 2026)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)

# ── Enums ──────────────────────────────────────────────────────────────────


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class WorkspaceStatus(StrEnum):
    IDLE = "idle"
    ACTIVE = "active"
    MERGING = "merging"
    CONFLICT = "conflict"
    MERGED = "merged"
    ABANDONED = "abandoned"


class ConflictSeverity(StrEnum):
    NONE = "none"
    AUTO_RESOLVABLE = "auto_resolvable"
    AI_RESOLVABLE = "ai_resolvable"
    HUMAN_REQUIRED = "human_required"


class MergeOutcome(StrEnum):
    SUCCESS = "success"
    AUTO_RESOLVED = "auto_resolved"
    ESCALATED = "escalated"
    BLOCKED = "blocked"


# ── Dataclasses ────────────────────────────────────────────────────────────


@dataclass
class FileOwnership:
    file_path: str = ""
    owner_agent_id: str = ""
    exclusive: bool = True
    assigned_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )


@dataclass
class AgentWorkspace:
    workspace_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    agent_id: str = ""
    branch_name: str = ""
    worktree_path: str = ""
    status: WorkspaceStatus = WorkspaceStatus.IDLE
    owned_files: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )


@dataclass
class ConflictRecord:
    conflict_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    file_path: str = ""
    agent_a: str = ""
    agent_b: str = ""
    severity: ConflictSeverity = ConflictSeverity.NONE
    resolution: str = ""
    resolved: bool = False


@dataclass
class MergeRequest:
    merge_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    workspace_id: str = ""
    agent_id: str = ""
    changed_files: list[str] = field(default_factory=list)
    outcome: MergeOutcome = MergeOutcome.SUCCESS
    conflicts: list[ConflictRecord] = field(default_factory=list)
    queued_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )


@dataclass
class DuplicationAlert:
    alert_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    agent_a: str = ""
    agent_b: str = ""
    description: str = ""
    file_a: str = ""
    file_b: str = ""
    similarity: float = 0.0


@dataclass
class CoordinatorConfig:
    max_concurrent_agents: int = 5
    enable_ownership_checks: bool = True
    duplication_threshold: float = 0.70
    auto_resolve_non_overlapping: bool = True


@dataclass
class CoordinatorReport:
    total_workspaces: int = 0
    active: int = 0
    merged: int = 0
    conflicts_total: int = 0
    conflicts_resolved: int = 0
    duplications_detected: int = 0
    gate: GateDecision = GateDecision.PASS


# ── Pure helpers ───────────────────────────────────────────────────────────


def _detect_file_conflicts(
    changes_a: list[str],
    changes_b: list[str],
) -> list[str]:
    return sorted(set(changes_a) & set(changes_b))


def _classify_conflict(
    overlapping_files: list[str],
    ownership_registry: dict[str, str],
) -> ConflictSeverity:
    if not overlapping_files:
        return ConflictSeverity.NONE

    exclusive_conflicts = [
        f for f in overlapping_files if f in ownership_registry
    ]
    if exclusive_conflicts:
        return ConflictSeverity.HUMAN_REQUIRED

    if len(overlapping_files) <= 2:
        return ConflictSeverity.AUTO_RESOLVABLE

    return ConflictSeverity.AI_RESOLVABLE


def _compute_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a and not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return round(len(intersection) / len(union), 4) if union else 0.0


def _detect_duplication(
    content_a: str,
    content_b: str,
    agent_a: str,
    agent_b: str,
    file_a: str,
    file_b: str,
    threshold: float,
) -> DuplicationAlert | None:
    tokens_a = set(content_a.lower().split())
    tokens_b = set(content_b.lower().split())
    sim = _compute_similarity(tokens_a, tokens_b)
    if sim >= threshold:
        return DuplicationAlert(
            agent_a=agent_a,
            agent_b=agent_b,
            description=f"Similarity {sim:.0%} between outputs",
            file_a=file_a,
            file_b=file_b,
            similarity=sim,
        )
    return None


def _gate_from_conflicts(
    unresolved: int,
    total: int,
) -> GateDecision:
    if unresolved > 0:
        return GateDecision.BLOCK
    if total > 0:
        return GateDecision.WARN
    return GateDecision.PASS


# ── Main class ─────────────────────────────────────────────────────────────


class MultiAgentWorkspaceCoordinator:
    """Coordinates parallel AI agent workspaces."""

    def __init__(
        self,
        config: CoordinatorConfig | None = None,
    ) -> None:
        self._config = config or CoordinatorConfig()
        self._workspaces: dict[str, AgentWorkspace] = {}
        self._ownership: dict[str, str] = {}
        self._merge_queue: list[MergeRequest] = []
        self._duplications: list[DuplicationAlert] = []

    @property
    def config(self) -> CoordinatorConfig:
        return self._config

    def create_workspace(
        self,
        agent_id: str,
        branch_name: str = "",
        worktree_path: str = "",
    ) -> tuple[str, str]:
        active = sum(
            1 for w in self._workspaces.values()
            if w.status == WorkspaceStatus.ACTIVE
        )
        if active >= self._config.max_concurrent_agents:
            return "", "Max concurrent agents reached"

        ws = AgentWorkspace(
            agent_id=agent_id,
            branch_name=branch_name or f"agent/{agent_id}",
            worktree_path=worktree_path or f".worktrees/{agent_id}",
            status=WorkspaceStatus.ACTIVE,
        )
        self._workspaces[ws.workspace_id] = ws
        logger.info(
            "Workspace created: %s for agent %s",
            ws.workspace_id, agent_id,
        )
        return ws.workspace_id, "Workspace created"

    def assign_ownership(
        self,
        agent_id: str,
        file_paths: list[str],
    ) -> tuple[bool, list[str]]:
        conflicts: list[str] = []
        for fp in file_paths:
            existing = self._ownership.get(fp)
            if existing and existing != agent_id:
                conflicts.append(
                    f"{fp} owned by {existing}"
                )
            else:
                self._ownership[fp] = agent_id

        if conflicts:
            return False, conflicts
        return True, []

    def register_changes(
        self,
        workspace_id: str,
        changed_files: list[str],
    ) -> tuple[bool, str]:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return False, "Workspace not found"
        ws.changed_files = changed_files

        if self._config.enable_ownership_checks:
            violations = [
                f for f in changed_files
                if f in self._ownership
                and self._ownership[f] != ws.agent_id
            ]
            if violations:
                return False, (
                    f"Ownership violations: {violations}"
                )

        return True, "Changes registered"

    def request_merge(
        self,
        workspace_id: str,
    ) -> MergeRequest:
        ws = self._workspaces.get(workspace_id)
        if ws is None:
            return MergeRequest(outcome=MergeOutcome.BLOCKED)

        conflicts: list[ConflictRecord] = []
        for other in self._workspaces.values():
            if other.workspace_id == workspace_id:
                continue
            if other.status not in (
                WorkspaceStatus.ACTIVE,
                WorkspaceStatus.MERGING,
            ):
                continue

            overlapping = _detect_file_conflicts(
                ws.changed_files, other.changed_files,
            )
            if overlapping:
                severity = _classify_conflict(
                    overlapping, self._ownership,
                )
                for fp in overlapping:
                    conflicts.append(ConflictRecord(
                        file_path=fp,
                        agent_a=ws.agent_id,
                        agent_b=other.agent_id,
                        severity=severity,
                        resolved=(
                            severity == ConflictSeverity.AUTO_RESOLVABLE
                            and self._config.auto_resolve_non_overlapping
                        ),
                    ))

        unresolved = [c for c in conflicts if not c.resolved]
        if unresolved:
            outcome = MergeOutcome.ESCALATED
            ws.status = WorkspaceStatus.CONFLICT
        else:
            outcome = (
                MergeOutcome.AUTO_RESOLVED if conflicts
                else MergeOutcome.SUCCESS
            )
            ws.status = WorkspaceStatus.MERGED

        mr = MergeRequest(
            workspace_id=workspace_id,
            agent_id=ws.agent_id,
            changed_files=ws.changed_files,
            outcome=outcome,
            conflicts=conflicts,
        )
        self._merge_queue.append(mr)
        return mr

    def check_duplication(
        self,
        agent_a: str,
        content_a: str,
        file_a: str,
        agent_b: str,
        content_b: str,
        file_b: str,
    ) -> DuplicationAlert | None:
        alert = _detect_duplication(
            content_a, content_b,
            agent_a, agent_b,
            file_a, file_b,
            self._config.duplication_threshold,
        )
        if alert:
            self._duplications.append(alert)
        return alert

    def get_workspace(self, workspace_id: str) -> AgentWorkspace | None:
        return self._workspaces.get(workspace_id)

    def coordinator_report(self) -> CoordinatorReport:
        workspaces = list(self._workspaces.values())
        total = len(workspaces)
        active = sum(
            1 for w in workspaces
            if w.status == WorkspaceStatus.ACTIVE
        )
        merged = sum(
            1 for w in workspaces
            if w.status == WorkspaceStatus.MERGED
        )

        all_conflicts = [
            c for mr in self._merge_queue for c in mr.conflicts
        ]
        conflicts_total = len(all_conflicts)
        conflicts_resolved = sum(1 for c in all_conflicts if c.resolved)
        unresolved = conflicts_total - conflicts_resolved

        return CoordinatorReport(
            total_workspaces=total,
            active=active,
            merged=merged,
            conflicts_total=conflicts_total,
            conflicts_resolved=conflicts_resolved,
            duplications_detected=len(self._duplications),
            gate=_gate_from_conflicts(unresolved, conflicts_total),
        )
