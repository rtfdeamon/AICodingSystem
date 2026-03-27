"""Self-Healing Tests — auto-fix broken tests on UI/env changes.

When tests break due to environmental changes (not code bugs),
the self-healing module:
1. Classifies failures as environmental vs logic bugs
2. Generates targeted fixes for environmental failures
3. Applies fixes and re-validates
4. Tracks healing patterns for continuous improvement
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class FailureCategory(StrEnum):
    """Classification of test failure root cause."""

    SELECTOR_CHANGE = "selector_change"  # UI element moved/renamed
    API_CHANGE = "api_change"  # API response shape changed
    ENV_CONFIG = "env_config"  # Environment variable / config mismatch
    TIMING = "timing"  # Race condition / timeout
    DEPENDENCY = "dependency"  # External dependency unavailable
    LOGIC_BUG = "logic_bug"  # Actual code bug (don't auto-fix)
    UNKNOWN = "unknown"


@dataclass
class FailureClassification:
    """Result of classifying a test failure."""

    category: FailureCategory
    confidence: float  # 0.0 - 1.0
    evidence: str = ""
    is_healable: bool = False


@dataclass
class HealingAction:
    """A proposed fix for a broken test."""

    test_file: str
    test_name: str
    category: FailureCategory
    old_content: str = ""
    new_content: str = ""
    description: str = ""
    applied: bool = False


@dataclass
class HealingResult:
    """Result of a self-healing attempt."""

    total_failures: int = 0
    classified: int = 0
    healable: int = 0
    healed: int = 0
    skipped_logic_bugs: int = 0
    actions: list[HealingAction] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


# ── Healing history for learning ───────────────────────────────────────

_healing_history: list[HealingResult] = []


def clear_healing_history() -> None:
    """Clear healing history (for testing)."""
    _healing_history.clear()


# ── Failure classification ─────────────────────────────────────────────

# Patterns that indicate environmental failures (not logic bugs)
_SELECTOR_PATTERNS = [
    re.compile(r"(?:Unable to find|not found).*(?:element|selector|role|testid)", re.IGNORECASE),
    re.compile(
        r"(?:querySelector|getBy|findBy|queryBy)\w*.*(?:null|undefined|not found)",
        re.IGNORECASE,
    ),
    re.compile(r"Expected.*to (?:be in|have).*document", re.IGNORECASE),
]

_API_PATTERNS = [
    re.compile(r"(?:TypeError|KeyError):.*(?:undefined|null|'?\w+'?) is not", re.IGNORECASE),
    re.compile(r"(?:status code|response|HTTP)\s*(?:was|:)\s*(?:4\d\d|5\d\d)", re.IGNORECASE),
    re.compile(r"(?:schema|validation).*(?:error|failed|mismatch)", re.IGNORECASE),
]

_ENV_PATTERNS = [
    re.compile(r"(?:ECONNREFUSED|ENOTFOUND|ETIMEDOUT)", re.IGNORECASE),
    re.compile(r"(?:env|environment|config).*(?:not set|missing|undefined)", re.IGNORECASE),
    re.compile(r"(?:database|redis|connection).*(?:refused|timeout|unavailable)", re.IGNORECASE),
]

_TIMING_PATTERNS = [
    re.compile(r"(?:timeout|timed out|exceeded.*time)", re.IGNORECASE),
    re.compile(r"(?:waitFor|act\(\)).*(?:not.*resolved|exceeded)", re.IGNORECASE),
    re.compile(r"(?:async|promise).*(?:timeout|not.*called)", re.IGNORECASE),
]

_DEPENDENCY_PATTERNS = [
    re.compile(r"(?:ModuleNotFoundError|Cannot find module|ImportError)", re.IGNORECASE),
    re.compile(r"(?:package|module|library).*(?:not installed|missing)", re.IGNORECASE),
]


def classify_failure(
    test_name: str,
    error_message: str,
    stack_trace: str = "",
) -> FailureClassification:
    """Classify a test failure to determine if it's auto-healable.

    Parameters
    ----------
    test_name:
        Name of the failing test.
    error_message:
        The error message or assertion failure.
    stack_trace:
        Optional full stack trace.
    """
    full_text = f"{error_message}\n{stack_trace}"

    # Check patterns in priority order
    for pattern in _SELECTOR_PATTERNS:
        if pattern.search(full_text):
            return FailureClassification(
                category=FailureCategory.SELECTOR_CHANGE,
                confidence=0.85,
                evidence=pattern.pattern[:100],
                is_healable=True,
            )

    for pattern in _TIMING_PATTERNS:
        if pattern.search(full_text):
            return FailureClassification(
                category=FailureCategory.TIMING,
                confidence=0.80,
                evidence=pattern.pattern[:100],
                is_healable=True,
            )

    for pattern in _API_PATTERNS:
        if pattern.search(full_text):
            return FailureClassification(
                category=FailureCategory.API_CHANGE,
                confidence=0.75,
                evidence=pattern.pattern[:100],
                is_healable=True,
            )

    for pattern in _DEPENDENCY_PATTERNS:
        if pattern.search(full_text):
            return FailureClassification(
                category=FailureCategory.DEPENDENCY,
                confidence=0.90,
                evidence=pattern.pattern[:100],
                is_healable=False,  # Dependency issues need human resolution
            )

    for pattern in _ENV_PATTERNS:
        if pattern.search(full_text):
            return FailureClassification(
                category=FailureCategory.ENV_CONFIG,
                confidence=0.70,
                evidence=pattern.pattern[:100],
                is_healable=True,
            )

    # Check for assertion errors (likely logic bugs)
    if re.search(r"(?:AssertionError|assert|expect\()", full_text, re.IGNORECASE):
        return FailureClassification(
            category=FailureCategory.LOGIC_BUG,
            confidence=0.60,
            evidence="Assertion failure detected",
            is_healable=False,
        )

    return FailureClassification(
        category=FailureCategory.UNKNOWN,
        confidence=0.3,
        evidence="No matching pattern",
        is_healable=False,
    )


def generate_healing_action(
    test_name: str,
    test_file: str,
    classification: FailureClassification,
    error_message: str,
) -> HealingAction | None:
    """Generate a healing action based on failure classification.

    Returns None if the failure is not auto-healable.
    """
    if not classification.is_healable:
        return None

    if classification.category == FailureCategory.SELECTOR_CHANGE:
        return HealingAction(
            test_file=test_file,
            test_name=test_name,
            category=classification.category,
            description=(
                "Update test selector to match current UI structure. "
                "Recommend using data-testid attributes for stability."
            ),
        )

    if classification.category == FailureCategory.TIMING:
        return HealingAction(
            test_file=test_file,
            test_name=test_name,
            category=classification.category,
            description=(
                "Increase timeout or add explicit wait for async operation. "
                "Consider using waitFor with appropriate timeout."
            ),
        )

    if classification.category == FailureCategory.API_CHANGE:
        return HealingAction(
            test_file=test_file,
            test_name=test_name,
            category=classification.category,
            description=(
                "Update test mock/fixture to match new API response shape. "
                "Sync test expectations with current API contract."
            ),
        )

    if classification.category == FailureCategory.ENV_CONFIG:
        return HealingAction(
            test_file=test_file,
            test_name=test_name,
            category=classification.category,
            description=(
                "Add environment variable setup in test fixture or "
                "update conftest.py with required configuration."
            ),
        )

    return None


def build_healing_prompt(
    actions: list[HealingAction],
    test_content: str = "",
) -> str:
    """Build a prompt for the AI agent to apply healing fixes.

    Parameters
    ----------
    actions:
        List of healing actions to apply.
    test_content:
        Content of the test file for context.
    """
    parts = [
        "## Self-Healing Test Fix Request\n\n",
        "The following tests are failing due to environmental changes, "
        "NOT logic bugs. Fix only the test infrastructure, not the application code.\n\n",
    ]

    for i, action in enumerate(actions, 1):
        parts.append(f"### Fix {i}: {action.test_name}\n")
        parts.append(f"- **File:** {action.test_file}\n")
        parts.append(f"- **Category:** {action.category.value}\n")
        parts.append(f"- **Action:** {action.description}\n\n")

    if test_content:
        parts.append(f"### Current Test File Content\n```\n{test_content[:10000]}\n```\n")

    parts.append(
        "\n### Rules\n"
        "1. Only modify test code, never application code\n"
        "2. Prefer data-testid selectors over DOM structure queries\n"
        "3. Add appropriate timeouts for async operations\n"
        "4. Update mock data to match current API contracts\n"
        "5. Keep test intent unchanged — only fix the mechanism\n"
    )

    return "".join(parts)


def process_failures(
    failures: list[dict[str, str]],
    *,
    auto_heal_threshold: float = 0.7,
) -> HealingResult:
    """Process test failures and generate healing actions.

    Parameters
    ----------
    failures:
        List of failure dicts with keys: test_name, error_message, file, stack_trace.
    auto_heal_threshold:
        Minimum confidence for auto-healing (0.0-1.0).
    """
    result = HealingResult(total_failures=len(failures))

    for failure in failures:
        test_name = failure.get("test_name", "unknown")
        error_msg = failure.get("error_message", "")
        stack_trace = failure.get("stack_trace", "")
        test_file = failure.get("file", "")

        classification = classify_failure(test_name, error_msg, stack_trace)
        result.classified += 1

        if classification.category == FailureCategory.LOGIC_BUG:
            result.skipped_logic_bugs += 1
            continue

        if classification.is_healable and classification.confidence >= auto_heal_threshold:
            action = generate_healing_action(
                test_name, test_file, classification, error_msg
            )
            if action:
                result.healable += 1
                result.actions.append(action)

    _healing_history.append(result)
    return result


def get_healing_stats() -> dict[str, Any]:
    """Get aggregated self-healing statistics."""
    if not _healing_history:
        return {
            "total_sessions": 0,
            "total_failures_processed": 0,
            "total_healed": 0,
            "healing_rate": 0.0,
            "category_breakdown": {},
        }

    total_failures = sum(h.total_failures for h in _healing_history)
    total_healable = sum(h.healable for h in _healing_history)
    total_healed = sum(h.healed for h in _healing_history)

    category_counts: dict[str, int] = {}
    for h in _healing_history:
        for action in h.actions:
            cat = action.category.value
            category_counts[cat] = category_counts.get(cat, 0) + 1

    return {
        "total_sessions": len(_healing_history),
        "total_failures_processed": total_failures,
        "total_healable": total_healable,
        "total_healed": total_healed,
        "healing_rate": round(
            (total_healed / total_healable * 100) if total_healable > 0 else 0.0, 1
        ),
        "category_breakdown": category_counts,
    }


def healing_result_to_json(result: HealingResult) -> dict[str, Any]:
    """Serialize a HealingResult to JSON-compatible dict."""
    return {
        "total_failures": result.total_failures,
        "classified": result.classified,
        "healable": result.healable,
        "healed": result.healed,
        "skipped_logic_bugs": result.skipped_logic_bugs,
        "actions": [
            {
                "test_file": a.test_file,
                "test_name": a.test_name,
                "category": a.category.value,
                "description": a.description,
                "applied": a.applied,
            }
            for a in result.actions
        ],
    }
