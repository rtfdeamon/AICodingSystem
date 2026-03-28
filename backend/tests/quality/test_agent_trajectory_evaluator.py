"""Tests for Agent Trajectory Evaluator."""

from __future__ import annotations

from app.quality.agent_trajectory_evaluator import (
    AgentTrajectoryEvaluator,
    BatchTrajectoryReport,
    GateDecision,
    StepType,
    TrajectoryConfig,
    TrajectoryGrade,
    TrajectoryRecord,
    TrajectoryStep,
    _compute_efficiency,
    _compute_recovery,
    _compute_tool_accuracy,
    _gate_from_grade,
    _grade_trajectory,
)

# ── _grade_trajectory ───────────────────────────────────────────────────

class TestGradeTrajectory:
    def test_optimal(self):
        cfg = TrajectoryConfig()
        assert _grade_trajectory(0.95, cfg) == TrajectoryGrade.OPTIMAL

    def test_efficient(self):
        cfg = TrajectoryConfig()
        assert _grade_trajectory(0.75, cfg) == TrajectoryGrade.EFFICIENT

    def test_wasteful(self):
        cfg = TrajectoryConfig()
        assert _grade_trajectory(0.50, cfg) == TrajectoryGrade.WASTEFUL

    def test_broken(self):
        cfg = TrajectoryConfig()
        assert _grade_trajectory(0.30, cfg) == TrajectoryGrade.BROKEN

    def test_boundary_optimal(self):
        cfg = TrajectoryConfig()
        assert _grade_trajectory(0.90, cfg) == TrajectoryGrade.OPTIMAL


# ── _gate_from_grade ────────────────────────────────────────────────────

class TestGateFromGrade:
    def test_optimal_passes(self):
        assert _gate_from_grade(TrajectoryGrade.OPTIMAL) == GateDecision.PASS

    def test_efficient_passes(self):
        assert _gate_from_grade(TrajectoryGrade.EFFICIENT) == GateDecision.PASS

    def test_wasteful_warns(self):
        assert _gate_from_grade(TrajectoryGrade.WASTEFUL) == GateDecision.WARN

    def test_broken_blocks(self):
        assert _gate_from_grade(TrajectoryGrade.BROKEN) == GateDecision.BLOCK


# ── _compute_efficiency ─────────────────────────────────────────────────

class TestComputeEfficiency:
    def test_perfect_efficiency(self):
        traj = TrajectoryRecord(agent="a", optimal_step_count=3)
        for i in range(3):
            traj.steps.append(TrajectoryStep(step_number=i + 1, contributed_to_outcome=True))
        eff = _compute_efficiency(traj)
        assert eff.efficiency_ratio == 1.0
        assert eff.dead_end_steps == 0

    def test_wasted_steps(self):
        traj = TrajectoryRecord(agent="a", optimal_step_count=2)
        traj.steps.append(TrajectoryStep(step_number=1, contributed_to_outcome=True))
        traj.steps.append(TrajectoryStep(step_number=2, contributed_to_outcome=False))
        traj.steps.append(TrajectoryStep(step_number=3, contributed_to_outcome=True))
        eff = _compute_efficiency(traj)
        assert eff.dead_end_steps == 1
        assert eff.dead_end_pct > 0

    def test_wasted_tool_calls(self):
        traj = TrajectoryRecord(agent="a", optimal_step_count=1)
        traj.steps.append(TrajectoryStep(
            step_type=StepType.TOOL_CALL, contributed_to_outcome=False,
        ))
        traj.steps.append(TrajectoryStep(
            step_type=StepType.TOOL_CALL, contributed_to_outcome=True,
        ))
        eff = _compute_efficiency(traj)
        assert eff.wasted_tool_calls == 1

    def test_empty_trajectory(self):
        traj = TrajectoryRecord(agent="a", optimal_step_count=3)
        eff = _compute_efficiency(traj)
        assert eff.actual_steps == 0


# ── _compute_recovery ──────────────────────────────────────────────────

class TestComputeRecovery:
    def test_no_errors(self):
        traj = TrajectoryRecord(agent="a")
        traj.steps.append(TrajectoryStep(step_type=StepType.REASONING))
        rec = _compute_recovery(traj)
        assert rec.recovery_rate == 1.0
        assert rec.total_errors == 0

    def test_error_with_recovery(self):
        traj = TrajectoryRecord(agent="a")
        traj.steps.append(TrajectoryStep(step_type=StepType.ERROR))
        traj.steps.append(TrajectoryStep(step_type=StepType.RECOVERY))
        rec = _compute_recovery(traj)
        assert rec.total_errors == 1
        assert rec.recovered_errors == 1
        assert rec.recovery_rate == 1.0

    def test_error_without_recovery(self):
        traj = TrajectoryRecord(agent="a")
        traj.steps.append(TrajectoryStep(step_type=StepType.ERROR))
        rec = _compute_recovery(traj)
        assert rec.total_errors == 1
        assert rec.recovered_errors == 0
        assert rec.recovery_rate == 0.0


# ── _compute_tool_accuracy ─────────────────────────────────────────────

class TestComputeToolAccuracy:
    def test_all_good(self):
        steps = [
            TrajectoryStep(
                step_type=StepType.TOOL_CALL,
                was_successful=True, contributed_to_outcome=True,
            ),
            TrajectoryStep(
                step_type=StepType.TOOL_CALL,
                was_successful=True, contributed_to_outcome=True,
            ),
        ]
        assert _compute_tool_accuracy(steps) == 1.0

    def test_mixed(self):
        steps = [
            TrajectoryStep(
                step_type=StepType.TOOL_CALL,
                was_successful=True, contributed_to_outcome=True,
            ),
            TrajectoryStep(
                step_type=StepType.TOOL_CALL,
                was_successful=False, contributed_to_outcome=False,
            ),
        ]
        assert _compute_tool_accuracy(steps) == 0.5

    def test_no_tool_calls(self):
        steps = [TrajectoryStep(step_type=StepType.REASONING)]
        assert _compute_tool_accuracy(steps) == 1.0


# ── AgentTrajectoryEvaluator ────────────────────────────────────────────

class TestAgentTrajectoryEvaluator:
    def test_create_trajectory(self):
        ev = AgentTrajectoryEvaluator()
        traj = ev.create_trajectory("agent1", "do something", optimal_step_count=3)
        assert isinstance(traj, TrajectoryRecord)
        assert traj.agent == "agent1"

    def test_add_step(self):
        ev = AgentTrajectoryEvaluator()
        traj = ev.create_trajectory("a")
        step = ev.add_step(traj.trajectory_id, StepType.REASONING, "think")
        assert step is not None
        assert step.step_number == 1
        step2 = ev.add_step(traj.trajectory_id, StepType.TOOL_CALL, "call", tool_name="search")
        assert step2.step_number == 2

    def test_add_step_nonexistent(self):
        ev = AgentTrajectoryEvaluator()
        step = ev.add_step("nonexistent", StepType.REASONING)
        assert step is None

    def test_set_outcome(self):
        ev = AgentTrajectoryEvaluator()
        traj = ev.create_trajectory("a")
        ev.set_outcome(traj.trajectory_id, False)
        assert traj.outcome_correct is False

    def test_evaluate_optimal_trajectory(self):
        ev = AgentTrajectoryEvaluator()
        traj = ev.create_trajectory("a", optimal_step_count=2)
        ev.add_step(traj.trajectory_id, StepType.REASONING, "think", reasoning_quality=1.0)
        ev.add_step(traj.trajectory_id, StepType.TOOL_CALL, "do", tool_name="t",
                     was_successful=True, contributed_to_outcome=True)
        score = ev.evaluate_trajectory(traj.trajectory_id)
        assert score is not None
        assert score.grade in {TrajectoryGrade.OPTIMAL, TrajectoryGrade.EFFICIENT}
        assert score.gate == GateDecision.PASS

    def test_evaluate_broken_trajectory(self):
        ev = AgentTrajectoryEvaluator()
        traj = ev.create_trajectory("a", optimal_step_count=2)
        for _i in range(10):
            ev.add_step(traj.trajectory_id, StepType.TOOL_CALL,
                         was_successful=False, contributed_to_outcome=False,
                         reasoning_quality=0.1)
        ev.set_outcome(traj.trajectory_id, False)
        score = ev.evaluate_trajectory(traj.trajectory_id)
        assert score is not None
        assert score.grade == TrajectoryGrade.BROKEN
        assert score.gate == GateDecision.BLOCK

    def test_evaluate_nonexistent(self):
        ev = AgentTrajectoryEvaluator()
        assert ev.evaluate_trajectory("nope") is None

    def test_batch_evaluate(self):
        ev = AgentTrajectoryEvaluator()
        # Good trajectory
        t1 = ev.create_trajectory("a", optimal_step_count=2)
        ev.add_step(t1.trajectory_id, StepType.REASONING, reasoning_quality=1.0)
        ev.add_step(t1.trajectory_id, StepType.TOOL_CALL, was_successful=True)
        # Bad trajectory
        t2 = ev.create_trajectory("b", optimal_step_count=1)
        for _ in range(8):
            ev.add_step(t2.trajectory_id, StepType.TOOL_CALL,
                         was_successful=False, contributed_to_outcome=False,
                         reasoning_quality=0.1)
        ev.set_outcome(t2.trajectory_id, False)

        report = ev.batch_evaluate()
        assert isinstance(report, BatchTrajectoryReport)
        assert report.total_trajectories == 2
        assert report.correct_outcomes >= 1

    def test_batch_empty(self):
        ev = AgentTrajectoryEvaluator()
        report = ev.batch_evaluate()
        assert report.total_trajectories == 0
        assert report.avg_path_score == 1.0

    def test_correct_with_bad_trajectory(self):
        ev = AgentTrajectoryEvaluator()
        t = ev.create_trajectory("a", optimal_step_count=1)
        for _ in range(10):
            ev.add_step(t.trajectory_id, StepType.TOOL_CALL,
                         was_successful=False, contributed_to_outcome=False,
                         reasoning_quality=0.1)
        ev.set_outcome(t.trajectory_id, True)  # right answer
        report = ev.batch_evaluate()
        assert report.correct_with_bad_trajectory >= 1

    def test_error_recovery_in_score(self):
        ev = AgentTrajectoryEvaluator()
        t = ev.create_trajectory("a", optimal_step_count=4)
        ev.add_step(t.trajectory_id, StepType.REASONING)
        ev.add_step(t.trajectory_id, StepType.ERROR, was_successful=False)
        ev.add_step(t.trajectory_id, StepType.RECOVERY)
        ev.add_step(t.trajectory_id, StepType.TOOL_CALL, was_successful=True)
        score = ev.evaluate_trajectory(t.trajectory_id)
        assert score.recovery.total_errors == 1
        assert score.recovery.recovered_errors == 1

    def test_step_clamp_reasoning_quality(self):
        ev = AgentTrajectoryEvaluator()
        t = ev.create_trajectory("a")
        step = ev.add_step(t.trajectory_id, StepType.REASONING, reasoning_quality=1.5)
        assert step.reasoning_quality == 1.0
        step2 = ev.add_step(t.trajectory_id, StepType.REASONING, reasoning_quality=-0.5)
        assert step2.reasoning_quality == 0.0

    def test_custom_config(self):
        cfg = TrajectoryConfig(optimal_threshold=0.99)
        ev = AgentTrajectoryEvaluator(config=cfg)
        t = ev.create_trajectory("a", optimal_step_count=2)
        ev.add_step(t.trajectory_id, StepType.REASONING, reasoning_quality=0.9)
        ev.add_step(t.trajectory_id, StepType.TOOL_CALL, was_successful=True)
        score = ev.evaluate_trajectory(t.trajectory_id)
        assert score.grade != TrajectoryGrade.OPTIMAL  # threshold too high
