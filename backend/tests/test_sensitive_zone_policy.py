"""Tests for Sensitive Code Zone Policy."""

from __future__ import annotations

from app.quality.sensitive_zone_policy import (
    DetectionMethod,
    Exemption,
    PolicyAction,
    SensitiveZone,
    SensitiveZonePolicy,
    ZoneType,
)

# ── Default Zones ────────────────────────────────────────────────────────

class TestDefaultZones:
    def test_default_zones_loaded(self):
        policy = SensitiveZonePolicy()
        assert len(policy.zones) >= 6

    def test_no_defaults(self):
        policy = SensitiveZonePolicy(use_defaults=False)
        assert len(policy.zones) == 0

    def test_custom_zones_added(self):
        custom = SensitiveZone(
            zone_type=ZoneType.CUSTOM,
            name="Custom Zone",
            path_patterns=[r"custom/"],
            action=PolicyAction.BLOCK,
        )
        policy = SensitiveZonePolicy(zones=[custom], use_defaults=False)
        assert len(policy.zones) == 1


# ── Path-Based Detection ────────────────────────────────────────────────

class TestPathDetection:
    def test_auth_path_detected(self):
        policy = SensitiveZonePolicy()
        decision = policy.check_file("src/auth/login.py")
        assert decision.action in (PolicyAction.REQUIRE_REVIEW, PolicyAction.BLOCK)
        assert len(decision.matches) > 0

    def test_crypto_path_blocked(self):
        policy = SensitiveZonePolicy()
        decision = policy.check_file("lib/crypto/encrypt.py")
        assert decision.action == PolicyAction.BLOCK
        assert decision.allowed is False

    def test_payment_path_blocked(self):
        policy = SensitiveZonePolicy()
        decision = policy.check_file("services/payment/stripe.py")
        assert decision.action == PolicyAction.BLOCK

    def test_safe_path_allowed(self):
        policy = SensitiveZonePolicy()
        decision = policy.check_file("src/utils/formatters.py")
        assert decision.allowed is True
        assert decision.action == PolicyAction.ALLOW

    def test_infra_path_warned(self):
        policy = SensitiveZonePolicy()
        decision = policy.check_file("infra/terraform/main.tf")
        assert decision.action == PolicyAction.WARN
        assert decision.allowed is True

    def test_pii_path_requires_review(self):
        policy = SensitiveZonePolicy()
        decision = policy.check_file("services/gdpr/data_subject.py")
        assert decision.action == PolicyAction.REQUIRE_REVIEW

    def test_secrets_path_requires_review(self):
        policy = SensitiveZonePolicy()
        decision = policy.check_file("config/vault/secrets.py")
        assert decision.action == PolicyAction.REQUIRE_REVIEW


# ── Content-Based Detection ──────────────────────────────────────────────

class TestContentDetection:
    def test_password_hashing_detected(self):
        policy = SensitiveZonePolicy()
        code = "def hash_password(pw):\n    return bcrypt.hash(pw)"
        decision = policy.check_file("utils/helpers.py", code)
        assert len(decision.matches) > 0

    def test_crypto_import_blocked(self):
        policy = SensitiveZonePolicy()
        code = "from cryptography.fernet import Fernet\nkey = Fernet.generate_key()"
        decision = policy.check_file("utils/helpers.py", code)
        assert decision.action == PolicyAction.BLOCK

    def test_jwt_detected(self):
        policy = SensitiveZonePolicy()
        code = "token = jwt.encode(payload, secret)"
        decision = policy.check_file("utils/token.py", code)
        assert len(decision.matches) > 0

    def test_sql_injection_in_payment(self):
        policy = SensitiveZonePolicy()
        code = "stripe.Charge.create(amount=100)"
        decision = policy.check_file("services/billing.py", code)
        assert len(decision.matches) > 0

    def test_safe_code_allowed(self):
        policy = SensitiveZonePolicy()
        code = "def add(a, b):\n    return a + b"
        decision = policy.check_file("utils/math.py", code)
        assert decision.allowed is True

    def test_both_detection_methods(self):
        policy = SensitiveZonePolicy()
        code = "from cryptography import AES\ncipher = AES.new(key)"
        decision = policy.check_file("lib/encrypt/aes.py", code)
        has_both = any(m.detection_method == DetectionMethod.BOTH for m in decision.matches)
        assert has_both

    def test_line_numbers_tracked(self):
        policy = SensitiveZonePolicy()
        code = "line1\nfrom cryptography import Fernet\nline3"
        decision = policy.check_file("utils/x.py", code)
        if decision.matches:
            match = decision.matches[0]
            assert len(match.line_numbers) > 0


# ── Exemptions ───────────────────────────────────────────────────────────

class TestExemptions:
    def test_exemption_overrides_block(self):
        policy = SensitiveZonePolicy()
        ex = Exemption(
            file_pattern=r"lib/crypto/.*",
            zone_type=ZoneType.CRYPTO,
            approved_by="security-team",
            reason="Pre-approved crypto module",
        )
        policy.add_exemption(ex)
        decision = policy.check_file("lib/crypto/encrypt.py")
        assert decision.allowed is True
        assert decision.exemption_used is not None

    def test_exemption_with_no_zone_type(self):
        policy = SensitiveZonePolicy()
        ex = Exemption(
            file_pattern=r"legacy/.*",
            approved_by="admin",
            reason="Legacy code",
        )
        policy.add_exemption(ex)
        decision = policy.check_file("legacy/auth/login.py")
        assert decision.allowed is True

    def test_expired_exemption_ignored(self):
        policy = SensitiveZonePolicy()
        ex = Exemption(
            file_pattern=r"lib/crypto/.*",
            zone_type=ZoneType.CRYPTO,
            approved_by="admin",
            reason="Temp",
            expires_at="2020-01-01T00:00:00+00:00",
        )
        policy.add_exemption(ex)
        decision = policy.check_file("lib/crypto/encrypt.py")
        assert decision.allowed is False

    def test_remove_exemption(self):
        policy = SensitiveZonePolicy()
        ex = Exemption(file_pattern=r".*", approved_by="admin", reason="test")
        eid = policy.add_exemption(ex)
        assert policy.remove_exemption(eid) is True

    def test_remove_nonexistent_exemption(self):
        policy = SensitiveZonePolicy()
        assert policy.remove_exemption("nope") is False


# ── Zone Management ──────────────────────────────────────────────────────

class TestZoneManagement:
    def test_add_zone(self):
        policy = SensitiveZonePolicy(use_defaults=False)
        zone = SensitiveZone(
            zone_type=ZoneType.CUSTOM,
            name="My Zone",
            path_patterns=[r"my_zone/"],
            action=PolicyAction.BLOCK,
        )
        policy.add_zone(zone)
        assert len(policy.zones) == 1

    def test_remove_zone(self):
        policy = SensitiveZonePolicy()
        before = len(policy.zones)
        removed = policy.remove_zone(ZoneType.CRYPTO)
        assert removed > 0
        assert len(policy.zones) < before

    def test_remove_nonexistent_zone(self):
        policy = SensitiveZonePolicy(use_defaults=False)
        assert policy.remove_zone(ZoneType.CUSTOM) == 0


# ── Batch Check ──────────────────────────────────────────────────────────

class TestBatchCheck:
    def test_batch_check(self):
        policy = SensitiveZonePolicy()
        files = {
            "src/auth/login.py": "password check",
            "src/utils/math.py": "def add(a, b): return a + b",
        }
        decisions = policy.check_batch(files)
        assert len(decisions) == 2
        # auth file should be flagged
        assert any(not d.allowed or d.action != PolicyAction.ALLOW for d in decisions)


# ── Strictest Action ─────────────────────────────────────────────────────

class TestStrictestAction:
    def test_block_takes_precedence_over_warn(self):
        policy = SensitiveZonePolicy()
        # This file matches both infra (warn) and crypto (block) zones
        code = "from cryptography import Fernet"
        decision = policy.check_file("infra/deploy/crypto_config.py", code)
        assert decision.action == PolicyAction.BLOCK


# ── Analytics ────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_decisions_recorded(self):
        policy = SensitiveZonePolicy()
        policy.check_file("src/auth/login.py")
        assert len(policy.decisions) == 1

    def test_clear_decisions(self):
        policy = SensitiveZonePolicy()
        policy.check_file("src/auth/login.py")
        count = policy.clear_decisions()
        assert count == 1
        assert len(policy.decisions) == 0

    def test_blocked_files(self):
        policy = SensitiveZonePolicy()
        policy.check_file("lib/crypto/encrypt.py")
        policy.check_file("src/utils/math.py")
        blocked = policy.blocked_files()
        assert "lib/crypto/encrypt.py" in blocked
        assert "src/utils/math.py" not in blocked

    def test_summary(self):
        policy = SensitiveZonePolicy()
        policy.check_file("lib/crypto/encrypt.py")
        policy.check_file("src/utils/math.py")
        s = policy.summary()
        assert s["total_checks"] == 2
        assert s["blocked_count"] >= 1
        assert s["zones_configured"] >= 6

    def test_summary_empty(self):
        policy = SensitiveZonePolicy()
        s = policy.summary()
        assert s["total_checks"] == 0
