"""Tests for shadow mode A/B testing module."""

from __future__ import annotations

import pytest

from app.observability.shadow_testing import (
    ExperimentStatus,
    VariantType,
    cancel_experiment,
    clear_experiment_data,
    complete_experiment,
    compute_experiment_report,
    create_experiment,
    experiment_report_to_json,
    get_experiment,
    get_experiment_results,
    list_active_experiments,
    record_shadow_result,
    simple_significance_test,
)


@pytest.fixture(autouse=True)
def _clean() -> None:
    clear_experiment_data()


def _make_experiment(
    name: str = "test_experiment",
    min_samples: int = 10,
) -> str:
    """Helper to create a standard experiment and return its ID."""
    exp = create_experiment(
        name=name,
        champion_model="gpt-4",
        challenger_model="claude-sonnet-4-6",
        champion_prompt="v1",
        challenger_prompt="v2",
        min_samples=min_samples,
    )
    return exp.id


def _record_n_results(
    experiment_id: str,
    n: int,
    champion_score: float = 0.8,
    challenger_score: float = 0.85,
    champion_latency: float = 200.0,
    challenger_latency: float = 150.0,
    champion_cost: float = 0.01,
    challenger_cost: float = 0.008,
) -> None:
    """Helper to record multiple shadow results."""
    for i in range(n):
        record_shadow_result(
            experiment_id=experiment_id,
            prompt=f"test prompt {i}",
            champion_resp=f"champion response {i}",
            challenger_resp=f"challenger response {i}",
            champion_score=champion_score,
            challenger_score=challenger_score,
            champion_latency=champion_latency,
            challenger_latency=challenger_latency,
            champion_cost=champion_cost,
            challenger_cost=challenger_cost,
        )


class TestCreateExperiment:
    def test_creates_active_experiment(self) -> None:
        exp = create_experiment(
            name="model_comparison",
            champion_model="gpt-4",
            challenger_model="claude-sonnet-4-6",
            champion_prompt="v1",
            challenger_prompt="v2",
        )
        assert exp.name == "model_comparison"
        assert exp.status == ExperimentStatus.ACTIVE
        assert exp.champion_model == "gpt-4"
        assert exp.challenger_model == "claude-sonnet-4-6"
        assert exp.champion_prompt_version == "v1"
        assert exp.challenger_prompt_version == "v2"

    def test_default_min_samples(self) -> None:
        exp = create_experiment(
            name="test",
            champion_model="a",
            challenger_model="b",
            champion_prompt="v1",
            challenger_prompt="v2",
        )
        assert exp.min_samples == 500

    def test_custom_min_samples(self) -> None:
        exp = create_experiment(
            name="test",
            champion_model="a",
            challenger_model="b",
            champion_prompt="v1",
            challenger_prompt="v2",
            min_samples=100,
        )
        assert exp.min_samples == 100

    def test_generates_unique_id(self) -> None:
        exp1 = create_experiment("a", "m1", "m2", "p1", "p2")
        exp2 = create_experiment("b", "m1", "m2", "p1", "p2")
        assert exp1.id != exp2.id

    def test_created_at_is_set(self) -> None:
        exp = create_experiment("test", "m1", "m2", "p1", "p2")
        assert exp.created_at is not None
        assert exp.completed_at is None


class TestRecordShadowResult:
    def test_records_result(self) -> None:
        exp_id = _make_experiment()
        result = record_shadow_result(
            experiment_id=exp_id,
            prompt="what is 2+2?",
            champion_resp="4",
            challenger_resp="four",
            champion_score=0.9,
            challenger_score=0.85,
            champion_latency=100.0,
            challenger_latency=120.0,
            champion_cost=0.01,
            challenger_cost=0.008,
        )
        assert result.experiment_id == exp_id
        assert result.prompt == "what is 2+2?"
        assert result.champion_score == 0.9
        assert result.challenger_score == 0.85

    def test_result_has_unique_request_id(self) -> None:
        exp_id = _make_experiment()
        r1 = record_shadow_result(exp_id, "p", "a", "b", 0.5, 0.5, 100, 100, 0.01, 0.01)
        r2 = record_shadow_result(exp_id, "p", "a", "b", 0.5, 0.5, 100, 100, 0.01, 0.01)
        assert r1.request_id != r2.request_id

    def test_raises_for_missing_experiment(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            record_shadow_result("nonexistent", "p", "a", "b", 0.5, 0.5, 100, 100, 0.01, 0.01)

    def test_raises_for_inactive_experiment(self) -> None:
        exp_id = _make_experiment()
        complete_experiment(exp_id)
        with pytest.raises(ValueError, match="not active"):
            record_shadow_result(exp_id, "p", "a", "b", 0.5, 0.5, 100, 100, 0.01, 0.01)


class TestGetExperiment:
    def test_get_existing(self) -> None:
        exp_id = _make_experiment()
        found = get_experiment(exp_id)
        assert found is not None
        assert found.id == exp_id

    def test_get_nonexistent(self) -> None:
        assert get_experiment("does_not_exist") is None


class TestGetExperimentResults:
    def test_returns_results(self) -> None:
        exp_id = _make_experiment()
        _record_n_results(exp_id, 5)
        results = get_experiment_results(exp_id)
        assert len(results) == 5

    def test_returns_empty_for_unknown(self) -> None:
        results = get_experiment_results("unknown")
        assert results == []


class TestSignificanceTest:
    def test_significant_difference(self) -> None:
        # Large, clearly different distributions
        scores_a = [0.9] * 50
        scores_b = [0.5] * 50
        # Add small variance to avoid division issues
        scores_a = [0.9 + (i % 5) * 0.01 for i in range(50)]
        scores_b = [0.5 + (i % 5) * 0.01 for i in range(50)]
        is_sig, p_val = simple_significance_test(scores_a, scores_b)
        assert is_sig is True
        assert p_val < 0.05

    def test_not_significant_similar_scores(self) -> None:
        scores_a = [0.80 + (i % 3) * 0.01 for i in range(30)]
        scores_b = [0.80 + (i % 3) * 0.01 for i in range(30)]
        is_sig, p_val = simple_significance_test(scores_a, scores_b)
        assert is_sig is False

    def test_too_few_samples(self) -> None:
        is_sig, p_val = simple_significance_test([0.9], [0.5])
        assert is_sig is False
        assert p_val == 1.0

    def test_empty_lists(self) -> None:
        is_sig, p_val = simple_significance_test([], [])
        assert is_sig is False
        assert p_val == 1.0

    def test_identical_scores(self) -> None:
        scores = [0.8] * 20
        is_sig, p_val = simple_significance_test(scores, scores)
        assert is_sig is False


class TestComputeExperimentReport:
    def test_report_with_results(self) -> None:
        exp_id = _make_experiment()
        _record_n_results(exp_id, 10, champion_score=0.8, challenger_score=0.85)
        report = compute_experiment_report(exp_id)
        assert report.experiment_id == exp_id
        assert report.total_samples == 10
        assert report.champion_avg_score == pytest.approx(0.8)
        assert report.challenger_avg_score == pytest.approx(0.85)

    def test_report_no_results(self) -> None:
        exp_id = _make_experiment()
        report = compute_experiment_report(exp_id)
        assert report.total_samples == 0
        assert report.champion_avg_score == 0.0
        assert report.winner is None

    def test_report_raises_for_missing_experiment(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            compute_experiment_report("nonexistent")

    def test_report_single_result(self) -> None:
        exp_id = _make_experiment()
        _record_n_results(exp_id, 1, champion_score=0.9, challenger_score=0.7)
        report = compute_experiment_report(exp_id)
        assert report.total_samples == 1
        assert report.champion_avg_score == pytest.approx(0.9)
        assert report.challenger_avg_score == pytest.approx(0.7)
        # Not enough samples for significance
        assert report.is_significant is False
        assert report.winner is None


class TestWinnerDetermination:
    def test_challenger_wins(self) -> None:
        exp_id = _make_experiment()
        # Clearly different scores with variance
        for i in range(50):
            record_shadow_result(
                exp_id, f"p{i}", "a", "b",
                champion_score=0.5 + (i % 5) * 0.01,
                challenger_score=0.9 + (i % 5) * 0.01,
                champion_latency=200, challenger_latency=150,
                champion_cost=0.01, challenger_cost=0.008,
            )
        report = compute_experiment_report(exp_id)
        assert report.is_significant is True
        assert report.winner == VariantType.CHALLENGER

    def test_champion_wins(self) -> None:
        exp_id = _make_experiment()
        for i in range(50):
            record_shadow_result(
                exp_id, f"p{i}", "a", "b",
                champion_score=0.95 + (i % 5) * 0.005,
                challenger_score=0.5 + (i % 5) * 0.01,
                champion_latency=200, challenger_latency=150,
                champion_cost=0.01, challenger_cost=0.008,
            )
        report = compute_experiment_report(exp_id)
        assert report.is_significant is True
        assert report.winner == VariantType.CHAMPION

    def test_no_winner_when_not_significant(self) -> None:
        exp_id = _make_experiment()
        # Use high-variance scores so the small mean difference is not significant
        for i in range(10):
            record_shadow_result(
                exp_id, f"p{i}", "a", "b",
                champion_score=0.5 + (i % 5) * 0.1,
                challenger_score=0.51 + (i % 5) * 0.1,
                champion_latency=200, challenger_latency=150,
                champion_cost=0.01, challenger_cost=0.008,
            )
        report = compute_experiment_report(exp_id)
        assert report.winner is None


class TestCostComparison:
    def test_cost_totals(self) -> None:
        exp_id = _make_experiment()
        _record_n_results(exp_id, 10, champion_cost=0.02, challenger_cost=0.01)
        report = compute_experiment_report(exp_id)
        assert report.champion_total_cost == pytest.approx(0.2)
        assert report.challenger_total_cost == pytest.approx(0.1)


class TestLatencyComparison:
    def test_latency_averages(self) -> None:
        exp_id = _make_experiment()
        _record_n_results(
            exp_id, 10,
            champion_latency=300.0,
            challenger_latency=150.0,
        )
        report = compute_experiment_report(exp_id)
        assert report.champion_avg_latency == pytest.approx(300.0)
        assert report.challenger_avg_latency == pytest.approx(150.0)


class TestCompleteExperiment:
    def test_marks_completed(self) -> None:
        exp_id = _make_experiment()
        exp = complete_experiment(exp_id)
        assert exp.status == ExperimentStatus.COMPLETED
        assert exp.completed_at is not None

    def test_raises_for_missing(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            complete_experiment("missing")


class TestCancelExperiment:
    def test_marks_cancelled(self) -> None:
        exp_id = _make_experiment()
        exp = cancel_experiment(exp_id)
        assert exp.status == ExperimentStatus.CANCELLED
        assert exp.completed_at is not None

    def test_raises_for_missing(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            cancel_experiment("missing")


class TestListActiveExperiments:
    def test_lists_only_active(self) -> None:
        id1 = _make_experiment("exp1")
        id2 = _make_experiment("exp2")
        id3 = _make_experiment("exp3")
        complete_experiment(id2)
        cancel_experiment(id3)
        active = list_active_experiments()
        assert len(active) == 1
        assert active[0].id == id1

    def test_empty_when_none_active(self) -> None:
        assert list_active_experiments() == []


class TestExperimentReportToJson:
    def test_serializes_report(self) -> None:
        exp_id = _make_experiment()
        _record_n_results(exp_id, 5)
        report = compute_experiment_report(exp_id)
        data = experiment_report_to_json(report)
        assert data["experiment_id"] == exp_id
        assert data["total_samples"] == 5
        assert "champion_avg_score" in data
        assert "challenger_avg_score" in data
        assert "p_value" in data
        assert isinstance(data["is_significant"], bool)

    def test_winner_none_serialized(self) -> None:
        exp_id = _make_experiment()
        report = compute_experiment_report(exp_id)
        data = experiment_report_to_json(report)
        assert data["winner"] is None

    def test_winner_value_serialized(self) -> None:
        exp_id = _make_experiment()
        for i in range(50):
            record_shadow_result(
                exp_id, f"p{i}", "a", "b",
                champion_score=0.5 + (i % 5) * 0.01,
                challenger_score=0.95 + (i % 5) * 0.005,
                champion_latency=200, challenger_latency=150,
                champion_cost=0.01, challenger_cost=0.008,
            )
        report = compute_experiment_report(exp_id)
        data = experiment_report_to_json(report)
        assert data["winner"] == "challenger"


class TestClearExperimentData:
    def test_clears_all(self) -> None:
        exp_id = _make_experiment()
        _record_n_results(exp_id, 3)
        clear_experiment_data()
        assert get_experiment(exp_id) is None
        assert get_experiment_results(exp_id) == []
        assert list_active_experiments() == []
