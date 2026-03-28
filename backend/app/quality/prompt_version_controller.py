"""Prompt Version Controller — Git-like version control for prompts.

Production AI systems need the same rigour for prompt management as for
code: versioning, diffing, environment-based deployment, and rollback.
This module provides a prompt registry with content-addressable storage,
semantic versioning, environment promotion (dev → staging → prod), and
audit trails.

Based on:
- Maxim AI "Top 5 Prompt Versioning Tools for Enterprise AI Teams 2026"
- DasRoot "Prompt Versioning: The Missing DevOps Layer in AI-Driven Ops" (2026)
- Langfuse "Prompt CMS" (2026)
- Braintrust "Environment-Based Prompt Deployment" (2026)
- Lakera "Ultimate Guide to Prompt Engineering 2026"

Key capabilities:
- Content-addressable prompt storage (hash-based deduplication)
- Semantic versioning: major.minor.patch with auto-increment rules
- Environment promotion: dev → staging → prod with quality gates
- Prompt diff: structural comparison between versions
- Rollback to any previous version with audit trail
- Metadata: author, description, model target, tags
- Quality gate: approved / pending_review / rejected / deprecated
- Batch registry report with version and environment status
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────

class PromptEnvironment(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class PromptStatus(StrEnum):
    APPROVED = "approved"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class GateDecision(StrEnum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


# ── Data classes ─────────────────────────────────────────────────────────

@dataclass
class SemanticVersion:
    """Semantic version for a prompt."""

    major: int = 1
    minor: int = 0
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def bump_patch(self) -> SemanticVersion:
        return SemanticVersion(self.major, self.minor, self.patch + 1)

    def bump_minor(self) -> SemanticVersion:
        return SemanticVersion(self.major, self.minor + 1, 0)

    def bump_major(self) -> SemanticVersion:
        return SemanticVersion(self.major + 1, 0, 0)

    def to_tuple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)


@dataclass
class PromptVersion:
    """A single versioned prompt."""

    version_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt_name: str = ""
    content: str = ""
    content_hash: str = ""
    version: SemanticVersion = field(default_factory=SemanticVersion)
    environment: PromptEnvironment = PromptEnvironment.DEV
    status: PromptStatus = PromptStatus.PENDING_REVIEW
    author: str = ""
    description: str = ""
    model_target: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    promoted_at: datetime | None = None


@dataclass
class PromptDiff:
    """Structural diff between two prompt versions."""

    old_version: str = ""
    new_version: str = ""
    old_content_hash: str = ""
    new_content_hash: str = ""
    lines_added: int = 0
    lines_removed: int = 0
    lines_changed: int = 0
    is_identical: bool = False
    change_summary: str = ""


@dataclass
class RollbackRecord:
    """Record of a rollback operation."""

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt_name: str = ""
    from_version: str = ""
    to_version: str = ""
    environment: PromptEnvironment = PromptEnvironment.DEV
    reason: str = ""
    performed_by: str = ""
    performed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class RegistryConfig:
    """Configuration for the prompt registry."""

    require_review_for_staging: bool = True
    require_review_for_prod: bool = True
    max_versions_per_prompt: int = 50
    auto_deprecate_old_versions: bool = True


@dataclass
class RegistryReport:
    """Report across all prompts in the registry."""

    total_prompts: int = 0
    total_versions: int = 0
    versions_by_environment: dict[str, int] = field(default_factory=dict)
    versions_by_status: dict[str, int] = field(default_factory=dict)
    rollback_count: int = 0
    latest_versions: dict[str, str] = field(default_factory=dict)  # prompt_name → version string


# ── Pure helpers ─────────────────────────────────────────────────────────

def _content_hash(content: str) -> str:
    """Compute content-addressable hash."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _compute_diff(old_content: str, new_content: str) -> PromptDiff:
    """Compute a simple line-level diff."""
    old_lines = set(old_content.strip().split("\n"))
    new_lines = set(new_content.strip().split("\n"))

    added = new_lines - old_lines
    removed = old_lines - new_lines
    is_identical = old_content.strip() == new_content.strip()

    return PromptDiff(
        lines_added=len(added),
        lines_removed=len(removed),
        lines_changed=len(added) + len(removed),
        is_identical=is_identical,
        change_summary=f"+{len(added)}/-{len(removed)} lines",
    )


def _can_promote(
    version: PromptVersion,
    target_env: PromptEnvironment,
    config: RegistryConfig,
) -> tuple[bool, str]:
    """Check if a version can be promoted to target environment."""
    # Must follow dev → staging → prod order
    env_order = {PromptEnvironment.DEV: 0, PromptEnvironment.STAGING: 1, PromptEnvironment.PROD: 2}
    current_ord = env_order.get(version.environment, 0)
    target_ord = env_order.get(target_env, 0)

    if target_ord <= current_ord:
        return False, f"Cannot promote from {version.environment} to {target_env}"

    if target_ord - current_ord > 1:
        return False, f"Cannot skip environments: {version.environment} → {target_env}"

    if (
        target_env == PromptEnvironment.STAGING
        and config.require_review_for_staging
        and version.status != PromptStatus.APPROVED
    ):
        return False, "Requires approved status for staging promotion"

    if (
        target_env == PromptEnvironment.PROD
        and config.require_review_for_prod
        and version.status != PromptStatus.APPROVED
    ):
        return False, "Requires approved status for prod promotion"

    return True, "OK"


# ── Main class ───────────────────────────────────────────────────────────

class PromptVersionController:
    """Git-like version control for prompts with environment promotion."""

    def __init__(self, config: RegistryConfig | None = None) -> None:
        self._config = config or RegistryConfig()
        self._versions: dict[str, list[PromptVersion]] = {}  # prompt_name → versions
        self._rollbacks: list[RollbackRecord] = []

    @property
    def config(self) -> RegistryConfig:
        return self._config

    def register_prompt(
        self,
        prompt_name: str,
        content: str,
        author: str = "",
        description: str = "",
        model_target: str = "",
        tags: list[str] | None = None,
        bump: str = "patch",  # "patch", "minor", "major"
    ) -> PromptVersion:
        """Register a new prompt version (auto-increments version)."""
        c_hash = _content_hash(content)

        # Check for duplicate content
        existing = self._versions.get(prompt_name, [])
        for v in existing:
            if v.content_hash == c_hash:
                logger.info("Duplicate content for %s, returning existing version", prompt_name)
                return v

        # Determine version
        if existing:
            latest = existing[-1]
            if bump == "major":
                version = latest.version.bump_major()
            elif bump == "minor":
                version = latest.version.bump_minor()
            else:
                version = latest.version.bump_patch()
        else:
            version = SemanticVersion(1, 0, 0)

        pv = PromptVersion(
            prompt_name=prompt_name,
            content=content,
            content_hash=c_hash,
            version=version,
            author=author,
            description=description,
            model_target=model_target,
            tags=tags or [],
        )

        self._versions.setdefault(prompt_name, []).append(pv)

        # Auto-deprecate old versions
        if self._config.auto_deprecate_old_versions and len(self._versions[prompt_name]) > 2:
            for old in self._versions[prompt_name][:-2]:
                if old.status not in (PromptStatus.DEPRECATED, PromptStatus.REJECTED):
                    old.status = PromptStatus.DEPRECATED

        logger.info("Registered %s v%s (hash=%s)", prompt_name, version, c_hash)
        return pv

    def approve(self, version_id: str) -> PromptVersion | None:
        """Approve a prompt version for promotion."""
        pv = self._find_version(version_id)
        if pv is None:
            return None
        pv.status = PromptStatus.APPROVED
        return pv

    def reject(self, version_id: str, reason: str = "") -> PromptVersion | None:
        """Reject a prompt version."""
        pv = self._find_version(version_id)
        if pv is None:
            return None
        pv.status = PromptStatus.REJECTED
        logger.info("Rejected %s v%s: %s", pv.prompt_name, pv.version, reason)
        return pv

    def promote(
        self,
        version_id: str,
        target_env: PromptEnvironment,
    ) -> tuple[PromptVersion | None, str]:
        """Promote a prompt version to the next environment."""
        pv = self._find_version(version_id)
        if pv is None:
            return None, "Version not found"

        can, reason = _can_promote(pv, target_env, self._config)
        if not can:
            return None, reason

        pv.environment = target_env
        pv.promoted_at = datetime.now(UTC)
        logger.info("Promoted %s v%s to %s", pv.prompt_name, pv.version, target_env)
        return pv, "OK"

    def rollback(
        self,
        prompt_name: str,
        environment: PromptEnvironment,
        reason: str = "",
        performed_by: str = "",
    ) -> tuple[PromptVersion | None, str]:
        """Rollback to the previous version in the given environment."""
        versions = [
            v for v in self._versions.get(prompt_name, [])
            if v.environment == environment and v.status != PromptStatus.REJECTED
        ]

        if len(versions) < 2:
            return None, "No previous version to rollback to"

        current = versions[-1]
        previous = versions[-2]

        # Deprecate current
        current.status = PromptStatus.DEPRECATED

        record = RollbackRecord(
            prompt_name=prompt_name,
            from_version=str(current.version),
            to_version=str(previous.version),
            environment=environment,
            reason=reason,
            performed_by=performed_by,
        )
        self._rollbacks.append(record)

        logger.info(
            "Rolled back %s from v%s to v%s in %s",
            prompt_name, current.version, previous.version, environment,
        )
        return previous, "OK"

    def diff(self, version_id_a: str, version_id_b: str) -> PromptDiff | None:
        """Compute diff between two prompt versions."""
        a = self._find_version(version_id_a)
        b = self._find_version(version_id_b)
        if a is None or b is None:
            return None

        d = _compute_diff(a.content, b.content)
        d.old_version = str(a.version)
        d.new_version = str(b.version)
        d.old_content_hash = a.content_hash
        d.new_content_hash = b.content_hash
        return d

    def get_latest(
        self,
        prompt_name: str,
        environment: PromptEnvironment | None = None,
    ) -> PromptVersion | None:
        """Get the latest version of a prompt, optionally filtered by env."""
        versions = self._versions.get(prompt_name, [])
        if environment:
            versions = [v for v in versions if v.environment == environment]
        return versions[-1] if versions else None

    def list_versions(self, prompt_name: str) -> list[PromptVersion]:
        """List all versions of a prompt."""
        return list(self._versions.get(prompt_name, []))

    def registry_report(self) -> RegistryReport:
        """Generate a report across all prompts."""
        total_versions = sum(len(v) for v in self._versions.values())

        env_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        latest: dict[str, str] = {}

        for name, versions in self._versions.items():
            if versions:
                latest[name] = str(versions[-1].version)
            for v in versions:
                env_counts[v.environment] = env_counts.get(v.environment, 0) + 1
                status_counts[v.status] = status_counts.get(v.status, 0) + 1

        return RegistryReport(
            total_prompts=len(self._versions),
            total_versions=total_versions,
            versions_by_environment=env_counts,
            versions_by_status=status_counts,
            rollback_count=len(self._rollbacks),
            latest_versions=latest,
        )

    def _find_version(self, version_id: str) -> PromptVersion | None:
        """Find a version by ID across all prompts."""
        for versions in self._versions.values():
            for v in versions:
                if v.version_id == version_id:
                    return v
        return None
