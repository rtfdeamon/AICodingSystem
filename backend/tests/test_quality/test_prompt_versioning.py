"""Tests for prompt versioning and lifecycle management module."""

from __future__ import annotations

import uuid

import pytest

from app.quality.prompt_versioning import (
    PromptEnvironment,
    VersionBumpType,
    bump_version,
    clear_prompt_registry,
    get_active_prompt,
    get_prompt_history,
    parse_semver,
    promote_prompt,
    prompt_version_to_json,
    register_prompt,
    rollback_prompt,
)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Clear prompt registry before each test."""
    clear_prompt_registry()


# ── Registration ──────────────────────────────────────────────────────────


class TestRegisterPrompt:
    def test_register_first_prompt(self) -> None:
        pv = register_prompt("greet", "Hello {{name}}", "alice", "initial", ["gpt-4"])
        assert pv.name == "greet"
        assert pv.version == "1.0.0"
        assert pv.environment == PromptEnvironment.DEV
        assert isinstance(pv.id, uuid.UUID)

    def test_register_bumps_patch(self) -> None:
        register_prompt("greet", "v1", "alice", "first", ["gpt-4"])
        pv2 = register_prompt("greet", "v2", "alice", "second", ["gpt-4"])
        assert pv2.version == "1.0.1"

    def test_register_consecutive_bumps(self) -> None:
        register_prompt("greet", "v1", "alice", "first", ["gpt-4"])
        register_prompt("greet", "v2", "alice", "second", ["gpt-4"])
        pv3 = register_prompt("greet", "v3", "alice", "third", ["gpt-4"])
        assert pv3.version == "1.0.2"

    def test_register_with_explicit_environment(self) -> None:
        pv = register_prompt("greet", "Hello", "alice", "init", ["gpt-4"], environment="staging")
        assert pv.environment == PromptEnvironment.STAGING

    def test_register_stores_model_versions(self) -> None:
        pv = register_prompt("greet", "Hello", "alice", "init", ["gpt-4", "claude-3"])
        assert pv.model_versions == ["gpt-4", "claude-3"]


# ── Retrieval ─────────────────────────────────────────────────────────────


class TestGetActivePrompt:
    def test_returns_latest_version(self) -> None:
        register_prompt("greet", "v1", "alice", "first", ["gpt-4"])
        register_prompt("greet", "v2", "alice", "second", ["gpt-4"])
        active = get_active_prompt("greet", "dev")
        assert active is not None
        assert active.version == "1.0.1"
        assert active.content == "v2"

    def test_returns_none_for_unknown(self) -> None:
        result = get_active_prompt("nonexistent", "dev")
        assert result is None

    def test_returns_none_for_wrong_environment(self) -> None:
        register_prompt("greet", "v1", "alice", "init", ["gpt-4"])
        result = get_active_prompt("greet", "production")
        assert result is None


# ── Environment isolation ─────────────────────────────────────────────────


class TestEnvironmentIsolation:
    def test_dev_prompt_not_visible_in_staging(self) -> None:
        register_prompt("greet", "dev-only", "alice", "init", ["gpt-4"], environment="dev")
        assert get_active_prompt("greet", "staging") is None

    def test_dev_prompt_not_visible_in_production(self) -> None:
        register_prompt("greet", "dev-only", "alice", "init", ["gpt-4"], environment="dev")
        assert get_active_prompt("greet", "production") is None

    def test_promoted_prompt_visible_in_target(self) -> None:
        pv = register_prompt("greet", "content", "alice", "init", ["gpt-4"])
        pv.eval_score = 0.95
        promote_prompt("greet", pv.version, "staging")
        assert get_active_prompt("greet", "staging") is not None
        assert get_active_prompt("greet", "staging").content == "content"


# ── Promotion ─────────────────────────────────────────────────────────────


class TestPromotePrompt:
    def test_promote_succeeds_above_threshold(self) -> None:
        pv = register_prompt("greet", "Hello", "alice", "init", ["gpt-4"])
        pv.eval_score = 0.9
        promoted = promote_prompt("greet", pv.version, "staging")
        assert promoted.environment == PromptEnvironment.STAGING
        assert promoted.version == pv.version
        assert promoted.content == pv.content

    def test_promote_fails_below_threshold(self) -> None:
        pv = register_prompt("greet", "Hello", "alice", "init", ["gpt-4"])
        pv.eval_score = 0.5
        with pytest.raises(ValueError, match="below minimum"):
            promote_prompt("greet", pv.version, "production")

    def test_promote_with_custom_threshold(self) -> None:
        pv = register_prompt("greet", "Hello", "alice", "init", ["gpt-4"])
        pv.eval_score = 0.6
        promoted = promote_prompt("greet", pv.version, "staging", min_eval_score=0.5)
        assert promoted.environment == PromptEnvironment.STAGING

    def test_promote_nonexistent_version_raises(self) -> None:
        register_prompt("greet", "Hello", "alice", "init", ["gpt-4"])
        with pytest.raises(ValueError, match="not found"):
            promote_prompt("greet", "9.9.9", "staging")

    def test_promote_nonexistent_name_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            promote_prompt("nope", "1.0.0", "staging")


# ── Rollback ──────────────────────────────────────────────────────────────


class TestRollbackPrompt:
    def test_rollback_returns_previous(self) -> None:
        pv1 = register_prompt("greet", "v1-content", "alice", "first", ["gpt-4"])
        pv1.eval_score = 0.9
        promote_prompt("greet", pv1.version, "staging")
        pv2 = register_prompt("greet", "v2-content", "alice", "second", ["gpt-4"])
        pv2.eval_score = 0.95
        promote_prompt("greet", pv2.version, "staging")

        rolled = rollback_prompt("greet", "staging")
        assert rolled is not None
        assert rolled.content == "v1-content"
        assert rolled.rollback_from == pv2.version

    def test_rollback_returns_none_with_single_version(self) -> None:
        register_prompt("greet", "v1", "alice", "init", ["gpt-4"])
        result = rollback_prompt("greet", "dev")
        assert result is None

    def test_rollback_returns_none_for_empty(self) -> None:
        result = rollback_prompt("nonexistent", "dev")
        assert result is None


# ── Version history ───────────────────────────────────────────────────────


class TestGetPromptHistory:
    def test_returns_all_versions(self) -> None:
        register_prompt("greet", "v1", "alice", "first", ["gpt-4"])
        register_prompt("greet", "v2", "alice", "second", ["gpt-4"])
        history = get_prompt_history("greet")
        assert len(history) == 2

    def test_returns_empty_for_unknown(self) -> None:
        history = get_prompt_history("nonexistent")
        assert history == []

    def test_includes_promoted_versions(self) -> None:
        pv = register_prompt("greet", "v1", "alice", "init", ["gpt-4"])
        pv.eval_score = 0.9
        promote_prompt("greet", pv.version, "staging")
        history = get_prompt_history("greet")
        assert len(history) == 2
        envs = {h.environment for h in history}
        assert PromptEnvironment.DEV in envs
        assert PromptEnvironment.STAGING in envs


# ── Semver parsing ────────────────────────────────────────────────────────


class TestParseSemver:
    def test_parse_valid(self) -> None:
        assert parse_semver("1.2.3") == (1, 2, 3)

    def test_parse_zeros(self) -> None:
        assert parse_semver("0.0.0") == (0, 0, 0)

    def test_parse_large_numbers(self) -> None:
        assert parse_semver("100.200.300") == (100, 200, 300)

    def test_parse_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid semver"):
            parse_semver("not-a-version")

    def test_parse_incomplete_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid semver"):
            parse_semver("1.2")


# ── Version bumping ──────────────────────────────────────────────────────


class TestBumpVersion:
    def test_bump_patch(self) -> None:
        assert bump_version("1.2.3", "patch") == "1.2.4"

    def test_bump_minor(self) -> None:
        assert bump_version("1.2.3", "minor") == "1.3.0"

    def test_bump_major(self) -> None:
        assert bump_version("1.2.3", "major") == "2.0.0"

    def test_bump_from_zero(self) -> None:
        assert bump_version("0.0.0", "patch") == "0.0.1"
        assert bump_version("0.0.0", "minor") == "0.1.0"
        assert bump_version("0.0.0", "major") == "1.0.0"


# ── JSON serialization ───────────────────────────────────────────────────


class TestPromptVersionToJson:
    def test_serializes_all_fields(self) -> None:
        pv = register_prompt("greet", "Hello", "alice", "init", ["gpt-4"])
        data = prompt_version_to_json(pv)
        assert data["name"] == "greet"
        assert data["version"] == "1.0.0"
        assert data["content"] == "Hello"
        assert data["author"] == "alice"
        assert data["environment"] == "dev"
        assert data["eval_score"] == 0.0
        assert data["rollback_from"] is None
        assert data["model_versions"] == ["gpt-4"]
        # id should be a string UUID
        uuid.UUID(data["id"])
        # created_at should be ISO format
        assert "T" in data["created_at"]

    def test_serializes_rollback_from(self) -> None:
        pv1 = register_prompt("greet", "v1", "alice", "first", ["gpt-4"])
        pv1.eval_score = 0.9
        promote_prompt("greet", pv1.version, "staging")
        pv2 = register_prompt("greet", "v2", "alice", "second", ["gpt-4"])
        pv2.eval_score = 0.95
        promote_prompt("greet", pv2.version, "staging")
        rolled = rollback_prompt("greet", "staging")
        data = prompt_version_to_json(rolled)
        assert data["rollback_from"] == pv2.version


# ── Enums ─────────────────────────────────────────────────────────────────


class TestEnums:
    def test_prompt_environment_values(self) -> None:
        assert PromptEnvironment.DEV == "dev"
        assert PromptEnvironment.STAGING == "staging"
        assert PromptEnvironment.PRODUCTION == "production"

    def test_version_bump_type_values(self) -> None:
        assert VersionBumpType.MAJOR == "major"
        assert VersionBumpType.MINOR == "minor"
        assert VersionBumpType.PATCH == "patch"


# ── Clear registry ────────────────────────────────────────────────────────


class TestClearPromptRegistry:
    def test_clears_all(self) -> None:
        register_prompt("greet", "Hello", "alice", "init", ["gpt-4"])
        clear_prompt_registry()
        assert get_prompt_history("greet") == []
        assert get_active_prompt("greet", "dev") is None
