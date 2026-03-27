"""Tests for automated evaluation tests module."""

from __future__ import annotations

import json

import pytest

from app.observability.eval_tests import (
    EvalBaseline,
    EvalStatus,
    check_completeness,
    check_length,
    check_patterns,
    check_structure,
    clear_eval_data,
    compute_prompt_hash,
    eval_result_to_json,
    evaluate_output,
    get_baseline,
    get_eval_stats,
    register_baseline,
)


@pytest.fixture(autouse=True)
def _clean() -> None:
    clear_eval_data()


# ── Prompt hashing ───────────────────────────────────────────────────


class TestComputePromptHash:
    def test_stable_hash(self) -> None:
        h1 = compute_prompt_hash("Review this code")
        h2 = compute_prompt_hash("Review this code")
        assert h1 == h2

    def test_normalizes_whitespace(self) -> None:
        h1 = compute_prompt_hash("Review  this   code")
        h2 = compute_prompt_hash("Review this code")
        assert h1 == h2

    def test_different_prompts_different_hashes(self) -> None:
        h1 = compute_prompt_hash("Review code")
        h2 = compute_prompt_hash("Write code")
        assert h1 != h2


# ── Baseline management ──────────────────────────────────────────────


class TestBaselineManagement:
    def test_register_and_get_baseline(self) -> None:
        register_baseline(
            prompt="Review this diff",
            agent_name="review_agent",
            action="code_review",
            expected_fields=["comments", "summary"],
            min_length=10,
        )
        found = get_baseline("Review this diff")
        assert found is not None
        assert found.agent_name == "review_agent"
        assert "comments" in found.expected_fields

    def test_get_nonexistent_baseline(self) -> None:
        assert get_baseline("nonexistent prompt") is None

    def test_register_with_structure(self) -> None:
        baseline = register_baseline(
            prompt="test",
            agent_name="test",
            action="test",
            expected_structure={"comments": "list", "summary": "str"},
        )
        assert "comments" in baseline.expected_structure


# ── Structure check ──────────────────────────────────────────────────


class TestCheckStructure:
    def test_valid_json_with_all_keys(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
            expected_structure={"comments": "list", "summary": "str"},
        )
        output = json.dumps({"comments": [], "summary": "ok"})
        result = check_structure(output, baseline)
        assert result.status == EvalStatus.PASSED
        assert result.score == 1.0

    def test_missing_keys(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
            expected_structure={"comments": "list", "summary": "str", "score": "float"},
        )
        output = json.dumps({"comments": []})
        result = check_structure(output, baseline)
        assert result.status in (EvalStatus.FAILED, EvalStatus.DEGRADED)
        assert result.score < 1.0

    def test_invalid_json_with_structure_expected(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
            expected_structure={"key": "str"},
        )
        result = check_structure("not json", baseline)
        assert result.status == EvalStatus.FAILED

    def test_non_json_accepted_without_structure(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
        )
        result = check_structure("plain text response", baseline)
        assert result.status == EvalStatus.PASSED


# ── Completeness check ───────────────────────────────────────────────


class TestCheckCompleteness:
    def test_all_fields_present(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
            expected_fields=["comments", "summary"],
        )
        result = check_completeness('{"comments": [], "summary": "ok"}', baseline)
        assert result.status == EvalStatus.PASSED

    def test_missing_fields(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
            expected_fields=["comments", "summary", "score"],
        )
        result = check_completeness('{"comments": []}', baseline)
        assert result.status in (EvalStatus.FAILED, EvalStatus.DEGRADED)

    def test_no_field_requirements(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
        )
        result = check_completeness("anything", baseline)
        assert result.status == EvalStatus.PASSED


# ── Length check ─────────────────────────────────────────────────────


class TestCheckLength:
    def test_within_bounds(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
            min_length=5,
            max_length=100,
        )
        result = check_length("Hello World", baseline)
        assert result.status == EvalStatus.PASSED

    def test_too_short(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
            min_length=100,
        )
        result = check_length("short", baseline)
        assert result.status == EvalStatus.FAILED

    def test_too_long(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
            max_length=10,
        )
        result = check_length("x" * 100, baseline)
        assert result.status == EvalStatus.DEGRADED


# ── Pattern check ────────────────────────────────────────────────────


class TestCheckPatterns:
    def test_all_patterns_match(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
            expected_patterns=[r"comments", r"summary"],
        )
        result = check_patterns('{"comments": [], "summary": "ok"}', baseline)
        assert result.status == EvalStatus.PASSED

    def test_unmatched_pattern(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
            expected_patterns=[r"comments", r"missing_field"],
        )
        result = check_patterns('{"comments": []}', baseline)
        assert result.status in (EvalStatus.FAILED, EvalStatus.DEGRADED)

    def test_no_patterns(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
        )
        result = check_patterns("anything", baseline)
        assert result.status == EvalStatus.PASSED


# ── Full evaluation ──────────────────────────────────────────────────


class TestEvaluateOutput:
    def test_passes_with_good_output(self) -> None:
        register_baseline(
            prompt="Review this",
            agent_name="review_agent",
            action="code_review",
            expected_structure={"comments": "list", "summary": "str"},
            expected_fields=["comments", "summary"],
            min_length=10,
            max_length=10000,
        )
        output = json.dumps({"comments": [{"file": "a.py"}], "summary": "Looks good"})
        result = evaluate_output(output, "Review this", "review_agent", "code_review")
        assert result.overall_status == EvalStatus.PASSED
        assert result.overall_score > 0.5

    def test_fails_with_bad_output(self) -> None:
        register_baseline(
            prompt="Review code",
            agent_name="review_agent",
            action="code_review",
            expected_structure={"comments": "list", "summary": "str"},
            min_length=100,
        )
        result = evaluate_output("bad", "Review code", "review_agent", "code_review")
        assert result.overall_status == EvalStatus.FAILED

    def test_skips_without_baseline(self) -> None:
        result = evaluate_output("output", "unknown prompt", "agent", "action")
        assert result.overall_status == EvalStatus.SKIPPED

    def test_explicit_baseline(self) -> None:
        baseline = EvalBaseline(
            prompt_hash="x",
            agent_name="test",
            action="test",
            min_length=1,
            max_length=1000,
        )
        result = evaluate_output(
            "valid output",
            "any prompt",
            "test",
            "test",
            baseline=baseline,
        )
        assert result.overall_status == EvalStatus.PASSED


# ── Stats ────────────────────────────────────────────────────────────


class TestEvalStats:
    def test_empty_stats(self) -> None:
        stats = get_eval_stats()
        assert stats["total_evals"] == 0

    def test_tracks_evals(self) -> None:
        register_baseline(
            prompt="test prompt",
            agent_name="agent",
            action="action",
            min_length=1,
        )
        evaluate_output("output", "test prompt", "agent", "action")
        stats = get_eval_stats()
        assert stats["total_evals"] == 1
        assert stats["passed"] == 1


# ── JSON serialization ──────────────────────────────────────────────


class TestEvalResultToJson:
    def test_serializes_result(self) -> None:
        register_baseline(
            prompt="p",
            agent_name="a",
            action="act",
            min_length=1,
        )
        result = evaluate_output("output", "p", "a", "act")
        data = eval_result_to_json(result)
        assert data["agent_name"] == "a"
        assert data["overall_status"] == "passed"
        assert isinstance(data["results"], list)
