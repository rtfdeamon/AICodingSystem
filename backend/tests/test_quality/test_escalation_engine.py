"""Tests for the Confidence-Gated Human-in-the-Loop Escalation Engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.quality.escalation_engine import (
    EscalationPolicy,
    EscalationReason,
    EscalationTier,
    clear_escalation_data,
    compute_composite_confidence,
    configure_policy,
    escalation_item_to_json,
    evaluate_escalation,
    get_escalation_stats,
    get_pending_escalations,
    get_sla_breaches,
    matches_high_risk_pattern,
    resolve_escalation,
)

# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_state() -> None:
    """Reset escalation state before every test."""
    clear_escalation_data()
    configure_policy(
        high_risk_patterns=["/auth/", "/payment/", "/admin/"],
        confidence_threshold=0.7,
        max_auto_lines=50,
        require_human_irreversible=True,
    )


# ── Policy configuration ─────────────────────────────────────────────────

class TestPolicyConfiguration:
    def test_configure_returns_policy(self) -> None:
        policy = configure_policy(
            high_risk_patterns=["/secrets/"],
            confidence_threshold=0.8,
            max_auto_lines=30,
        )
        assert isinstance(policy, EscalationPolicy)
        assert policy.confidence_threshold == 0.8
        assert policy.max_auto_approve_lines == 30
        assert "/secrets/" in policy.high_risk_patterns

    def test_default_policy_values(self) -> None:
        policy = configure_policy(high_risk_patterns=[])
        assert policy.confidence_threshold == 0.7
        assert policy.max_auto_approve_lines == 50
        assert policy.require_human_for_irreversible is True


# ── Auto-approve ──────────────────────────────────────────────────────────

class TestAutoApprove:
    def test_high_confidence_small_safe_change(self) -> None:
        item = evaluate_escalation(
            file_paths=["src/utils/helpers.py"],
            change_size=10,
            confidence_score=0.95,
        )
        assert item.tier == EscalationTier.AUTO_APPROVE
        assert item.resolution == "approved"
        assert item.resolved_at is not None

    def test_auto_approve_sla_is_zero(self) -> None:
        item = evaluate_escalation(
            file_paths=["src/utils/fmt.py"],
            change_size=5,
            confidence_score=0.99,
        )
        assert item.sla_hours == 0

    def test_auto_approve_not_in_pending(self) -> None:
        evaluate_escalation(
            file_paths=["src/lib.py"],
            change_size=10,
            confidence_score=0.95,
        )
        assert len(get_pending_escalations()) == 0


# ── Developer review ──────────────────────────────────────────────────────

class TestDeveloperReview:
    def test_low_confidence_triggers_review(self) -> None:
        item = evaluate_escalation(
            file_paths=["src/utils/helpers.py"],
            change_size=10,
            confidence_score=0.3,
        )
        assert item.tier in (
            EscalationTier.DEVELOPER_REVIEW,
            EscalationTier.SENIOR_REVIEW,
            EscalationTier.SECURITY_REVIEW,
        )
        assert EscalationReason.LOW_CONFIDENCE in item.reasons

    def test_medium_confidence_needs_developer(self) -> None:
        # Composite just below threshold
        item = evaluate_escalation(
            file_paths=["src/service.py"],
            change_size=20,
            confidence_score=0.5,
            hallucination_score=0.3,
        )
        assert item.tier != EscalationTier.AUTO_APPROVE
        assert item.resolution is None


# ── Senior review ─────────────────────────────────────────────────────────

class TestSeniorReview:
    def test_large_change_escalates(self) -> None:
        item = evaluate_escalation(
            file_paths=["src/refactor.py"],
            change_size=300,
            confidence_score=0.95,
        )
        assert item.tier == EscalationTier.SENIOR_REVIEW
        assert EscalationReason.LARGE_CHANGE in item.reasons

    def test_schema_change_escalates(self) -> None:
        item = evaluate_escalation(
            file_paths=["db/migrations/002_add_column.py"],
            change_size=10,
            confidence_score=0.95,
        )
        assert item.tier == EscalationTier.SENIOR_REVIEW
        assert EscalationReason.SCHEMA_CHANGE in item.reasons

    def test_senior_review_sla(self) -> None:
        item = evaluate_escalation(
            file_paths=["db/schema.sql"],
            change_size=10,
            confidence_score=0.95,
        )
        assert item.sla_hours == 8


# ── Security review ───────────────────────────────────────────────────────

class TestSecurityReview:
    def test_auth_path_with_low_confidence(self) -> None:
        item = evaluate_escalation(
            file_paths=["src/auth/login.py"],
            change_size=10,
            confidence_score=0.3,
        )
        assert item.tier == EscalationTier.SECURITY_REVIEW
        assert EscalationReason.HIGH_RISK_PATH in item.reasons

    def test_security_findings_escalate(self) -> None:
        item = evaluate_escalation(
            file_paths=["src/api.py"],
            change_size=10,
            confidence_score=0.95,
            has_security_findings=True,
        )
        assert item.tier == EscalationTier.SECURITY_REVIEW
        assert EscalationReason.SECURITY_SURFACE in item.reasons

    def test_crypto_code_escalates(self) -> None:
        item = evaluate_escalation(
            file_paths=["lib/crypto/aes.py"],
            change_size=10,
            confidence_score=0.95,
        )
        assert item.tier == EscalationTier.SECURITY_REVIEW
        assert EscalationReason.CRYPTO_CODE in item.reasons

    def test_pii_path_escalates(self) -> None:
        item = evaluate_escalation(
            file_paths=["services/pii_handler.py"],
            change_size=10,
            confidence_score=0.95,
        )
        assert item.tier == EscalationTier.SECURITY_REVIEW
        assert EscalationReason.PII_DETECTED in item.reasons

    def test_security_review_sla(self) -> None:
        item = evaluate_escalation(
            file_paths=["src/auth/token.py"],
            change_size=10,
            confidence_score=0.3,
        )
        assert item.sla_hours == 2

    def test_security_review_priority(self) -> None:
        item = evaluate_escalation(
            file_paths=["lib/crypto/sign.py"],
            change_size=10,
            confidence_score=0.95,
        )
        assert item.priority == 1


# ── High risk pattern matching ────────────────────────────────────────────

class TestHighRiskPatterns:
    def test_matches_auth_pattern(self) -> None:
        assert matches_high_risk_pattern("src/auth/login.py", ["/auth/"])

    def test_matches_payment_pattern(self) -> None:
        assert matches_high_risk_pattern("api/payment/charge.py", ["/payment/"])

    def test_no_match_safe_path(self) -> None:
        assert not matches_high_risk_pattern("src/utils/helpers.py", ["/auth/", "/payment/"])

    def test_empty_patterns(self) -> None:
        assert not matches_high_risk_pattern("src/auth/login.py", [])


# ── Composite confidence ──────────────────────────────────────────────────

class TestCompositeConfidence:
    def test_perfect_scores(self) -> None:
        result = compute_composite_confidence(1.0, 0.0, True)
        assert result == pytest.approx(1.0)

    def test_worst_scores(self) -> None:
        result = compute_composite_confidence(0.0, 1.0, False)
        assert result == pytest.approx(0.0)

    def test_weights_sum_correctly(self) -> None:
        # 0.5*0.8 + 0.3*(1-0.2) + 0.2*1.0 = 0.4 + 0.24 + 0.2 = 0.84
        result = compute_composite_confidence(0.8, 0.2, True)
        assert result == pytest.approx(0.84)

    def test_clamped_to_unit(self) -> None:
        result = compute_composite_confidence(1.0, -0.5, True)
        assert result <= 1.0


# ── Irreversible action escalation ────────────────────────────────────────

class TestIrreversibleActions:
    def test_irreversible_forces_review(self) -> None:
        item = evaluate_escalation(
            file_paths=["src/utils/helpers.py"],
            change_size=10,
            confidence_score=0.95,
            is_irreversible=True,
        )
        assert item.tier != EscalationTier.AUTO_APPROVE

    def test_irreversible_policy_disabled(self) -> None:
        configure_policy(
            high_risk_patterns=[],
            require_human_irreversible=False,
        )
        item = evaluate_escalation(
            file_paths=["src/utils/helpers.py"],
            change_size=10,
            confidence_score=0.95,
            is_irreversible=True,
        )
        assert item.tier == EscalationTier.AUTO_APPROVE


# ── Resolve escalation ───────────────────────────────────────────────────

class TestResolveEscalation:
    def test_resolve_approved(self) -> None:
        item = evaluate_escalation(
            file_paths=["src/auth/login.py"],
            change_size=10,
            confidence_score=0.3,
        )
        resolved = resolve_escalation(item.id, "approved")
        assert resolved.resolution == "approved"
        assert resolved.resolved_at is not None

    def test_resolve_rejected(self) -> None:
        item = evaluate_escalation(
            file_paths=["lib/crypto/aes.py"],
            change_size=10,
            confidence_score=0.95,
        )
        resolved = resolve_escalation(item.id, "rejected")
        assert resolved.resolution == "rejected"

    def test_resolve_removes_from_pending(self) -> None:
        item = evaluate_escalation(
            file_paths=["lib/crypto/aes.py"],
            change_size=10,
            confidence_score=0.95,
        )
        resolve_escalation(item.id, "approved")
        assert len(get_pending_escalations()) == 0

    def test_resolve_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            resolve_escalation("nonexistent-id", "approved")


# ── Pending queue filtering ───────────────────────────────────────────────

class TestPendingQueue:
    def test_filter_by_tier(self) -> None:
        evaluate_escalation(
            file_paths=["lib/crypto/aes.py"],
            change_size=10,
            confidence_score=0.95,
        )
        evaluate_escalation(
            file_paths=["db/migrations/001.py"],
            change_size=10,
            confidence_score=0.95,
        )
        security = get_pending_escalations(EscalationTier.SECURITY_REVIEW)
        senior = get_pending_escalations(EscalationTier.SENIOR_REVIEW)
        assert len(security) == 1
        assert len(senior) == 1

    def test_all_pending(self) -> None:
        evaluate_escalation(
            file_paths=["lib/crypto/aes.py"],
            change_size=10,
            confidence_score=0.95,
        )
        evaluate_escalation(
            file_paths=["db/schema.sql"],
            change_size=10,
            confidence_score=0.95,
        )
        assert len(get_pending_escalations()) == 2


# ── SLA breach detection ─────────────────────────────────────────────────

class TestSLABreaches:
    def test_no_breaches_initially(self) -> None:
        evaluate_escalation(
            file_paths=["lib/crypto/aes.py"],
            change_size=10,
            confidence_score=0.95,
        )
        assert len(get_sla_breaches()) == 0

    def test_detects_breach(self) -> None:
        item = evaluate_escalation(
            file_paths=["lib/crypto/aes.py"],
            change_size=10,
            confidence_score=0.95,
        )
        # Simulate creation 3 hours ago (SLA is 2h for security review)
        item.created_at = datetime.now(UTC) - timedelta(hours=3)
        breaches = get_sla_breaches()
        assert len(breaches) == 1
        assert breaches[0].id == item.id


# ── Stats tracking ────────────────────────────────────────────────────────

class TestEscalationStats:
    def test_empty_stats(self) -> None:
        stats = get_escalation_stats()
        assert stats.total_escalations == 0
        assert stats.escalation_rate == 0.0

    def test_stats_after_evaluations(self) -> None:
        # Auto-approved
        evaluate_escalation(
            file_paths=["src/utils.py"],
            change_size=5,
            confidence_score=0.95,
        )
        # Security review
        evaluate_escalation(
            file_paths=["lib/crypto/aes.py"],
            change_size=10,
            confidence_score=0.95,
        )
        stats = get_escalation_stats()
        assert stats.total_escalations == 2
        assert stats.by_tier.get("auto_approve") == 1
        assert stats.by_tier.get("security_review") == 1
        assert stats.escalation_rate == 0.5


# ── JSON serialization ───────────────────────────────────────────────────

class TestJSONSerialization:
    def test_serializes_auto_approved(self) -> None:
        item = evaluate_escalation(
            file_paths=["src/lib.py"],
            change_size=5,
            confidence_score=0.99,
        )
        data = escalation_item_to_json(item)
        assert data["tier"] == "auto_approve"
        assert data["resolution"] == "approved"
        assert isinstance(data["reasons"], list)
        assert isinstance(data["created_at"], str)

    def test_serializes_pending(self) -> None:
        item = evaluate_escalation(
            file_paths=["lib/crypto/aes.py"],
            change_size=10,
            confidence_score=0.95,
        )
        data = escalation_item_to_json(item)
        assert data["tier"] == "security_review"
        assert data["resolved_at"] is None
        assert data["resolution"] is None
        assert "crypto_code" in data["reasons"]


# ── Edge cases ────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_all_paths_safe(self) -> None:
        item = evaluate_escalation(
            file_paths=["src/utils/fmt.py", "src/utils/string.py"],
            change_size=15,
            confidence_score=0.95,
        )
        assert item.tier == EscalationTier.AUTO_APPROVE

    def test_empty_file_paths(self) -> None:
        item = evaluate_escalation(
            file_paths=[],
            change_size=5,
            confidence_score=0.95,
        )
        assert item.tier == EscalationTier.AUTO_APPROVE

    def test_clear_resets_everything(self) -> None:
        evaluate_escalation(
            file_paths=["lib/crypto/aes.py"],
            change_size=10,
            confidence_score=0.95,
        )
        clear_escalation_data()
        assert len(get_pending_escalations()) == 0
        stats = get_escalation_stats()
        assert stats.total_escalations == 0
