"""Tests for Procedural Memory Learner."""

from __future__ import annotations

from app.quality.procedural_memory_learner import (
    GateDecision,
    LearnerConfig,
    ProceduralMemoryLearner,
    ProcedureStatus,
    Trajectory,
    TrajectoryOutcome,
    TrajectoryStep,
    _bayesian_reliability,
    _contrastive_analysis,
    _extract_abstract_steps,
    _gate_from_reliability,
    _identify_critical_steps,
    _procedure_hash,
    _step_similarity,
)

# ── Helper factories ──────────────────────────────────────────────────────


def _make_learner(**overrides) -> ProceduralMemoryLearner:
    config = LearnerConfig(**overrides) if overrides else None
    return ProceduralMemoryLearner(config)


def _make_step(
    idx: int = 0,
    action: str = "read_file",
    tool: str = "",
    critical: bool = False,
) -> TrajectoryStep:
    return TrajectoryStep(
        step_idx=idx,
        action=action,
        tool_call=tool,
        is_critical=critical,
    )


_SENTINEL: list = None  # type: ignore[assignment]


def _make_trajectory(
    task_type: str = "code_review",
    outcome: TrajectoryOutcome = TrajectoryOutcome.SUCCESS,
    quality: float = 0.9,
    steps: list[TrajectoryStep] | None = _SENTINEL,
) -> Trajectory:
    return Trajectory(
        agent_id="agent-1",
        task_type=task_type,
        outcome=outcome,
        quality_score=quality,
        steps=(
            [
                _make_step(0, "read_file"),
                _make_step(1, "analyze"),
                _make_step(2, "write_review"),
            ]
            if steps is _SENTINEL
            else (steps or [])
        ),
    )


# ── Pure helper tests ─────────────────────────────────────────────────────


class TestProcedureHash:
    def test_deterministic(self):
        steps = ["a", "b", "c"]
        assert _procedure_hash(steps) == _procedure_hash(steps)

    def test_different_steps(self):
        assert _procedure_hash(["a"]) != _procedure_hash(["b"])

    def test_length(self):
        assert len(_procedure_hash(["x"])) == 16


class TestBayesianReliability:
    def test_uninformed_prior(self):
        rel = _bayesian_reliability(0, 0)
        assert rel == 0.5

    def test_all_success(self):
        rel = _bayesian_reliability(10, 0)
        assert rel > 0.9

    def test_all_failure(self):
        rel = _bayesian_reliability(0, 10)
        assert rel < 0.1

    def test_balanced(self):
        rel = _bayesian_reliability(5, 5)
        assert 0.45 < rel < 0.55

    def test_custom_prior(self):
        rel = _bayesian_reliability(0, 0, alpha=5.0, beta=1.0)
        assert rel > 0.8


class TestExtractAbstractSteps:
    def test_basic(self):
        traj = _make_trajectory()
        steps = _extract_abstract_steps(traj)
        assert len(steps) == 3
        assert steps[0] == "read_file"

    def test_with_tool_call(self):
        traj = _make_trajectory(
            steps=[_make_step(0, "search", tool="grep")],
        )
        steps = _extract_abstract_steps(traj)
        assert "via grep" in steps[0]

    def test_empty(self):
        traj = _make_trajectory(steps=[])
        steps = _extract_abstract_steps(traj)
        assert steps == []


class TestIdentifyCriticalSteps:
    def test_divergent_steps(self):
        success = [_make_trajectory(
            steps=[
                _make_step(0, "read"),
                _make_step(1, "validate"),
            ],
        )]
        failure = [_make_trajectory(
            outcome=TrajectoryOutcome.FAILURE,
            steps=[
                _make_step(0, "read"),
                _make_step(1, "skip_validation"),
            ],
        )]
        critical = _identify_critical_steps(success, failure)
        assert 1 in critical

    def test_identical_steps(self):
        success = [_make_trajectory(
            steps=[_make_step(0, "read")],
        )]
        failure = [_make_trajectory(
            outcome=TrajectoryOutcome.FAILURE,
            steps=[_make_step(0, "read")],
        )]
        critical = _identify_critical_steps(success, failure)
        assert len(critical) == 0

    def test_empty_success(self):
        critical = _identify_critical_steps([], [])
        assert critical == []


class TestContrastiveAnalysis:
    def test_divergence(self):
        success = [_make_trajectory(
            steps=[
                _make_step(0, "read"),
                _make_step(1, "validate"),
            ],
        )]
        failure = [_make_trajectory(
            outcome=TrajectoryOutcome.FAILURE,
            steps=[
                _make_step(0, "read"),
                _make_step(1, "skip"),
            ],
        )]
        insights = _contrastive_analysis(success, failure)
        assert len(insights) >= 1
        divergent = [i for i in insights if i.step_idx == 1]
        assert len(divergent) == 1

    def test_no_failures(self):
        success = [_make_trajectory()]
        insights = _contrastive_analysis(success, [])
        assert insights == []

    def test_no_successes(self):
        failure = [_make_trajectory(
            outcome=TrajectoryOutcome.FAILURE,
        )]
        insights = _contrastive_analysis([], failure)
        assert insights == []


class TestStepSimilarity:
    def test_identical(self):
        steps = ["read", "analyze", "write"]
        assert _step_similarity(steps, steps) == 1.0

    def test_no_overlap(self):
        assert _step_similarity(["a"], ["b"]) == 0.0

    def test_partial(self):
        sim = _step_similarity(
            ["a", "b", "c"], ["b", "c", "d"],
        )
        assert 0.4 < sim < 0.6

    def test_empty(self):
        assert _step_similarity([], []) == 1.0


class TestGateFromReliability:
    def test_high(self):
        assert _gate_from_reliability(0.9, 0.6) == GateDecision.PASS

    def test_medium(self):
        assert _gate_from_reliability(0.5, 0.6) == GateDecision.WARN

    def test_low(self):
        assert _gate_from_reliability(0.2, 0.6) == GateDecision.BLOCK


# ── Learner class tests ──────────────────────────────────────────────────


class TestIngestTrajectory:
    def test_ingest(self):
        pml = _make_learner()
        tid = pml.ingest_trajectory(_make_trajectory())
        assert tid


class TestExtractProcedure:
    def test_enough_trajectories(self):
        pml = _make_learner(min_trajectories_to_extract=2)
        pml.ingest_trajectory(_make_trajectory(quality=0.8))
        pml.ingest_trajectory(_make_trajectory(quality=0.95))
        proc = pml.extract_procedure("code_review")
        assert proc is not None
        assert proc.task_type == "code_review"
        assert len(proc.abstract_steps) > 0

    def test_not_enough_trajectories(self):
        pml = _make_learner(min_trajectories_to_extract=5)
        pml.ingest_trajectory(_make_trajectory())
        proc = pml.extract_procedure("code_review")
        assert proc is None

    def test_deduplication(self):
        pml = _make_learner(min_trajectories_to_extract=2)
        pml.ingest_trajectory(_make_trajectory(quality=0.9))
        pml.ingest_trajectory(_make_trajectory(quality=0.8))
        p1 = pml.extract_procedure("code_review")
        p2 = pml.extract_procedure("code_review")
        assert p1.procedure_id == p2.procedure_id

    def test_reliability_score(self):
        pml = _make_learner(min_trajectories_to_extract=2)
        pml.ingest_trajectory(_make_trajectory())
        pml.ingest_trajectory(_make_trajectory())
        pml.ingest_trajectory(_make_trajectory(
            outcome=TrajectoryOutcome.FAILURE,
        ))
        proc = pml.extract_procedure("code_review")
        assert proc.reliability > 0.5


class TestRecordOutcome:
    def test_success_increases(self):
        pml = _make_learner(min_trajectories_to_extract=2)
        pml.ingest_trajectory(_make_trajectory())
        pml.ingest_trajectory(_make_trajectory())
        proc = pml.extract_procedure("code_review")
        r1 = proc.reliability
        r2 = pml.record_outcome(proc.procedure_id, success=True)
        assert r2 >= r1

    def test_failure_decreases(self):
        pml = _make_learner(min_trajectories_to_extract=2)
        pml.ingest_trajectory(_make_trajectory())
        pml.ingest_trajectory(_make_trajectory())
        proc = pml.extract_procedure("code_review")
        r1 = proc.reliability
        r2 = pml.record_outcome(proc.procedure_id, success=False)
        assert r2 <= r1

    def test_deprecation(self):
        pml = _make_learner(
            min_trajectories_to_extract=2,
            deprecation_threshold=0.4,
        )
        pml.ingest_trajectory(_make_trajectory())
        pml.ingest_trajectory(_make_trajectory())
        proc = pml.extract_procedure("code_review")
        for _ in range(20):
            pml.record_outcome(proc.procedure_id, success=False)
        p = pml.get_procedure(proc.procedure_id)
        assert p.status == ProcedureStatus.DEPRECATED

    def test_not_found(self):
        pml = _make_learner()
        rel = pml.record_outcome("nope", success=True)
        assert rel == 0.0

    def test_promotion_to_active(self):
        pml = _make_learner(
            min_trajectories_to_extract=2,
            reliability_threshold=0.6,
        )
        pml.ingest_trajectory(_make_trajectory())
        pml.ingest_trajectory(_make_trajectory())
        proc = pml.extract_procedure("code_review")
        assert proc.status == ProcedureStatus.CANDIDATE
        for _ in range(5):
            pml.record_outcome(proc.procedure_id, success=True)
        p = pml.get_procedure(proc.procedure_id)
        assert p.status == ProcedureStatus.ACTIVE


class TestRetrieve:
    def test_exact_match(self):
        pml = _make_learner(min_trajectories_to_extract=2)
        pml.ingest_trajectory(_make_trajectory())
        pml.ingest_trajectory(_make_trajectory())
        pml.extract_procedure("code_review")
        results = pml.retrieve("code_review")
        assert len(results) == 1
        assert results[0].similarity == 1.0

    def test_no_match(self):
        pml = _make_learner()
        results = pml.retrieve("unknown_task")
        assert len(results) == 0

    def test_deprecated_excluded(self):
        pml = _make_learner(
            min_trajectories_to_extract=2,
            deprecation_threshold=0.4,
        )
        pml.ingest_trajectory(_make_trajectory())
        pml.ingest_trajectory(_make_trajectory())
        proc = pml.extract_procedure("code_review")
        for _ in range(20):
            pml.record_outcome(proc.procedure_id, success=False)
        results = pml.retrieve("code_review")
        assert len(results) == 0


class TestContrastiveRefine:
    def test_with_data(self):
        pml = _make_learner()
        pml.ingest_trajectory(_make_trajectory())
        pml.ingest_trajectory(_make_trajectory(
            outcome=TrajectoryOutcome.FAILURE,
            steps=[
                _make_step(0, "read_file"),
                _make_step(1, "skip_analysis"),
                _make_step(2, "write_review"),
            ],
        ))
        insights = pml.contrastive_refine("code_review")
        assert len(insights) >= 1

    def test_no_data(self):
        pml = _make_learner()
        insights = pml.contrastive_refine("nothing")
        assert insights == []


class TestMergeSimilar:
    def test_merge(self):
        pml = _make_learner(
            min_trajectories_to_extract=2,
            similarity_merge_threshold=0.7,
        )
        # Similar but not identical steps so they get separate hashes
        steps_a = [
            _make_step(0, "read_file"),
            _make_step(1, "analyze"),
            _make_step(2, "write_review"),
        ]
        steps_b = [
            _make_step(0, "read_file"),
            _make_step(1, "analyze"),
            _make_step(2, "write_review"),
            _make_step(3, "finalize"),
        ]
        pml.ingest_trajectory(_make_trajectory(
            task_type="review_a", quality=0.9, steps=steps_a,
        ))
        pml.ingest_trajectory(_make_trajectory(
            task_type="review_a", quality=0.8, steps=steps_a,
        ))
        pml.ingest_trajectory(_make_trajectory(
            task_type="review_b", quality=0.7, steps=steps_b,
        ))
        pml.ingest_trajectory(_make_trajectory(
            task_type="review_b", quality=0.6, steps=steps_b,
        ))
        pml.extract_procedure("review_a")
        pml.extract_procedure("review_b")
        merged = pml.merge_similar()
        assert merged >= 1

    def test_no_merge(self):
        pml = _make_learner(
            min_trajectories_to_extract=2,
            similarity_merge_threshold=0.99,
        )
        pml.ingest_trajectory(_make_trajectory(
            task_type="a",
            steps=[_make_step(0, "unique_action_a")],
        ))
        pml.ingest_trajectory(_make_trajectory(
            task_type="a",
            steps=[_make_step(0, "unique_action_a")],
        ))
        pml.ingest_trajectory(_make_trajectory(
            task_type="b",
            steps=[_make_step(0, "totally_different")],
        ))
        pml.ingest_trajectory(_make_trajectory(
            task_type="b",
            steps=[_make_step(0, "totally_different")],
        ))
        pml.extract_procedure("a")
        pml.extract_procedure("b")
        merged = pml.merge_similar()
        assert merged == 0


class TestLearnerReport:
    def test_empty(self):
        pml = _make_learner()
        report = pml.learner_report()
        assert report.total_procedures == 0
        assert report.gate == GateDecision.PASS

    def test_with_procedures(self):
        pml = _make_learner(min_trajectories_to_extract=2)
        pml.ingest_trajectory(_make_trajectory())
        pml.ingest_trajectory(_make_trajectory())
        pml.extract_procedure("code_review")
        report = pml.learner_report()
        assert report.total_procedures == 1
        assert report.total_trajectories_ingested == 2
        assert report.avg_reliability > 0
