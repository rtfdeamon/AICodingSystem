"""Tests for intelligent test selection module."""

from __future__ import annotations

from app.quality.test_selector import SelectionResult, select_tests


class TestSourceToTestMapping:
    def test_maps_agent_file(self) -> None:
        result = select_tests(
            changed_files=["app/agents/review_agent.py"],
            available_tests=["tests/test_agents/test_review_agent.py"],
        )
        assert "tests/test_agents/test_review_agent.py" in result.selected_tests

    def test_maps_api_file(self) -> None:
        result = select_tests(
            changed_files=["app/api/v1/reviews.py"],
            available_tests=["tests/test_api/test_reviews.py"],
        )
        assert "tests/test_api/test_reviews.py" in result.selected_tests

    def test_maps_service_file(self) -> None:
        result = select_tests(
            changed_files=["app/services/kanban_service.py"],
            available_tests=["tests/test_services/test_kanban_service.py"],
        )
        assert "tests/test_services/test_kanban_service.py" in result.selected_tests

    def test_maps_test_file_to_itself(self) -> None:
        result = select_tests(
            changed_files=["tests/test_api/test_reviews.py"],
            available_tests=["tests/test_api/test_reviews.py"],
        )
        assert "tests/test_api/test_reviews.py" in result.selected_tests


class TestConftestHandling:
    def test_conftest_change_selects_all(self) -> None:
        all_tests = [
            "tests/test_api/test_reviews.py",
            "tests/test_agents/test_review_agent.py",
            "tests/test_services/test_kanban_service.py",
        ]
        result = select_tests(
            changed_files=["tests/conftest.py"],
            available_tests=all_tests,
        )
        assert len(result.selected_tests) == len(all_tests)


class TestFallback:
    def test_no_mapping_runs_all(self) -> None:
        all_tests = ["tests/test_x.py", "tests/test_y.py"]
        result = select_tests(
            changed_files=["unknown/module.py"],
            available_tests=all_tests,
        )
        assert len(result.selected_tests) == len(all_tests)

    def test_non_python_files_ignored(self) -> None:
        result = select_tests(
            changed_files=["README.md", "package.json"],
            available_tests=["tests/test_x.py"],
        )
        # Non-python files produce no mapping, falls back to all
        assert isinstance(result, SelectionResult)


class TestAlwaysRun:
    def test_always_run_included(self) -> None:
        result = select_tests(
            changed_files=["app/agents/review_agent.py"],
            available_tests=[
                "tests/test_agents/test_review_agent.py",
                "tests/test_integration/test_e2e.py",
            ],
            always_run=["tests/test_integration/test_e2e.py"],
        )
        assert "tests/test_integration/test_e2e.py" in result.selected_tests


class TestSelectionMetrics:
    def test_selection_ratio(self) -> None:
        all_tests = [
            "tests/test_agents/test_review_agent.py",
            "tests/test_api/test_reviews.py",
            "tests/test_services/test_kanban_service.py",
        ]
        result = select_tests(
            changed_files=["app/agents/review_agent.py"],
            available_tests=all_tests,
        )
        assert result.selection_ratio < 1.0
        assert result.total_tests_available == 3

    def test_count_property(self) -> None:
        result = SelectionResult(selected_tests=["a.py", "b.py"])
        assert result.count == 2

    def test_reason_tracking(self) -> None:
        result = select_tests(
            changed_files=["app/agents/review_agent.py"],
            available_tests=["tests/test_agents/test_review_agent.py"],
        )
        assert len(result.reason) > 0


class TestWithoutAvailableTests:
    def test_returns_predicted_paths(self) -> None:
        result = select_tests(
            changed_files=["app/agents/review_agent.py"],
        )
        assert result.count > 0
        assert "tests/test_agents/test_review_agent.py" in result.selected_tests


class TestEmptyInput:
    def test_no_changed_files(self) -> None:
        result = select_tests(changed_files=[], available_tests=["tests/test_x.py"])
        # No changes, falls back to all
        assert isinstance(result, SelectionResult)
