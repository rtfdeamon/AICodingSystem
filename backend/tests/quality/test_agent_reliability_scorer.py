"""Tests for Agent Reliability Scorer."""

from __future__ import annotations

from app.quality.agent_reliability_scorer import (
    AgentReliabilityScorer,
    BatchReliabilityReport,
    DimensionScore,
    GateDecision,
    ObservationRecord,
    ReliabilityConfig,
    ReliabilityGrade,
    ReliabilityScore,
    ReliabilityTrend,
    SafetySeverity,
    _compute_calibration,
    _compute_consistency,
    _compute_robustness,
    _compute_safety,
    _gate_from_grade,
    _grade_reliability,
)

# ── _grade_reliability ──────────────────────────────────────────────────

class TestGradeReliability:
    def test_reliable(self):
        cfg = ReliabilityConfig()
        assert _grade_reliability(0.90, cfg) == ReliabilityGrade.RELIABLE

    def test_acceptable(self):
        cfg = ReliabilityConfig()
        assert _grade_reliability(0.70, cfg) == ReliabilityGrade.ACCEPTABLE

    def test_fragile(self):
        cfg = ReliabilityConfig()
        assert _grade_reliability(0.50, cfg) == ReliabilityGrade.FRAGILE

    def test_unreliable(self):
        cfg = ReliabilityConfig()
        assert _grade_reliability(0.30, cfg) == ReliabilityGrade.UNRELIABLE

    def test_boundary_reliable(self):
        cfg = ReliabilityConfig()
        assert _grade_reliability(0.85, cfg) == ReliabilityGrade.RELIABLE

    def test_boundary_acceptable(self):
        cfg = ReliabilityConfig()
        assert _grade_reliability(0.65, cfg) == ReliabilityGrade.ACCEPTABLE


# ── _gate_from_grade ────────────────────────────────────────────────────

class TestGateFromGrade:
    def test_reliable_passes(self):
        assert _gate_from_grade(ReliabilityGrade.RELIABLE) == GateDecision.PASS

    def test_acceptable_passes(self):
        assert _gate_from_grade(ReliabilityGrade.ACCEPTABLE) == GateDecision.PASS

    def test_fragile_warns(self):
        assert _gate_from_grade(ReliabilityGrade.FRAGILE) == GateDecision.WARN

    def test_unreliable_blocks(self):
        assert _gate_from_grade(ReliabilityGrade.UNRELIABLE) == GateDecision.BLOCK


# ── _compute_consistency ────────────────────────────────────────────────

class TestComputeConsistency:
    def test_empty(self):
        result = _compute_consistency([])
        assert result.score == 1.0

    def test_single_record(self):
        rec = ObservationRecord(agent="a", input_hash="h1", quality_score=0.8)
        result = _compute_consistency([rec])
        assert result.score == 1.0

    def test_consistent_repeated_inputs(self):
        records = [
            ObservationRecord(agent="a", input_hash="h1", quality_score=0.8),
            ObservationRecord(agent="a", input_hash="h1", quality_score=0.8),
            ObservationRecord(agent="a", input_hash="h1", quality_score=0.8),
        ]
        result = _compute_consistency(records)
        assert result.score == 1.0

    def test_inconsistent_repeated_inputs(self):
        records = [
            ObservationRecord(agent="a", input_hash="h1", quality_score=0.9),
            ObservationRecord(agent="a", input_hash="h1", quality_score=0.1),
        ]
        result = _compute_consistency(records)
        assert result.score < 1.0

    def test_no_repeated_inputs_uses_overall_variance(self):
        records = [
            ObservationRecord(agent="a", input_hash="h1", quality_score=0.5),
            ObservationRecord(agent="a", input_hash="h2", quality_score=0.5),
        ]
        result = _compute_consistency(records)
        assert result.score == 1.0  # zero variance


# ── _compute_robustness ────────────────────────────────────────────────

class TestComputeRobustness:
    def test_no_perturbation_data(self):
        records = [
            ObservationRecord(agent="a", quality_score=0.8, is_perturbed=False),
        ]
        result = _compute_robustness(records)
        assert result.score == 1.0

    def test_no_quality_drop(self):
        records = [
            ObservationRecord(agent="a", quality_score=0.8, is_perturbed=False),
            ObservationRecord(agent="a", quality_score=0.8, is_perturbed=True),
        ]
        result = _compute_robustness(records)
        assert result.score == 1.0

    def test_quality_drop(self):
        records = [
            ObservationRecord(agent="a", quality_score=0.9, is_perturbed=False),
            ObservationRecord(agent="a", quality_score=0.3, is_perturbed=True),
        ]
        result = _compute_robustness(records)
        assert result.score < 1.0

    def test_zero_normal_quality(self):
        records = [
            ObservationRecord(agent="a", quality_score=0.0, is_perturbed=False),
            ObservationRecord(agent="a", quality_score=0.0, is_perturbed=True),
        ]
        result = _compute_robustness(records)
        assert result.score == 1.0


# ── _compute_calibration ───────────────────────────────────────────────

class TestComputeCalibration:
    def test_perfect_calibration(self):
        records = [
            ObservationRecord(agent="a", quality_score=0.8, confidence=0.8),
            ObservationRecord(agent="a", quality_score=0.6, confidence=0.6),
        ]
        result = _compute_calibration(records)
        assert result.score == 1.0

    def test_poor_calibration(self):
        records = [
            ObservationRecord(agent="a", quality_score=0.9, confidence=0.1),
            ObservationRecord(agent="a", quality_score=0.8, confidence=0.2),
        ]
        result = _compute_calibration(records)
        assert result.score < 0.5

    def test_no_confidence_data(self):
        records = [
            ObservationRecord(agent="a", quality_score=0.8, confidence=0.0),
        ]
        result = _compute_calibration(records)
        assert result.score == 1.0  # insufficient data


# ── _compute_safety ─────────────────────────────────────────────────────

class TestComputeSafety:
    def test_no_incidents(self):
        records = [
            ObservationRecord(agent="a", quality_score=0.8),
        ]
        result = _compute_safety(records)
        assert result.score == 1.0

    def test_low_severity_incident(self):
        records = [
            ObservationRecord(agent="a", quality_score=0.8),
            ObservationRecord(agent="a", safety_incident=True, safety_severity=SafetySeverity.LOW),
        ] + [ObservationRecord(agent="a", quality_score=0.8) for _ in range(8)]
        result = _compute_safety(records)
        assert result.score > 0.9

    def test_critical_incident(self):
        records = [
            ObservationRecord(
                agent="a", safety_incident=True,
                safety_severity=SafetySeverity.CRITICAL,
            ),
            ObservationRecord(agent="a", quality_score=0.8),
        ]
        result = _compute_safety(records)
        assert result.score < 1.0

    def test_empty_records(self):
        result = _compute_safety([])
        assert result.score == 1.0

    def test_multiple_incidents(self):
        records = [
            ObservationRecord(agent="a", safety_incident=True, safety_severity=SafetySeverity.HIGH),
            ObservationRecord(
                agent="a", safety_incident=True,
                safety_severity=SafetySeverity.MEDIUM,
            ),
        ]
        result = _compute_safety(records)
        assert result.score < 0.5


# ── AgentReliabilityScorer ──────────────────────────────────────────────

class TestAgentReliabilityScorer:
    def test_record_observation(self):
        scorer = AgentReliabilityScorer()
        rec = scorer.record_observation("agent1", quality_score=0.8)
        assert rec.agent == "agent1"
        assert rec.quality_score == 0.8

    def test_clamp_quality_score(self):
        scorer = AgentReliabilityScorer()
        rec = scorer.record_observation("agent1", quality_score=1.5)
        assert rec.quality_score == 1.0
        rec2 = scorer.record_observation("agent1", quality_score=-0.3)
        assert rec2.quality_score == 0.0

    def test_evaluate_agent_basic(self):
        scorer = AgentReliabilityScorer()
        for _ in range(5):
            scorer.record_observation("a", quality_score=0.9, confidence=0.9)
        result = scorer.evaluate_agent("a")
        assert isinstance(result, ReliabilityScore)
        assert result.agent == "a"
        assert result.composite_score > 0

    def test_evaluate_reliable_agent(self):
        scorer = AgentReliabilityScorer()
        for _ in range(10):
            scorer.record_observation(
                "a", input_hash="h1", quality_score=0.95,
                confidence=0.95, is_perturbed=False,
            )
        for _ in range(5):
            scorer.record_observation(
                "a", input_hash="h1", quality_score=0.93,
                confidence=0.93, is_perturbed=True,
            )
        result = scorer.evaluate_agent("a")
        assert result.grade == ReliabilityGrade.RELIABLE
        assert result.gate == GateDecision.PASS

    def test_evaluate_unreliable_agent(self):
        scorer = AgentReliabilityScorer()
        # Use deterministic varied scores
        qualities = [0.1, 0.9, 0.3, 0.7, 0.2, 0.8, 0.4, 0.6, 0.15, 0.85,
                     0.25, 0.75, 0.35, 0.65, 0.12, 0.88, 0.22, 0.78, 0.3, 0.7]
        confs = [0.9, 0.1, 0.8, 0.2, 0.7, 0.3, 0.6, 0.4, 0.95, 0.05,
                 0.85, 0.15, 0.75, 0.25, 0.92, 0.08, 0.82, 0.18, 0.7, 0.3]
        for i in range(20):
            scorer.record_observation(
                "bad", input_hash=f"h{i % 3}",
                quality_score=qualities[i],
                confidence=confs[i],
                is_perturbed=i % 2 == 0,
                safety_incident=i % 5 == 0,
                safety_severity=SafetySeverity.HIGH if i % 5 == 0 else None,
            )
        result = scorer.evaluate_agent("bad")
        assert result.composite_score < 0.85

    def test_trend_stable(self):
        scorer = AgentReliabilityScorer()
        for _ in range(5):
            scorer.record_observation("a", quality_score=0.9)
        scorer.evaluate_agent("a")
        scorer.evaluate_agent("a")
        trend = scorer.get_trend("a")
        assert isinstance(trend, ReliabilityTrend)
        assert trend.direction == "stable"

    def test_trend_no_history(self):
        scorer = AgentReliabilityScorer()
        trend = scorer.get_trend("unknown")
        assert trend.direction == "stable"
        assert trend.current_score == 0.0

    def test_batch_evaluate(self):
        scorer = AgentReliabilityScorer()
        for _ in range(5):
            scorer.record_observation(
                "a", input_hash="h1", quality_score=0.95,
                confidence=0.95,
            )
            scorer.record_observation(
                "b", input_hash="h2", quality_score=0.3,
                confidence=0.9, safety_incident=True,
                safety_severity=SafetySeverity.HIGH,
            )
        report = scorer.batch_evaluate()
        assert isinstance(report, BatchReliabilityReport)
        assert len(report.scores) == 2
        # "a" should be more reliable than "b"
        a_score = next(s for s in report.scores if s.agent == "a")
        b_score = next(s for s in report.scores if s.agent == "b")
        assert a_score.composite_score > b_score.composite_score

    def test_batch_evaluate_empty(self):
        scorer = AgentReliabilityScorer()
        report = scorer.batch_evaluate()
        assert report.total_observations == 0
        assert report.overall_score == 1.0

    def test_custom_config(self):
        cfg = ReliabilityConfig(reliable_threshold=0.99)
        scorer = AgentReliabilityScorer(config=cfg)
        for i in range(10):
            scorer.record_observation(
                "a", input_hash="h1",
                quality_score=0.7 + (i % 3) * 0.1,
                confidence=0.9, is_perturbed=i % 2 == 0,
            )
        result = scorer.evaluate_agent("a")
        # composite won't reach 0.99 due to variance and perturbation
        assert result.composite_score < 0.99

    def test_observation_record_fields(self):
        rec = ObservationRecord(
            agent="test", input_hash="h1", quality_score=0.7,
            confidence=0.8, is_perturbed=True,
            safety_incident=True, safety_severity=SafetySeverity.MEDIUM,
        )
        assert rec.agent == "test"
        assert rec.is_perturbed is True
        assert rec.safety_severity == SafetySeverity.MEDIUM

    def test_dimension_scores_present(self):
        scorer = AgentReliabilityScorer()
        for _ in range(5):
            scorer.record_observation("a", quality_score=0.8, confidence=0.8)
        result = scorer.evaluate_agent("a")
        assert isinstance(result.consistency, DimensionScore)
        assert isinstance(result.robustness, DimensionScore)
        assert isinstance(result.calibration, DimensionScore)
        assert isinstance(result.safety, DimensionScore)
