"""Prompt versioning and lifecycle management.

Tracks prompt versions across environments (dev → staging → production),
enforces evaluation-score gates before promotion, and supports rollback
to previous versions.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


class PromptEnvironment(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


class VersionBumpType(StrEnum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# Promotion order used by promote_prompt
_PROMOTION_ORDER: list[PromptEnvironment] = [
    PromptEnvironment.DEV,
    PromptEnvironment.STAGING,
    PromptEnvironment.PRODUCTION,
]


@dataclass
class PromptVersion:
    """A single versioned prompt."""

    id: uuid.UUID
    name: str
    version: str
    content: str
    author: str
    change_rationale: str
    model_versions: list[str]
    environment: PromptEnvironment
    eval_score: float
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    rollback_from: str | None = None


# ── In-memory prompt registry (production would use DB table) ─────────────

_prompt_registry: dict[str, list[PromptVersion]] = {}


def register_prompt(
    name: str,
    content: str,
    author: str,
    change_rationale: str,
    model_versions: list[str],
    environment: str = "dev",
) -> PromptVersion:
    """Register a new prompt version.

    The version string is automatically bumped (patch) from the latest
    version for the given name, or starts at ``1.0.0`` if this is the
    first registration.

    Returns
    -------
    The newly created PromptVersion.
    """
    env = PromptEnvironment(environment)
    existing = _prompt_registry.get(name, [])

    if existing:
        latest = max(existing, key=lambda pv: parse_semver(pv.version))
        version = bump_version(latest.version, VersionBumpType.PATCH)
    else:
        version = "1.0.0"

    pv = PromptVersion(
        id=uuid.uuid4(),
        name=name,
        version=version,
        content=content,
        author=author,
        change_rationale=change_rationale,
        model_versions=model_versions,
        environment=env,
        eval_score=0.0,
    )

    _prompt_registry.setdefault(name, []).append(pv)

    logger.info(
        "Prompt registered: name=%s version=%s env=%s",
        name,
        version,
        env.value,
    )
    return pv


def get_active_prompt(
    name: str,
    environment: str,
) -> PromptVersion | None:
    """Return the latest version of *name* in the given environment.

    Returns ``None`` if no version exists for that name/environment pair.
    """
    env = PromptEnvironment(environment)
    versions = _prompt_registry.get(name, [])
    env_versions = [pv for pv in versions if pv.environment == env]
    if not env_versions:
        return None
    return max(env_versions, key=lambda pv: parse_semver(pv.version))


def promote_prompt(
    name: str,
    version: str,
    target_env: str,
    min_eval_score: float = 0.8,
) -> PromptVersion:
    """Promote a prompt version to *target_env*.

    A new PromptVersion entry is created in the target environment with
    the same content.  The promotion is rejected if the source version's
    ``eval_score`` is below *min_eval_score*.

    Raises
    ------
    ValueError
        If the prompt/version is not found, the eval score is too low,
        or the target environment is invalid.
    """
    target = PromptEnvironment(target_env)
    versions = _prompt_registry.get(name, [])
    source = next((pv for pv in versions if pv.version == version), None)

    if source is None:
        raise ValueError(f"Prompt '{name}' version '{version}' not found")

    if source.eval_score < min_eval_score:
        raise ValueError(
            f"Eval score {source.eval_score:.2f} below minimum {min_eval_score:.2f}"
        )

    promoted = PromptVersion(
        id=uuid.uuid4(),
        name=source.name,
        version=source.version,
        content=source.content,
        author=source.author,
        change_rationale=source.change_rationale,
        model_versions=source.model_versions,
        environment=target,
        eval_score=source.eval_score,
    )

    _prompt_registry.setdefault(name, []).append(promoted)

    logger.info(
        "Prompt promoted: name=%s version=%s -> %s",
        name,
        version,
        target.value,
    )
    return promoted


def rollback_prompt(
    name: str,
    environment: str,
) -> PromptVersion | None:
    """Roll back to the previous version in *environment*.

    Creates a new registry entry that copies the previous version and
    records a ``rollback_from`` reference.  Returns ``None`` if there
    are fewer than two versions in the environment.
    """
    env = PromptEnvironment(environment)
    versions = _prompt_registry.get(name, [])
    env_versions = sorted(
        [pv for pv in versions if pv.environment == env],
        key=lambda pv: parse_semver(pv.version),
    )

    if len(env_versions) < 2:
        return None

    current = env_versions[-1]
    previous = env_versions[-2]

    rolled_back = PromptVersion(
        id=uuid.uuid4(),
        name=previous.name,
        version=previous.version,
        content=previous.content,
        author=previous.author,
        change_rationale=f"Rollback from {current.version}",
        model_versions=previous.model_versions,
        environment=env,
        eval_score=previous.eval_score,
        rollback_from=current.version,
    )

    _prompt_registry[name].append(rolled_back)

    logger.info(
        "Prompt rolled back: name=%s env=%s from=%s to=%s",
        name,
        env.value,
        current.version,
        previous.version,
    )
    return rolled_back


def get_prompt_history(name: str) -> list[PromptVersion]:
    """Return the full version history for *name*, oldest first."""
    versions = _prompt_registry.get(name, [])
    return sorted(versions, key=lambda pv: pv.created_at)


def parse_semver(version: str) -> tuple[int, int, int]:
    """Parse a semver string ``"major.minor.patch"`` into a tuple.

    Raises
    ------
    ValueError
        If the string does not match ``X.Y.Z`` format.
    """
    m = _SEMVER_RE.match(version)
    if not m:
        raise ValueError(f"Invalid semver: '{version}'")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump_version(current: str, bump_type: str) -> str:
    """Bump a semver string by the given *bump_type*.

    Parameters
    ----------
    current:
        Current version string, e.g. ``"1.2.3"``.
    bump_type:
        One of ``"major"``, ``"minor"``, ``"patch"``.

    Returns
    -------
    The bumped version string.
    """
    bt = VersionBumpType(bump_type)
    major, minor, patch = parse_semver(current)

    if bt == VersionBumpType.MAJOR:
        return f"{major + 1}.0.0"
    if bt == VersionBumpType.MINOR:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def clear_prompt_registry() -> None:
    """Clear all stored prompts (for testing)."""
    _prompt_registry.clear()


def prompt_version_to_json(pv: PromptVersion) -> dict:
    """Serialize a PromptVersion to a JSON-compatible dict."""
    return {
        "id": str(pv.id),
        "name": pv.name,
        "version": pv.version,
        "content": pv.content,
        "author": pv.author,
        "change_rationale": pv.change_rationale,
        "model_versions": pv.model_versions,
        "environment": pv.environment.value,
        "eval_score": pv.eval_score,
        "created_at": pv.created_at.isoformat(),
        "rollback_from": pv.rollback_from,
    }
