"""Automated Evaluation Tests — baseline regression detection for agent outputs.

Runs evaluation tests against AI agent outputs to detect quality regression:
- Stores baseline outputs for known prompts
- Compares new outputs against baselines
- Detects quality degradation (structure, completeness, accuracy)
- Integrates with CI/CD pipeline for automated gating
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class EvalStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    DEGRADED = "degraded"  # Quality decreased but still acceptable
    SKIPPED = "skipped"


class EvalDimension(StrEnum):
    """Dimensions on which agent output is evaluated."""

    STRUCTURE = "structure"  # JSON structure, required fields
    COMPLETENESS = "completeness"  # All expected elements present
    ACCURACY = "accuracy"  # Correct values and decisions
    CONSISTENCY = "consistency"  # Stable across runs
    SAFETY = "safety"  # No PII, no harmful content


@dataclass
class EvalCriterion:
    """A single evaluation criterion for an agent output."""

    dimension: EvalDimension
    name: str
    description: str
    check_fn_name: str = ""  # Name of the check function
    weight: float = 1.0  # Importance weight (0.0-1.0)


@dataclass
class EvalResult:
    """Result of evaluating a single criterion."""

    criterion: EvalCriterion
    status: EvalStatus
    score: float = 0.0  # 0.0 - 1.0
    message: str = ""
    baseline_value: str = ""
    actual_value: str = ""


@dataclass
class EvalSuiteResult:
    """Result of running a full evaluation suite."""

    eval_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    agent_name: str = ""
    action: str = ""
    prompt_hash: str = ""
    overall_status: EvalStatus = EvalStatus.PASSED
    overall_score: float = 0.0
    results: list[EvalResult] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int = 0


# ── Baseline Storage (in-memory MVP) ─────────────────────────────────

@dataclass
class EvalBaseline:
    """Stored baseline for an agent output."""

    prompt_hash: str
    agent_name: str
    action: str
    expected_structure: dict[str, Any] = field(default_factory=dict)
    expected_fields: list[str] = field(default_factory=list)
    min_length: int = 0
    max_length: int = 0
    expected_patterns: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


_baselines: dict[str, EvalBaseline] = {}
_eval_history: list[EvalSuiteResult] = []


def clear_eval_data() -> None:
    """Clear baselines and history (for testing)."""
    _baselines.clear()
    _eval_history.clear()


def compute_prompt_hash(prompt: str) -> str:
    """Compute a stable hash for a prompt (for baseline matching)."""
    # Normalize whitespace for stable hashing
    normalized = re.sub(r"\s+", " ", prompt.strip())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


# ── Baseline Management ──────────────────────────────────────────────


def register_baseline(
    prompt: str,
    agent_name: str,
    action: str,
    *,
    expected_structure: dict[str, Any] | None = None,
    expected_fields: list[str] | None = None,
    min_length: int = 0,
    max_length: int = 100000,
    expected_patterns: list[str] | None = None,
) -> EvalBaseline:
    """Register a baseline for an agent prompt.

    Parameters
    ----------
    prompt:
        The prompt text (hashed for matching).
    agent_name:
        Agent name (e.g., "review_agent").
    action:
        Action type (e.g., "code_review").
    expected_structure:
        Expected JSON structure with type hints.
    expected_fields:
        List of required field names in output.
    min_length:
        Minimum acceptable output length.
    max_length:
        Maximum acceptable output length.
    expected_patterns:
        Regex patterns expected in output.
    """
    prompt_hash = compute_prompt_hash(prompt)
    baseline = EvalBaseline(
        prompt_hash=prompt_hash,
        agent_name=agent_name,
        action=action,
        expected_structure=expected_structure or {},
        expected_fields=expected_fields or [],
        min_length=min_length,
        max_length=max_length,
        expected_patterns=expected_patterns or [],
    )
    _baselines[prompt_hash] = baseline

    logger.info(
        "Baseline registered: agent=%s action=%s hash=%s",
        agent_name,
        action,
        prompt_hash,
    )
    return baseline


def get_baseline(prompt: str) -> EvalBaseline | None:
    """Get the baseline for a prompt, if one exists."""
    return _baselines.get(compute_prompt_hash(prompt))


# ── Evaluation Checks ────────────────────────────────────────────────


def check_structure(output: str, baseline: EvalBaseline) -> EvalResult:
    """Check if output has expected JSON structure."""
    criterion = EvalCriterion(
        dimension=EvalDimension.STRUCTURE,
        name="json_structure",
        description="Output must be valid JSON with expected structure",
    )

    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        # Not JSON — check if it's expected to be
        if baseline.expected_structure:
            return EvalResult(
                criterion=criterion,
                status=EvalStatus.FAILED,
                score=0.0,
                message="Output is not valid JSON",
            )
        return EvalResult(
            criterion=criterion,
            status=EvalStatus.PASSED,
            score=1.0,
            message="Non-JSON output accepted (no structure baseline)",
        )

    if not baseline.expected_structure:
        return EvalResult(
            criterion=criterion,
            status=EvalStatus.PASSED,
            score=1.0,
            message="Valid JSON (no structure baseline to compare)",
        )

    # Check top-level keys
    expected_keys = set(baseline.expected_structure.keys())
    actual_keys = set(data.keys()) if isinstance(data, dict) else set()
    missing = expected_keys - actual_keys

    if missing:
        score = 1.0 - (len(missing) / len(expected_keys))
        return EvalResult(
            criterion=criterion,
            status=EvalStatus.DEGRADED if score > 0.5 else EvalStatus.FAILED,
            score=max(score, 0.0),
            message=f"Missing keys: {', '.join(sorted(missing))}",
            baseline_value=str(sorted(expected_keys)),
            actual_value=str(sorted(actual_keys)),
        )

    return EvalResult(
        criterion=criterion,
        status=EvalStatus.PASSED,
        score=1.0,
        message="All expected keys present",
    )


def check_completeness(output: str, baseline: EvalBaseline) -> EvalResult:
    """Check if output contains all expected fields/elements."""
    criterion = EvalCriterion(
        dimension=EvalDimension.COMPLETENESS,
        name="field_completeness",
        description="Output must contain all required fields",
    )

    if not baseline.expected_fields:
        return EvalResult(
            criterion=criterion,
            status=EvalStatus.PASSED,
            score=1.0,
            message="No field requirements defined",
        )

    found = 0
    missing_fields: list[str] = []
    for field_name in baseline.expected_fields:
        if field_name in output:
            found += 1
        else:
            missing_fields.append(field_name)

    total = len(baseline.expected_fields)
    score = found / total if total > 0 else 1.0

    if missing_fields:
        return EvalResult(
            criterion=criterion,
            status=EvalStatus.DEGRADED if score >= 0.7 else EvalStatus.FAILED,
            score=score,
            message=f"Missing fields: {', '.join(missing_fields[:5])}",
        )

    return EvalResult(
        criterion=criterion,
        status=EvalStatus.PASSED,
        score=1.0,
        message="All required fields present",
    )


def check_length(output: str, baseline: EvalBaseline) -> EvalResult:
    """Check if output length is within expected bounds."""
    criterion = EvalCriterion(
        dimension=EvalDimension.ACCURACY,
        name="output_length",
        description="Output length must be within expected range",
    )

    length = len(output)

    if length < baseline.min_length:
        return EvalResult(
            criterion=criterion,
            status=EvalStatus.FAILED,
            score=length / baseline.min_length if baseline.min_length > 0 else 0.0,
            message=f"Output too short: {length} < {baseline.min_length}",
            baseline_value=f"min={baseline.min_length}",
            actual_value=str(length),
        )

    if length > baseline.max_length:
        return EvalResult(
            criterion=criterion,
            status=EvalStatus.DEGRADED,
            score=baseline.max_length / length if length > 0 else 0.0,
            message=f"Output too long: {length} > {baseline.max_length}",
            baseline_value=f"max={baseline.max_length}",
            actual_value=str(length),
        )

    return EvalResult(
        criterion=criterion,
        status=EvalStatus.PASSED,
        score=1.0,
        message=f"Length {length} within bounds [{baseline.min_length}, {baseline.max_length}]",
    )


def check_patterns(output: str, baseline: EvalBaseline) -> EvalResult:
    """Check if output matches expected regex patterns."""
    criterion = EvalCriterion(
        dimension=EvalDimension.CONSISTENCY,
        name="pattern_matching",
        description="Output must match expected patterns",
    )

    if not baseline.expected_patterns:
        return EvalResult(
            criterion=criterion,
            status=EvalStatus.PASSED,
            score=1.0,
            message="No patterns to check",
        )

    matched = 0
    unmatched: list[str] = []
    for pattern in baseline.expected_patterns:
        try:
            if re.search(pattern, output, re.MULTILINE):
                matched += 1
            else:
                unmatched.append(pattern)
        except re.error:
            logger.warning("Invalid regex pattern in baseline: %s", pattern)
            matched += 1  # Don't penalize for bad baseline patterns

    total = len(baseline.expected_patterns)
    score = matched / total if total > 0 else 1.0

    if unmatched:
        return EvalResult(
            criterion=criterion,
            status=EvalStatus.DEGRADED if score >= 0.5 else EvalStatus.FAILED,
            score=score,
            message=f"Unmatched patterns: {len(unmatched)}/{total}",
        )

    return EvalResult(
        criterion=criterion,
        status=EvalStatus.PASSED,
        score=1.0,
        message=f"All {total} patterns matched",
    )


# ── Full Evaluation Suite ────────────────────────────────────────────


def evaluate_output(
    output: str,
    prompt: str,
    agent_name: str,
    action: str,
    *,
    baseline: EvalBaseline | None = None,
) -> EvalSuiteResult:
    """Run the full evaluation suite against an agent output.

    Parameters
    ----------
    output:
        The agent's output to evaluate.
    prompt:
        The prompt that generated the output.
    agent_name:
        Agent name.
    action:
        Action type.
    baseline:
        Optional explicit baseline. If None, looks up by prompt hash.
    """
    if baseline is None:
        baseline = get_baseline(prompt)

    suite = EvalSuiteResult(
        agent_name=agent_name,
        action=action,
        prompt_hash=compute_prompt_hash(prompt),
    )

    if baseline is None:
        suite.overall_status = EvalStatus.SKIPPED
        suite.overall_score = 0.0
        suite.results.append(EvalResult(
            criterion=EvalCriterion(
                dimension=EvalDimension.STRUCTURE,
                name="baseline_check",
                description="Baseline existence check",
            ),
            status=EvalStatus.SKIPPED,
            message="No baseline registered for this prompt",
        ))
        _eval_history.append(suite)
        return suite

    # Run all checks
    checks = [
        check_structure(output, baseline),
        check_completeness(output, baseline),
        check_length(output, baseline),
        check_patterns(output, baseline),
    ]
    suite.results = checks

    # Calculate overall score (weighted average)
    total_weight = sum(r.criterion.weight for r in checks)
    if total_weight > 0:
        suite.overall_score = round(
            sum(r.score * r.criterion.weight for r in checks) / total_weight,
            3,
        )

    # Determine overall status
    failed_count = sum(1 for r in checks if r.status == EvalStatus.FAILED)
    degraded_count = sum(1 for r in checks if r.status == EvalStatus.DEGRADED)

    if failed_count > 0:
        suite.overall_status = EvalStatus.FAILED
    elif degraded_count > 0:
        suite.overall_status = EvalStatus.DEGRADED
    else:
        suite.overall_status = EvalStatus.PASSED

    _eval_history.append(suite)

    logger.info(
        "Eval complete: agent=%s action=%s status=%s score=%.2f",
        agent_name,
        action,
        suite.overall_status.value,
        suite.overall_score,
    )
    return suite


def get_eval_stats() -> dict[str, Any]:
    """Get aggregated evaluation statistics."""
    if not _eval_history:
        return {
            "total_evals": 0,
            "passed": 0,
            "failed": 0,
            "degraded": 0,
            "pass_rate": 0.0,
            "avg_score": 0.0,
        }

    passed = sum(1 for e in _eval_history if e.overall_status == EvalStatus.PASSED)
    failed = sum(1 for e in _eval_history if e.overall_status == EvalStatus.FAILED)
    degraded = sum(1 for e in _eval_history if e.overall_status == EvalStatus.DEGRADED)
    total = len(_eval_history)
    avg_score = sum(e.overall_score for e in _eval_history) / total

    return {
        "total_evals": total,
        "passed": passed,
        "failed": failed,
        "degraded": degraded,
        "pass_rate": round(passed / total * 100, 1) if total > 0 else 0.0,
        "avg_score": round(avg_score, 3),
    }


def eval_result_to_json(result: EvalSuiteResult) -> dict[str, Any]:
    """Serialize an EvalSuiteResult to JSON-compatible dict."""
    return {
        "eval_id": result.eval_id,
        "agent_name": result.agent_name,
        "action": result.action,
        "prompt_hash": result.prompt_hash,
        "overall_status": result.overall_status.value,
        "overall_score": result.overall_score,
        "results": [
            {
                "dimension": r.criterion.dimension.value,
                "name": r.criterion.name,
                "status": r.status.value,
                "score": r.score,
                "message": r.message,
            }
            for r in result.results
        ],
        "timestamp": result.timestamp.isoformat(),
    }
