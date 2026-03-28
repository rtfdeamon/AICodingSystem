"""Procedural Memory Learner.

Extracts, distils, and reuses successful coding patterns from agent trajectories:
- Trajectory-to-procedure extraction via semantic abstraction
- Bayesian reliability tracking for each procedure
- Contrastive refinement from success vs failure trajectories
- Canonical trajectory indexing for few-shot retrieval
- Procedure lifecycle management (creation, merging, deprecation)

Based on:
- arXiv 2512.18950 "MACLA - Hierarchical Procedural Memory" (AAMAS 2026)
- Microsoft Research CORPGEN for multi-horizon tasks (2026)
- arXiv "MemOS - A Memory Operating System for AI" (2026)
- arXiv 2508.06433 "Mem^p - Exploring Agent Procedural Memory" (2025)
"""

from __future__ import annotations

import hashlib
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


class ProcedureStatus(StrEnum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    DEPRECATED = "deprecated"
    MERGED = "merged"


class TrajectoryOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


# ── Dataclasses ────────────────────────────────────────────────────────────


@dataclass
class TrajectoryStep:
    step_idx: int = 0
    action: str = ""
    reasoning: str = ""
    tool_call: str = ""
    result: str = ""
    is_critical: bool = False
    duration_ms: float = 0.0


@dataclass
class Trajectory:
    trajectory_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    agent_id: str = ""
    task_type: str = ""
    steps: list[TrajectoryStep] = field(default_factory=list)
    outcome: TrajectoryOutcome = TrajectoryOutcome.SUCCESS
    quality_score: float = 0.0
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )


@dataclass
class Procedure:
    procedure_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    name: str = ""
    task_type: str = ""
    abstract_steps: list[str] = field(default_factory=list)
    critical_steps: list[int] = field(default_factory=list)
    source_trajectory_ids: list[str] = field(default_factory=list)
    status: ProcedureStatus = ProcedureStatus.CANDIDATE
    # Bayesian tracking
    success_count: int = 0
    failure_count: int = 0
    reliability: float = 0.5
    content_hash: str = ""
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )


@dataclass
class RetrievalResult:
    procedure: Procedure | None = None
    similarity: float = 0.0
    recommended: bool = False


@dataclass
class ContrastiveInsight:
    step_idx: int = 0
    success_pattern: str = ""
    failure_pattern: str = ""
    importance: float = 0.0


@dataclass
class LearnerConfig:
    min_trajectories_to_extract: int = 2
    reliability_threshold: float = 0.60
    deprecation_threshold: float = 0.30
    similarity_merge_threshold: float = 0.80
    bayesian_prior_alpha: float = 1.0
    bayesian_prior_beta: float = 1.0


@dataclass
class LearnerReport:
    total_procedures: int = 0
    active: int = 0
    deprecated: int = 0
    avg_reliability: float = 0.0
    total_trajectories_ingested: int = 0
    gate: GateDecision = GateDecision.PASS


# ── Pure helpers ───────────────────────────────────────────────────────────


def _procedure_hash(steps: list[str]) -> str:
    raw = "|".join(steps)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _bayesian_reliability(
    successes: int,
    failures: int,
    alpha: float = 1.0,
    beta: float = 1.0,
) -> float:
    return round(
        (successes + alpha) / (successes + failures + alpha + beta),
        4,
    )


def _extract_abstract_steps(trajectory: Trajectory) -> list[str]:
    steps: list[str] = []
    for s in trajectory.steps:
        abstract = s.action
        if s.tool_call:
            abstract = f"{s.action} via {s.tool_call}"
        steps.append(abstract)
    return steps


def _identify_critical_steps(
    success_trajs: list[Trajectory],
    failure_trajs: list[Trajectory],
) -> list[int]:
    if not success_trajs:
        return []

    max_steps = max(len(t.steps) for t in success_trajs)
    critical: list[int] = []

    for i in range(max_steps):
        success_actions = {
            t.steps[i].action
            for t in success_trajs
            if i < len(t.steps)
        }
        failure_actions = {
            t.steps[i].action
            for t in failure_trajs
            if i < len(t.steps)
        }
        if success_actions and success_actions != failure_actions:
            critical.append(i)

    return critical


def _contrastive_analysis(
    success_trajs: list[Trajectory],
    failure_trajs: list[Trajectory],
) -> list[ContrastiveInsight]:
    insights: list[ContrastiveInsight] = []
    if not success_trajs or not failure_trajs:
        return insights

    max_steps = max(
        max((len(t.steps) for t in success_trajs), default=0),
        max((len(t.steps) for t in failure_trajs), default=0),
    )

    for i in range(max_steps):
        s_actions = [
            t.steps[i].action
            for t in success_trajs
            if i < len(t.steps)
        ]
        f_actions = [
            t.steps[i].action
            for t in failure_trajs
            if i < len(t.steps)
        ]
        if not s_actions or not f_actions:
            continue

        s_set = set(s_actions)
        f_set = set(f_actions)
        if s_set != f_set:
            importance = 1.0 - (
                len(s_set & f_set) / len(s_set | f_set)
                if s_set | f_set else 0.0
            )
            insights.append(ContrastiveInsight(
                step_idx=i,
                success_pattern=", ".join(sorted(s_set)),
                failure_pattern=", ".join(sorted(f_set)),
                importance=round(importance, 3),
            ))

    return insights


def _step_similarity(steps_a: list[str], steps_b: list[str]) -> float:
    set_a = set(s.lower() for s in steps_a)
    set_b = set(s.lower() for s in steps_b)
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 0.0
    return round(len(set_a & set_b) / len(union), 4)


def _gate_from_reliability(avg: float, threshold: float) -> GateDecision:
    if avg >= threshold:
        return GateDecision.PASS
    if avg >= threshold * 0.7:
        return GateDecision.WARN
    return GateDecision.BLOCK


# ── Main class ─────────────────────────────────────────────────────────────


class ProceduralMemoryLearner:
    """Learns reusable procedures from agent execution trajectories."""

    def __init__(
        self,
        config: LearnerConfig | None = None,
    ) -> None:
        self._config = config or LearnerConfig()
        self._procedures: dict[str, Procedure] = {}
        self._trajectories: dict[str, list[Trajectory]] = {}

    @property
    def config(self) -> LearnerConfig:
        return self._config

    def ingest_trajectory(self, trajectory: Trajectory) -> str:
        key = trajectory.task_type
        if key not in self._trajectories:
            self._trajectories[key] = []
        self._trajectories[key].append(trajectory)
        logger.info(
            "Trajectory ingested: %s type=%s outcome=%s",
            trajectory.trajectory_id, key, trajectory.outcome,
        )
        return trajectory.trajectory_id

    def extract_procedure(self, task_type: str) -> Procedure | None:
        trajs = self._trajectories.get(task_type, [])
        successes = [
            t for t in trajs if t.outcome == TrajectoryOutcome.SUCCESS
        ]
        failures = [
            t for t in trajs if t.outcome == TrajectoryOutcome.FAILURE
        ]

        if len(successes) < self._config.min_trajectories_to_extract:
            return None

        best = max(successes, key=lambda t: t.quality_score)
        abstract_steps = _extract_abstract_steps(best)
        critical = _identify_critical_steps(successes, failures)
        content_hash = _procedure_hash(abstract_steps)

        for existing in self._procedures.values():
            if existing.content_hash == content_hash:
                return existing

        proc = Procedure(
            name=f"Procedure for {task_type}",
            task_type=task_type,
            abstract_steps=abstract_steps,
            critical_steps=critical,
            source_trajectory_ids=[t.trajectory_id for t in successes],
            status=ProcedureStatus.CANDIDATE,
            success_count=len(successes),
            failure_count=len(failures),
            reliability=_bayesian_reliability(
                len(successes), len(failures),
                self._config.bayesian_prior_alpha,
                self._config.bayesian_prior_beta,
            ),
            content_hash=content_hash,
        )
        self._procedures[proc.procedure_id] = proc
        logger.info(
            "Procedure extracted: %s reliability=%.3f",
            proc.procedure_id, proc.reliability,
        )
        return proc

    def record_outcome(
        self,
        procedure_id: str,
        success: bool,
    ) -> float:
        proc = self._procedures.get(procedure_id)
        if proc is None:
            return 0.0
        if success:
            proc.success_count += 1
        else:
            proc.failure_count += 1
        proc.reliability = _bayesian_reliability(
            proc.success_count, proc.failure_count,
            self._config.bayesian_prior_alpha,
            self._config.bayesian_prior_beta,
        )
        if proc.reliability < self._config.deprecation_threshold:
            proc.status = ProcedureStatus.DEPRECATED
        elif (
            proc.status == ProcedureStatus.CANDIDATE
            and proc.reliability >= self._config.reliability_threshold
        ):
            proc.status = ProcedureStatus.ACTIVE
        return proc.reliability

    def retrieve(self, task_type: str) -> list[RetrievalResult]:
        results: list[RetrievalResult] = []
        for proc in self._procedures.values():
            if proc.status == ProcedureStatus.DEPRECATED:
                continue
            if proc.task_type == task_type:
                results.append(RetrievalResult(
                    procedure=proc,
                    similarity=1.0,
                    recommended=(
                        proc.reliability
                        >= self._config.reliability_threshold
                    ),
                ))
            else:
                sim = _step_similarity(
                    proc.abstract_steps,
                    [task_type],
                )
                if sim > 0:
                    results.append(RetrievalResult(
                        procedure=proc,
                        similarity=sim,
                        recommended=False,
                    ))

        results.sort(key=lambda r: r.similarity, reverse=True)
        return results

    def contrastive_refine(
        self,
        task_type: str,
    ) -> list[ContrastiveInsight]:
        trajs = self._trajectories.get(task_type, [])
        successes = [
            t for t in trajs if t.outcome == TrajectoryOutcome.SUCCESS
        ]
        failures = [
            t for t in trajs if t.outcome == TrajectoryOutcome.FAILURE
        ]
        return _contrastive_analysis(successes, failures)

    def merge_similar(self) -> int:
        merged_count = 0
        procs = [
            p for p in self._procedures.values()
            if p.status != ProcedureStatus.DEPRECATED
        ]

        for i, a in enumerate(procs):
            for b in procs[i + 1:]:
                if a.status == ProcedureStatus.MERGED:
                    break
                if b.status == ProcedureStatus.MERGED:
                    continue
                sim = _step_similarity(
                    a.abstract_steps, b.abstract_steps,
                )
                if sim >= self._config.similarity_merge_threshold:
                    if a.reliability >= b.reliability:
                        b.status = ProcedureStatus.MERGED
                        a.source_trajectory_ids.extend(
                            b.source_trajectory_ids,
                        )
                    else:
                        a.status = ProcedureStatus.MERGED
                        b.source_trajectory_ids.extend(
                            a.source_trajectory_ids,
                        )
                    merged_count += 1

        return merged_count

    def get_procedure(self, procedure_id: str) -> Procedure | None:
        return self._procedures.get(procedure_id)

    def learner_report(self) -> LearnerReport:
        procs = list(self._procedures.values())
        total = len(procs)
        active = sum(
            1 for p in procs
            if p.status in (ProcedureStatus.ACTIVE, ProcedureStatus.CANDIDATE)
        )
        deprecated = sum(
            1 for p in procs if p.status == ProcedureStatus.DEPRECATED
        )
        avg_rel = (
            round(sum(p.reliability for p in procs) / total, 4)
            if total else 0.0
        )
        total_ingested = sum(
            len(ts) for ts in self._trajectories.values()
        )

        gate = (
            GateDecision.PASS if total == 0
            else _gate_from_reliability(
                avg_rel, self._config.reliability_threshold,
            )
        )

        return LearnerReport(
            total_procedures=total,
            active=active,
            deprecated=deprecated,
            avg_reliability=avg_rel,
            total_trajectories_ingested=total_ingested,
            gate=gate,
        )
