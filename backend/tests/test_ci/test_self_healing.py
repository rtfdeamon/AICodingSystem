"""Tests for self-healing tests module — failure classification, healing actions."""

from __future__ import annotations

import pytest

from app.ci.self_healing import (
    FailureCategory,
    build_healing_prompt,
    classify_failure,
    clear_healing_history,
    generate_healing_action,
    get_healing_stats,
    healing_result_to_json,
    process_failures,
)


@pytest.fixture(autouse=True)
def _clean_history() -> None:
    clear_healing_history()


# ── Failure classification ────────────────────────────────────────────


class TestClassifyFailure:
    def test_detects_selector_change(self) -> None:
        result = classify_failure(
            "test_login_button",
            "Unable to find element with role 'button'",
        )
        assert result.category == FailureCategory.SELECTOR_CHANGE
        assert result.is_healable

    def test_detects_query_selector_not_found(self) -> None:
        result = classify_failure(
            "test_header",
            "querySelector('.header-nav') returned null",
        )
        assert result.category == FailureCategory.SELECTOR_CHANGE

    def test_detects_timing_issue(self) -> None:
        result = classify_failure(
            "test_async_load",
            "Timed out waiting for element to appear",
        )
        assert result.category == FailureCategory.TIMING
        assert result.is_healable

    def test_detects_wait_for_timeout(self) -> None:
        result = classify_failure(
            "test_data_load",
            "waitFor callback not resolved within 5000ms",
        )
        assert result.category == FailureCategory.TIMING

    def test_detects_api_change(self) -> None:
        result = classify_failure(
            "test_fetch_users",
            "TypeError: response.data.users is not a function",
        )
        assert result.category == FailureCategory.API_CHANGE
        assert result.is_healable

    def test_detects_status_code_error(self) -> None:
        result = classify_failure(
            "test_api_call",
            "Expected status code 200 but response status code was 422",
        )
        assert result.category == FailureCategory.API_CHANGE

    def test_detects_env_config_issue(self) -> None:
        result = classify_failure(
            "test_connect",
            "ECONNREFUSED 127.0.0.1:5432",
        )
        assert result.category == FailureCategory.ENV_CONFIG
        assert result.is_healable

    def test_detects_database_connection_refused(self) -> None:
        result = classify_failure(
            "test_db",
            "database connection refused on localhost",
        )
        assert result.category == FailureCategory.ENV_CONFIG

    def test_detects_dependency_missing(self) -> None:
        result = classify_failure(
            "test_import",
            "ModuleNotFoundError: No module named 'pandas'",
        )
        assert result.category == FailureCategory.DEPENDENCY
        assert not result.is_healable  # Needs human resolution

    def test_detects_logic_bug(self) -> None:
        result = classify_failure(
            "test_calculation",
            "AssertionError: expected 42 but got 43",
        )
        assert result.category == FailureCategory.LOGIC_BUG
        assert not result.is_healable

    def test_unknown_category(self) -> None:
        result = classify_failure(
            "test_something",
            "Something weird happened",
        )
        assert result.category == FailureCategory.UNKNOWN
        assert not result.is_healable

    def test_confidence_above_zero(self) -> None:
        result = classify_failure("test_x", "Unable to find element")
        assert result.confidence > 0


# ── Healing action generation ─────────────────────────────────────────


class TestGenerateHealingAction:
    def test_generates_selector_fix(self) -> None:
        classification = classify_failure("t", "Unable to find element with testid")
        action = generate_healing_action("t", "test_file.py", classification, "")
        assert action is not None
        assert action.category == FailureCategory.SELECTOR_CHANGE
        assert "testid" in action.description.lower() or "selector" in action.description.lower()

    def test_generates_timing_fix(self) -> None:
        classification = classify_failure("t", "Timed out")
        action = generate_healing_action("t", "test_file.py", classification, "")
        assert action is not None
        assert action.category == FailureCategory.TIMING

    def test_returns_none_for_logic_bug(self) -> None:
        classification = classify_failure("t", "AssertionError: 1 != 2")
        action = generate_healing_action("t", "test.py", classification, "")
        assert action is None

    def test_returns_none_for_unhealable(self) -> None:
        classification = classify_failure("t", "ModuleNotFoundError: no pandas")
        action = generate_healing_action("t", "test.py", classification, "")
        assert action is None


# ── Prompt building ───────────────────────────────────────────────────


class TestBuildHealingPrompt:
    def test_includes_all_actions(self) -> None:
        from app.ci.self_healing import HealingAction
        actions = [
            HealingAction(
                test_file="test_ui.py",
                test_name="test_button",
                category=FailureCategory.SELECTOR_CHANGE,
                description="Update selector",
            ),
            HealingAction(
                test_file="test_api.py",
                test_name="test_fetch",
                category=FailureCategory.API_CHANGE,
                description="Update mock",
            ),
        ]
        prompt = build_healing_prompt(actions)
        assert "test_button" in prompt
        assert "test_fetch" in prompt
        assert "selector_change" in prompt
        assert "api_change" in prompt

    def test_includes_test_content(self) -> None:
        prompt = build_healing_prompt([], test_content="def test_foo(): pass")
        assert "test_foo" in prompt

    def test_includes_rules(self) -> None:
        prompt = build_healing_prompt([])
        assert "Only modify test code" in prompt


# ── Full processing ──────────────────────────────────────────────────


class TestProcessFailures:
    def test_processes_mixed_failures(self) -> None:
        failures = [
            {"test_name": "test_ui", "error_message": "Unable to find element", "file": "t.py"},
            {"test_name": "test_calc", "error_message": "AssertionError: 1 != 2", "file": "t.py"},
            {"test_name": "test_load", "error_message": "Timed out", "file": "t.py"},
        ]
        result = process_failures(failures)
        assert result.total_failures == 3
        assert result.classified == 3
        assert result.skipped_logic_bugs == 1
        assert result.healable >= 1

    def test_empty_failures(self) -> None:
        result = process_failures([])
        assert result.total_failures == 0
        assert result.classified == 0

    def test_respects_confidence_threshold(self) -> None:
        failures = [
            {"test_name": "test_x", "error_message": "Something weird"},
        ]
        result = process_failures(failures, auto_heal_threshold=0.99)
        assert result.healable == 0


# ── Stats ────────────────────────────────────────────────────────────


class TestHealingStats:
    def test_empty_stats(self) -> None:
        stats = get_healing_stats()
        assert stats["total_sessions"] == 0

    def test_tracks_sessions(self) -> None:
        process_failures([
            {"test_name": "t", "error_message": "Unable to find element", "file": "f.py"}
        ])
        stats = get_healing_stats()
        assert stats["total_sessions"] == 1
        assert stats["total_failures_processed"] == 1


# ── JSON serialization ──────────────────────────────────────────────


class TestHealingResultToJson:
    def test_serializes_result(self) -> None:
        result = process_failures([
            {"test_name": "t", "error_message": "Timed out", "file": "f.py"}
        ])
        data = healing_result_to_json(result)
        assert data["total_failures"] == 1
        assert isinstance(data["actions"], list)
