"""Tests for Prompt Version Controller."""

from __future__ import annotations

from app.quality.prompt_version_controller import (
    PromptEnvironment,
    PromptStatus,
    PromptVersion,
    PromptVersionController,
    RegistryConfig,
    SemanticVersion,
    _can_promote,
    _compute_diff,
    _content_hash,
)

# ── Helper factories ──────────────────────────────────────────────────────

def _make_controller(**overrides) -> PromptVersionController:
    config = RegistryConfig(**overrides) if overrides else None
    return PromptVersionController(config)


PROMPT_A = "You are a code reviewer. Check for bugs and security issues."
PROMPT_B = "You are a code reviewer. Check for bugs, security issues, and performance."
PROMPT_C = "You are an assistant that helps with coding tasks."


# ── Pure helper tests ─────────────────────────────────────────────────────

class TestContentHash:
    def test_deterministic(self):
        h1 = _content_hash("hello")
        h2 = _content_hash("hello")
        assert h1 == h2

    def test_different_content(self):
        h1 = _content_hash("hello")
        h2 = _content_hash("world")
        assert h1 != h2

    def test_length(self):
        h = _content_hash("test")
        assert len(h) == 16


class TestComputeDiff:
    def test_identical(self):
        diff = _compute_diff("line1\nline2", "line1\nline2")
        assert diff.is_identical is True
        assert diff.lines_changed == 0

    def test_added_lines(self):
        diff = _compute_diff("line1", "line1\nline2")
        assert diff.lines_added == 1

    def test_removed_lines(self):
        diff = _compute_diff("line1\nline2", "line1")
        assert diff.lines_removed == 1

    def test_change_summary(self):
        diff = _compute_diff("a", "b")
        assert "+" in diff.change_summary
        assert "-" in diff.change_summary


class TestCanPromote:
    def test_dev_to_staging_approved(self):
        cfg = RegistryConfig()
        v = PromptVersion(environment=PromptEnvironment.DEV, status=PromptStatus.APPROVED)
        ok, reason = _can_promote(v, PromptEnvironment.STAGING, cfg)
        assert ok is True

    def test_dev_to_staging_pending(self):
        cfg = RegistryConfig(require_review_for_staging=True)
        v = PromptVersion(environment=PromptEnvironment.DEV, status=PromptStatus.PENDING_REVIEW)
        ok, reason = _can_promote(v, PromptEnvironment.STAGING, cfg)
        assert ok is False
        assert "approved" in reason.lower()

    def test_cannot_skip_environments(self):
        cfg = RegistryConfig()
        v = PromptVersion(environment=PromptEnvironment.DEV, status=PromptStatus.APPROVED)
        ok, reason = _can_promote(v, PromptEnvironment.PROD, cfg)
        assert ok is False
        assert "skip" in reason.lower()

    def test_cannot_demote(self):
        cfg = RegistryConfig()
        v = PromptVersion(environment=PromptEnvironment.STAGING, status=PromptStatus.APPROVED)
        ok, reason = _can_promote(v, PromptEnvironment.DEV, cfg)
        assert ok is False

    def test_staging_to_prod_approved(self):
        cfg = RegistryConfig()
        v = PromptVersion(environment=PromptEnvironment.STAGING, status=PromptStatus.APPROVED)
        ok, _ = _can_promote(v, PromptEnvironment.PROD, cfg)
        assert ok is True

    def test_no_review_required(self):
        cfg = RegistryConfig(require_review_for_staging=False)
        v = PromptVersion(environment=PromptEnvironment.DEV, status=PromptStatus.PENDING_REVIEW)
        ok, _ = _can_promote(v, PromptEnvironment.STAGING, cfg)
        assert ok is True


class TestSemanticVersion:
    def test_str(self):
        v = SemanticVersion(1, 2, 3)
        assert str(v) == "1.2.3"

    def test_bump_patch(self):
        v = SemanticVersion(1, 0, 0).bump_patch()
        assert v.to_tuple() == (1, 0, 1)

    def test_bump_minor(self):
        v = SemanticVersion(1, 2, 3).bump_minor()
        assert v.to_tuple() == (1, 3, 0)

    def test_bump_major(self):
        v = SemanticVersion(1, 2, 3).bump_major()
        assert v.to_tuple() == (2, 0, 0)

    def test_to_tuple(self):
        assert SemanticVersion(1, 0, 0).to_tuple() == (1, 0, 0)


# ── Controller tests ──────────────────────────────────────────────────────

class TestRegisterPrompt:
    def test_first_version(self):
        ctrl = _make_controller()
        pv = ctrl.register_prompt("review-prompt", PROMPT_A, author="dev")
        assert str(pv.version) == "1.0.0"
        assert pv.prompt_name == "review-prompt"
        assert pv.author == "dev"
        assert pv.content_hash

    def test_auto_increment_patch(self):
        ctrl = _make_controller()
        ctrl.register_prompt("p1", PROMPT_A)
        pv2 = ctrl.register_prompt("p1", PROMPT_B)
        assert str(pv2.version) == "1.0.1"

    def test_minor_bump(self):
        ctrl = _make_controller()
        ctrl.register_prompt("p1", PROMPT_A)
        pv2 = ctrl.register_prompt("p1", PROMPT_B, bump="minor")
        assert str(pv2.version) == "1.1.0"

    def test_major_bump(self):
        ctrl = _make_controller()
        ctrl.register_prompt("p1", PROMPT_A)
        pv2 = ctrl.register_prompt("p1", PROMPT_B, bump="major")
        assert str(pv2.version) == "2.0.0"

    def test_deduplication(self):
        ctrl = _make_controller()
        pv1 = ctrl.register_prompt("p1", PROMPT_A)
        pv2 = ctrl.register_prompt("p1", PROMPT_A)  # same content
        assert pv1.version_id == pv2.version_id

    def test_auto_deprecate(self):
        ctrl = _make_controller(auto_deprecate_old_versions=True)
        ctrl.register_prompt("p1", PROMPT_A)
        ctrl.register_prompt("p1", PROMPT_B)
        ctrl.register_prompt("p1", PROMPT_C)
        versions = ctrl.list_versions("p1")
        assert versions[0].status == PromptStatus.DEPRECATED

    def test_tags_preserved(self):
        ctrl = _make_controller()
        pv = ctrl.register_prompt("p1", PROMPT_A, tags=["safety", "review"])
        assert pv.tags == ["safety", "review"]


class TestApproveReject:
    def test_approve(self):
        ctrl = _make_controller()
        pv = ctrl.register_prompt("p1", PROMPT_A)
        result = ctrl.approve(pv.version_id)
        assert result.status == PromptStatus.APPROVED

    def test_reject(self):
        ctrl = _make_controller()
        pv = ctrl.register_prompt("p1", PROMPT_A)
        result = ctrl.reject(pv.version_id, reason="too verbose")
        assert result.status == PromptStatus.REJECTED

    def test_approve_nonexistent(self):
        ctrl = _make_controller()
        assert ctrl.approve("nonexistent") is None

    def test_reject_nonexistent(self):
        ctrl = _make_controller()
        assert ctrl.reject("nonexistent") is None


class TestPromote:
    def test_dev_to_staging(self):
        ctrl = _make_controller()
        pv = ctrl.register_prompt("p1", PROMPT_A)
        ctrl.approve(pv.version_id)
        promoted, msg = ctrl.promote(pv.version_id, PromptEnvironment.STAGING)
        assert promoted is not None
        assert promoted.environment == PromptEnvironment.STAGING
        assert promoted.promoted_at is not None

    def test_staging_to_prod(self):
        ctrl = _make_controller()
        pv = ctrl.register_prompt("p1", PROMPT_A)
        ctrl.approve(pv.version_id)
        ctrl.promote(pv.version_id, PromptEnvironment.STAGING)
        promoted, _ = ctrl.promote(pv.version_id, PromptEnvironment.PROD)
        assert promoted.environment == PromptEnvironment.PROD

    def test_cannot_skip(self):
        ctrl = _make_controller()
        pv = ctrl.register_prompt("p1", PROMPT_A)
        ctrl.approve(pv.version_id)
        result, msg = ctrl.promote(pv.version_id, PromptEnvironment.PROD)
        assert result is None
        assert "skip" in msg.lower()

    def test_unapproved_blocked(self):
        ctrl = _make_controller()
        pv = ctrl.register_prompt("p1", PROMPT_A)
        result, msg = ctrl.promote(pv.version_id, PromptEnvironment.STAGING)
        assert result is None

    def test_nonexistent_version(self):
        ctrl = _make_controller()
        result, msg = ctrl.promote("nonexistent", PromptEnvironment.STAGING)
        assert result is None


class TestRollback:
    def test_rollback_success(self):
        ctrl = _make_controller()
        pv1 = ctrl.register_prompt("p1", PROMPT_A)
        ctrl.approve(pv1.version_id)
        ctrl.promote(pv1.version_id, PromptEnvironment.STAGING)

        pv2 = ctrl.register_prompt("p1", PROMPT_B)
        ctrl.approve(pv2.version_id)
        ctrl.promote(pv2.version_id, PromptEnvironment.STAGING)

        rolled, msg = ctrl.rollback("p1", PromptEnvironment.STAGING, reason="regression")
        assert rolled is not None
        assert str(rolled.version) == "1.0.0"

    def test_no_previous_version(self):
        ctrl = _make_controller()
        result, msg = ctrl.rollback("p1", PromptEnvironment.DEV)
        assert result is None
        assert "no previous" in msg.lower()

    def test_rollback_deprecates_current(self):
        ctrl = _make_controller()
        pv1 = ctrl.register_prompt("p1", PROMPT_A)
        ctrl.approve(pv1.version_id)
        ctrl.promote(pv1.version_id, PromptEnvironment.STAGING)

        pv2 = ctrl.register_prompt("p1", PROMPT_B)
        ctrl.approve(pv2.version_id)
        ctrl.promote(pv2.version_id, PromptEnvironment.STAGING)

        ctrl.rollback("p1", PromptEnvironment.STAGING)
        versions = ctrl.list_versions("p1")
        staging_versions = [v for v in versions if v.environment == PromptEnvironment.STAGING]
        assert any(v.status == PromptStatus.DEPRECATED for v in staging_versions)


class TestDiff:
    def test_diff_between_versions(self):
        ctrl = _make_controller()
        pv1 = ctrl.register_prompt("p1", PROMPT_A)
        pv2 = ctrl.register_prompt("p1", PROMPT_B)
        diff = ctrl.diff(pv1.version_id, pv2.version_id)
        assert diff is not None
        assert diff.is_identical is False
        assert diff.old_version == "1.0.0"
        assert diff.new_version == "1.0.1"

    def test_diff_identical(self):
        ctrl = _make_controller()
        pv = ctrl.register_prompt("p1", PROMPT_A)
        diff = ctrl.diff(pv.version_id, pv.version_id)
        assert diff.is_identical is True

    def test_diff_nonexistent(self):
        ctrl = _make_controller()
        assert ctrl.diff("a", "b") is None


class TestGetLatest:
    def test_latest_overall(self):
        ctrl = _make_controller()
        ctrl.register_prompt("p1", PROMPT_A)
        ctrl.register_prompt("p1", PROMPT_B)
        latest = ctrl.get_latest("p1")
        assert str(latest.version) == "1.0.1"

    def test_latest_by_env(self):
        ctrl = _make_controller()
        pv1 = ctrl.register_prompt("p1", PROMPT_A)
        ctrl.approve(pv1.version_id)
        ctrl.promote(pv1.version_id, PromptEnvironment.STAGING)
        ctrl.register_prompt("p1", PROMPT_B)  # still in dev

        staging = ctrl.get_latest("p1", PromptEnvironment.STAGING)
        assert staging is not None
        assert staging.environment == PromptEnvironment.STAGING

    def test_nonexistent_prompt(self):
        ctrl = _make_controller()
        assert ctrl.get_latest("nonexistent") is None


class TestListVersions:
    def test_list(self):
        ctrl = _make_controller()
        ctrl.register_prompt("p1", PROMPT_A)
        ctrl.register_prompt("p1", PROMPT_B)
        versions = ctrl.list_versions("p1")
        assert len(versions) == 2

    def test_empty(self):
        ctrl = _make_controller()
        assert ctrl.list_versions("nonexistent") == []


class TestRegistryReport:
    def test_empty(self):
        ctrl = _make_controller()
        report = ctrl.registry_report()
        assert report.total_prompts == 0

    def test_with_data(self):
        ctrl = _make_controller()
        pv1 = ctrl.register_prompt("p1", PROMPT_A)
        ctrl.register_prompt("p2", PROMPT_C)
        ctrl.approve(pv1.version_id)
        report = ctrl.registry_report()
        assert report.total_prompts == 2
        assert report.total_versions == 2
        assert "p1" in report.latest_versions
        assert "p2" in report.latest_versions

    def test_rollback_count(self):
        ctrl = _make_controller()
        pv1 = ctrl.register_prompt("p1", PROMPT_A)
        ctrl.approve(pv1.version_id)
        ctrl.promote(pv1.version_id, PromptEnvironment.STAGING)
        pv2 = ctrl.register_prompt("p1", PROMPT_B)
        ctrl.approve(pv2.version_id)
        ctrl.promote(pv2.version_id, PromptEnvironment.STAGING)
        ctrl.rollback("p1", PromptEnvironment.STAGING)
        report = ctrl.registry_report()
        assert report.rollback_count == 1


class TestRegistryConfig:
    def test_defaults(self):
        cfg = RegistryConfig()
        assert cfg.require_review_for_staging is True
        assert cfg.max_versions_per_prompt == 50

    def test_custom(self):
        cfg = RegistryConfig(require_review_for_staging=False)
        assert cfg.require_review_for_staging is False


class TestEnumValues:
    def test_environments(self):
        assert PromptEnvironment.DEV == "dev"
        assert PromptEnvironment.PROD == "prod"

    def test_statuses(self):
        assert PromptStatus.APPROVED == "approved"
        assert PromptStatus.DEPRECATED == "deprecated"
