"""Intelligent test selection — predicts relevant tests for code changes.

Analyzes which files changed and maps them to likely-affected test files,
enabling up to 40% faster CI by running only relevant tests.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SelectionResult:
    """Result of intelligent test selection."""

    selected_tests: list[str] = field(default_factory=list)
    # test -> changed files that triggered it
    reason: dict[str, list[str]] = field(default_factory=dict)
    total_tests_available: int = 0
    selection_ratio: float = 0.0  # fraction of tests selected

    @property
    def count(self) -> int:
        return len(self.selected_tests)


def _source_to_test_path(source_path: str) -> list[str]:
    """Map a source file to its likely test file paths.

    Examples:
        app/agents/review_agent.py -> tests/test_agents/test_review_agent.py
        app/api/v1/reviews.py -> tests/test_api/test_reviews.py
        app/services/kanban_service.py -> tests/test_services/test_kanban_service.py
    """
    candidates: list[str] = []
    path = Path(source_path)

    # Skip non-Python files
    if path.suffix != ".py":
        return candidates

    # Skip test files themselves
    if path.name.startswith("test_") or "/tests/" in source_path:
        return [source_path]

    # Strip leading 'app/' and build test path
    parts = list(path.parts)
    if parts and parts[0] == "app":
        parts = parts[1:]

    filename = path.stem  # e.g. "review_agent"
    test_filename = f"test_{filename}.py"

    # Direct mapping: app/X/Y.py -> tests/test_X/test_Y.py
    if len(parts) >= 2:
        module_dir = parts[0]  # e.g. "agents", "api", "services"
        candidates.append(f"tests/test_{module_dir}/{test_filename}")

        # For api/v1/X.py -> tests/test_api/test_X.py
        if module_dir == "api" and len(parts) >= 3:
            candidates.append(f"tests/test_api/{test_filename}")
    elif len(parts) == 1:
        # Top-level app files
        candidates.append(f"tests/{test_filename}")

    return candidates


def _get_affected_modules(changed_files: list[str]) -> set[str]:
    """Determine which top-level modules are affected by changed files."""
    modules: set[str] = set()
    for f in changed_files:
        parts = Path(f).parts
        if parts and parts[0] == "app" and len(parts) > 1:
            modules.add(parts[1])
    return modules


def select_tests(
    changed_files: list[str],
    available_tests: list[str] | None = None,
    *,
    test_dir: str = "tests",
    always_run: list[str] | None = None,
) -> SelectionResult:
    """Select relevant tests based on changed files.

    Parameters
    ----------
    changed_files:
        List of changed source file paths (relative to project root).
    available_tests:
        List of all available test file paths. If None, returns predicted
        test paths without validation.
    test_dir:
        Root test directory name.
    always_run:
        Test files that should always be included (e.g. conftest, integration).

    Returns
    -------
    SelectionResult with selected tests and reasons.
    """
    selected: dict[str, list[str]] = {}  # test_path -> [source files that triggered it]

    # Always include conftest changes
    if always_run:
        for t in always_run:
            selected[t] = ["always_run"]

    for source_file in changed_files:
        test_candidates = _source_to_test_path(source_file)

        for test_path in test_candidates:
            if test_path not in selected:
                selected[test_path] = []
            selected[test_path].append(source_file)

    # If conftest.py changed, run all tests
    conftest_changed = any("conftest.py" in f for f in changed_files)
    if conftest_changed:
        logger.info("conftest.py changed — selecting all tests")
        if available_tests:
            for t in available_tests:
                if t not in selected:
                    selected[t] = ["conftest.py changed"]

    # If base models or schemas changed, include broader test coverage
    broad_impact_patterns = [
        r"app/models/base",
        r"app/database\.py",
        r"app/config\.py",
        r"app/main\.py",
    ]
    for source_file in changed_files:
        for pattern in broad_impact_patterns:
            if re.search(pattern, source_file):
                # Add all tests in affected module directories
                affected_modules = _get_affected_modules(changed_files)
                if available_tests:
                    for t in available_tests:
                        for mod in affected_modules:
                            if f"test_{mod}" in t and t not in selected:
                                selected[t] = [f"broad impact: {source_file}"]

    # Filter to only existing test files if available_tests provided
    if available_tests is not None:
        available_set = set(available_tests)
        filtered = {k: v for k, v in selected.items() if k in available_set}
        # If no tests matched, fall back to running all tests
        if not filtered and changed_files:
            logger.info(
                "No test mapping found for %d changed files — running all tests",
                len(changed_files),
            )
            filtered = {t: ["fallback: no mapping"] for t in available_tests}
        selected = filtered

    total_available = len(available_tests) if available_tests is not None else 0
    selected_count = len(selected)
    selection_ratio = (selected_count / total_available) if total_available > 0 else 1.0

    logger.info(
        "Test selection: %d/%d tests selected (%.0f%% reduction) for %d changed files",
        selected_count,
        total_available,
        (1 - selection_ratio) * 100,
        len(changed_files),
    )

    return SelectionResult(
        selected_tests=list(selected.keys()),
        reason=selected,
        total_tests_available=total_available,
        selection_ratio=round(selection_ratio, 3),
    )
