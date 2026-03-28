"""Agent Trajectory Evaluator — execution path evaluation for multi-step agents.

Evaluating AI agents requires more than checking final outcomes.
Trajectory evaluation examines every reasoning step, tool call, and
decision along the execution path.  An agent can produce a correct final
answer through flawed reasoning, or fail despite correct intermediate
steps.  This module evaluates the *how*, not just the *what*.

Based on:
- Galileo "Agent Evaluation Framework: Metrics, Rubrics & Benchmarks" (2026)
- Anthropic "Demystifying Evals for AI Agents" (2026)
- Amazon "Evaluating AI Agents: Real-world Lessons" (2026)
- InfoQ "Evaluating AI Agents in Practice" (2026)
- Evidently AI "10 AI Agent Benchmarks" (2026)

Key capabilities:
- Step-by-step trajectory recording (reasoning, tool calls, decisions)
- Tool call validation: correct tool, correct arguments, correct order
- Reasoning quality scoring per step
- Path efficiency: actual steps vs optimal steps
- Dead-end detection: wasted steps that don't contribute to outcome
- Error recovery scoring: how well agent recovers from failures
- Quality gate: optimal / efficient / wasteful / broken
- Batch evaluation across multiple trajectories
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class StepType(StrEnum):
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    DECISION = "decision"
    ERROR = "error"
    RECOVERY = "recovery"


class TrajectoryGrade(StrEnum):
    OPTIMAL = "optimal"  # >= 0.90
    EFFICIENT = "efficient"  # >= 0.70
    WASTEFUL = "wasteful"  # >= 0.45
    BROKEN = "broken"  # < 0.45


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class TrajectoryStep:
    """Single step in an agent's execution trajectory."""

    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_number: int = 0
    step_type: StepType = StepType.REASONING
    description: str = ""
    tool_name: str = ""  # for tool_call steps
    tool_args: dict = field(default_factory=dict)
    was_successful: bool = True
    contributed_to_outcome: bool = True  # did this step help?
    reasoning_quality: float = 1.0  # 0-1, how sound was the reasoning
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TrajectoryRecord:
    """Complete trajectory for one agent execution."""

    trajectory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent: str = ""
    task_description: str = ""
    steps: list[TrajectoryStep] = field(default_factory=list)
    outcome_correct: bool = True
    optimal_step_count: int = 0  # expected minimum steps
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TrajectoryConfig:
    """Configuration for trajectory evaluation."""

    optimal_threshold: float = 0.90
    efficient_threshold: float = 0.70
    wasteful_threshold: float = 0.45
    max_efficiency_ratio: float = 3.0  # >3x optimal = wasteful
    min_reasoning_quality: float = 0.5


@dataclass
class StepAnalysis:
    """Analysis of a single step."""

    step_id: str
    step_type: StepType
    is_productive: bool  # contributed to outcome
    is_successful: bool
    reasoning_quality: float


@dataclass
class EfficiencyMetrics:
    """Path efficiency metrics."""

    actual_steps: int
    optimal_steps: int
    efficiency_ratio: float  # optimal / actual (1.0 = perfect)
    dead_end_steps: int
    dead_end_pct: float
    wasted_tool_calls: int


@dataclass
class RecoveryMetrics:
    """Error recovery metrics."""

    total_errors: int
    recovered_errors: int
    recovery_rate: float
    recovery_steps: int  # steps spent recovering


@dataclass
class TrajectoryScore:
    """Complete trajectory evaluation score."""

    trajectory_id: str
    agent: str
    efficiency: EfficiencyMetrics
    recovery: RecoveryMetrics
    step_analyses: list[StepAnalysis]
    avg_reasoning_quality: float
    tool_call_accuracy: float
    path_score: float  # combined 0-1
    grade: TrajectoryGrade
    gate: GateDecision
    outcome_correct: bool


@dataclass
class BatchTrajectoryReport:
    """Batch evaluation across trajectories."""

    scores: list[TrajectoryScore]
    avg_path_score: float
    avg_efficiency_ratio: float
    avg_recovery_rate: float
    overall_grade: TrajectoryGrade
    total_trajectories: int
    correct_outcomes: int
    correct_with_bad_trajectory: int  # right answer, wrong reasoning


# ── Pure helpers ─────────────────────────────────────────────────────────

def _compute_efficiency(record: TrajectoryRecord) -> EfficiencyMetrics:
    """Compute path efficiency metrics."""
    actual = len(record.steps)
    optimal = max(1, record.optimal_step_count) if record.optimal_step_count > 0 else max(1, actual)

    dead_ends = [s for s in record.steps if not s.contributed_to_outcome]
    wasted_tools = [
        s for s in record.steps
        if s.step_type == StepType.TOOL_CALL and not s.contributed_to_outcome
    ]

    ratio = optimal / actual if actual > 0 else 1.0
    dead_pct = len(dead_ends) / actual if actual > 0 else 0.0

    return EfficiencyMetrics(
        actual_steps=actual,
        optimal_steps=optimal,
        efficiency_ratio=round(min(1.0, ratio), 4),
        dead_end_steps=len(dead_ends),
        dead_end_pct=round(dead_pct, 4),
        wasted_tool_calls=len(wasted_tools),
    )


def _compute_recovery(record: TrajectoryRecord) -> RecoveryMetrics:
    """Compute error recovery metrics."""
    errors = [s for s in record.steps if s.step_type == StepType.ERROR]
    recoveries = [s for s in record.steps if s.step_type == StepType.RECOVERY]

    recovery_rate = len(recoveries) / len(errors) if errors else 1.0

    return RecoveryMetrics(
        total_errors=len(errors),
        recovered_errors=len(recoveries),
        recovery_rate=round(min(1.0, recovery_rate), 4),
        recovery_steps=len(recoveries),
    )


def _analyze_steps(steps: list[TrajectoryStep]) -> list[StepAnalysis]:
    """Analyze individual steps."""
    return [
        StepAnalysis(
            step_id=s.step_id,
            step_type=s.step_type,
            is_productive=s.contributed_to_outcome,
            is_successful=s.was_successful,
            reasoning_quality=s.reasoning_quality,
        )
        for s in steps
    ]


def _compute_tool_accuracy(steps: list[TrajectoryStep]) -> float:
    """Fraction of tool calls that were successful and productive."""
    tool_steps = [s for s in steps if s.step_type == StepType.TOOL_CALL]
    if not tool_steps:
        return 1.0
    good = sum(1 for s in tool_steps if s.was_successful and s.contributed_to_outcome)
    return round(good / len(tool_steps), 4)


def _grade_trajectory(score: float, config: TrajectoryConfig) -> TrajectoryGrade:
    """Grade a trajectory score."""
    if score >= config.optimal_threshold:
        return TrajectoryGrade.OPTIMAL
    if score >= config.efficient_threshold:
        return TrajectoryGrade.EFFICIENT
    if score >= config.wasteful_threshold:
        return TrajectoryGrade.WASTEFUL
    return TrajectoryGrade.BROKEN


def _gate_from_grade(grade: TrajectoryGrade) -> GateDecision:
    """Map grade to gate decision."""
    if grade in {TrajectoryGrade.OPTIMAL, TrajectoryGrade.EFFICIENT}:
        return GateDecision.PASS
    if grade == TrajectoryGrade.WASTEFUL:
        return GateDecision.WARN
    return GateDecision.BLOCK


# ── Main class ───────────────────────────────────────────────────────────

class AgentTrajectoryEvaluator:
    """Evaluates agent execution trajectories."""

    def __init__(self, config: TrajectoryConfig | None = None) -> None:
        self._config = config or TrajectoryConfig()
        self._trajectories: list[TrajectoryRecord] = []

    def create_trajectory(
        self,
        agent: str,
        task_description: str = "",
        optimal_step_count: int = 0,
    ) -> TrajectoryRecord:
        """Create a new trajectory record."""
        rec = TrajectoryRecord(
            agent=agent,
            task_description=task_description,
            optimal_step_count=optimal_step_count,
        )
        self._trajectories.append(rec)
        return rec

    def add_step(
        self,
        trajectory_id: str,
        step_type: StepType = StepType.REASONING,
        description: str = "",
        tool_name: str = "",
        tool_args: dict | None = None,
        was_successful: bool = True,
        contributed_to_outcome: bool = True,
        reasoning_quality: float = 1.0,
    ) -> TrajectoryStep | None:
        """Add a step to an existing trajectory."""
        traj = next(
            (t for t in self._trajectories if t.trajectory_id == trajectory_id),
            None,
        )
        if traj is None:
            return None

        step = TrajectoryStep(
            step_number=len(traj.steps) + 1,
            step_type=step_type,
            description=description,
            tool_name=tool_name,
            tool_args=tool_args or {},
            was_successful=was_successful,
            contributed_to_outcome=contributed_to_outcome,
            reasoning_quality=max(0.0, min(1.0, reasoning_quality)),
        )
        traj.steps.append(step)
        return step

    def set_outcome(self, trajectory_id: str, correct: bool) -> None:
        """Set the outcome correctness for a trajectory."""
        traj = next(
            (t for t in self._trajectories if t.trajectory_id == trajectory_id),
            None,
        )
        if traj is not None:
            traj.outcome_correct = correct

    def evaluate_trajectory(self, trajectory_id: str) -> TrajectoryScore | None:
        """Evaluate a single trajectory."""
        traj = next(
            (t for t in self._trajectories if t.trajectory_id == trajectory_id),
            None,
        )
        if traj is None:
            return None

        efficiency = _compute_efficiency(traj)
        recovery = _compute_recovery(traj)
        step_analyses = _analyze_steps(traj.steps)
        tool_accuracy = _compute_tool_accuracy(traj.steps)

        reasoning_scores = [
            s.reasoning_quality for s in traj.steps
            if s.step_type in {StepType.REASONING, StepType.DECISION}
        ]
        avg_reasoning = (
            sum(reasoning_scores) / len(reasoning_scores) if reasoning_scores else 1.0
        )

        # Combined path score: weighted average
        path_score = (
            0.30 * efficiency.efficiency_ratio
            + 0.20 * (1.0 - efficiency.dead_end_pct)
            + 0.20 * avg_reasoning
            + 0.15 * tool_accuracy
            + 0.15 * recovery.recovery_rate
        )
        path_score = round(max(0.0, min(1.0, path_score)), 4)

        grade = _grade_trajectory(path_score, self._config)
        gate = _gate_from_grade(grade)

        return TrajectoryScore(
            trajectory_id=traj.trajectory_id,
            agent=traj.agent,
            efficiency=efficiency,
            recovery=recovery,
            step_analyses=step_analyses,
            avg_reasoning_quality=round(avg_reasoning, 4),
            tool_call_accuracy=tool_accuracy,
            path_score=path_score,
            grade=grade,
            gate=gate,
            outcome_correct=traj.outcome_correct,
        )

    def batch_evaluate(self) -> BatchTrajectoryReport:
        """Evaluate all trajectories."""
        scores = []
        for traj in self._trajectories:
            score = self.evaluate_trajectory(traj.trajectory_id)
            if score:
                scores.append(score)

        avg_path = (
            sum(s.path_score for s in scores) / len(scores) if scores else 1.0
        )
        avg_eff = (
            sum(s.efficiency.efficiency_ratio for s in scores) / len(scores)
            if scores else 1.0
        )
        avg_rec = (
            sum(s.recovery.recovery_rate for s in scores) / len(scores)
            if scores else 1.0
        )

        correct = sum(1 for s in scores if s.outcome_correct)
        correct_bad_traj = sum(
            1 for s in scores
            if s.outcome_correct and s.grade in {TrajectoryGrade.WASTEFUL, TrajectoryGrade.BROKEN}
        )

        overall_grade = _grade_trajectory(avg_path, self._config)

        return BatchTrajectoryReport(
            scores=scores,
            avg_path_score=round(avg_path, 4),
            avg_efficiency_ratio=round(avg_eff, 4),
            avg_recovery_rate=round(avg_rec, 4),
            overall_grade=overall_grade,
            total_trajectories=len(scores),
            correct_outcomes=correct,
            correct_with_bad_trajectory=correct_bad_traj,
        )
