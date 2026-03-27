"""Tests for PII leakage monitoring module."""

from __future__ import annotations

from app.quality.pii_monitor import (
    PIIScanResult,
    PIIType,
    scan_for_pii,
    validate_agent_output,
)

# ── Email detection ────────────────────────────────────────────────────

class TestEmailDetection:
    def test_detects_simple_email(self) -> None:
        result = scan_for_pii("Contact john.doe@company.com for details")
        assert result.has_pii
        assert PIIType.EMAIL.value in result.pii_types_found

    def test_skips_example_email(self) -> None:
        result = scan_for_pii("Send to user@example.com")
        assert not result.has_pii

    def test_skips_noreply_email(self) -> None:
        result = scan_for_pii("From noreply@github.com")
        assert not result.has_pii

    def test_redacts_email(self) -> None:
        result = scan_for_pii("Email: alice@secretcorp.com")
        assert "a***@secretcorp.com" in result.redacted_text


# ── Phone detection ────────────────────────────────────────────────────

class TestPhoneDetection:
    def test_detects_us_phone(self) -> None:
        result = scan_for_pii("Call 555-123-4567 for support")
        assert result.has_pii
        assert PIIType.PHONE.value in result.pii_types_found

    def test_detects_phone_with_parens(self) -> None:
        result = scan_for_pii("Phone: (555) 123-4567")
        assert result.has_pii

    def test_redacts_phone(self) -> None:
        result = scan_for_pii("Call 555-123-4567")
        assert "***-***-4567" in result.redacted_text


# ── SSN detection ──────────────────────────────────────────────────────

class TestSSNDetection:
    def test_detects_ssn(self) -> None:
        result = scan_for_pii("SSN: 123-45-6789")
        assert result.has_pii
        assert PIIType.SSN.value in result.pii_types_found

    def test_redacts_ssn(self) -> None:
        result = scan_for_pii("SSN: 123-45-6789")
        assert "***-**-6789" in result.redacted_text


# ── Credit card detection ──────────────────────────────────────────────

class TestCreditCardDetection:
    def test_detects_visa(self) -> None:
        result = scan_for_pii("Card: 4111111111111111")
        assert result.has_pii
        assert PIIType.CREDIT_CARD.value in result.pii_types_found

    def test_detects_card_with_spaces(self) -> None:
        result = scan_for_pii("Card: 4111 1111 1111 1111")
        assert result.has_pii

    def test_redacts_card(self) -> None:
        result = scan_for_pii("Card: 4111111111111111")
        assert "1111" in result.redacted_text
        assert "4111111111111111" not in result.redacted_text


# ── API key / secret detection ─────────────────────────────────────────

class TestAPIKeyDetection:
    def test_detects_aws_key(self) -> None:
        result = scan_for_pii("AWS key: AKIAIOSFODNN7EXAMPLE")
        assert result.has_pii
        assert PIIType.AWS_KEY.value in result.pii_types_found

    def test_detects_generic_api_key(self) -> None:
        fake_key = "sk_test_FAKEFAKEFAKEFAKEFAKEFAKE00"  # noqa: S105
        result = scan_for_pii(f"key: {fake_key}")
        assert result.has_pii

    def test_detects_private_key_block(self) -> None:
        result = scan_for_pii("-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIB...")
        assert result.has_pii
        assert PIIType.PRIVATE_KEY.value in result.pii_types_found
        assert "[REDACTED PRIVATE KEY]" in result.redacted_text


# ── JWT detection ──────────────────────────────────────────────────────

class TestJWTDetection:
    def test_detects_jwt(self) -> None:
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        )
        result = scan_for_pii(f"Token: {jwt}")
        assert result.has_pii
        assert PIIType.JWT_TOKEN.value in result.pii_types_found


# ── Password hash detection ────────────────────────────────────────────

class TestPasswordHashDetection:
    def test_detects_bcrypt_hash(self) -> None:
        result = scan_for_pii("Hash: $2b$12$LJ3m4ys3Dz/bHS0v0R9Mx.7ZqXtL1B2CEwn7RQHK4C5xhBfAJEyq")
        assert result.has_pii
        assert PIIType.PASSWORD_HASH.value in result.pii_types_found
        assert "[REDACTED HASH]" in result.redacted_text


# ── Clean text ─────────────────────────────────────────────────────────

class TestCleanText:
    def test_clean_code_no_pii(self) -> None:
        code = """
def calculate_sum(a: int, b: int) -> int:
    return a + b

class UserService:
    async def get_user(self, user_id: str):
        return await self.db.get(user_id)
"""
        result = scan_for_pii(code)
        assert not result.has_pii
        assert result.finding_count == 0

    def test_clean_url_no_pii(self) -> None:
        result = scan_for_pii("Visit https://example.com/api/v1/users")
        assert not result.has_pii

    def test_empty_string(self) -> None:
        result = scan_for_pii("")
        assert not result.has_pii


# ── Filtering ──────────────────────────────────────────────────────────

class TestFiltering:
    def test_min_confidence_filter(self) -> None:
        # IP addresses have low confidence (0.6)
        result = scan_for_pii("Server: 8.8.8.8", min_confidence=0.8)
        assert PIIType.IP_ADDRESS.value not in result.pii_types_found

    def test_types_filter(self) -> None:
        text = "Email: john@secret.com, SSN: 123-45-6789"
        result = scan_for_pii(text, types_to_check={PIIType.EMAIL})
        assert PIIType.EMAIL.value in result.pii_types_found
        assert PIIType.SSN.value not in result.pii_types_found


# ── Multiple findings ──────────────────────────────────────────────────

class TestMultipleFindings:
    def test_multiple_pii_types(self) -> None:
        text = "Email: john@secret.com, SSN: 123-45-6789, Call 555-123-4567"
        result = scan_for_pii(text)
        assert result.has_pii
        assert result.finding_count >= 3

    def test_redacted_text_preserves_structure(self) -> None:
        text = "Name: John, SSN: 123-45-6789, more text here"
        result = scan_for_pii(text)
        assert "more text here" in result.redacted_text
        assert "123-45-6789" not in result.redacted_text


# ── validate_agent_output ──────────────────────────────────────────────

class TestValidateAgentOutput:
    def test_clean_output(self) -> None:
        is_clean, result = validate_agent_output("def hello(): pass")
        assert is_clean
        assert not result.has_pii

    def test_dirty_output(self) -> None:
        key = "sk_test_FAKEFAKEFAKEFAKEFAKEFAKE00"  # noqa: S105
        is_clean, result = validate_agent_output(f"API key: {key}")
        assert not is_clean
        assert result.has_pii


# ── PIIScanResult properties ───────────────────────────────────────────

class TestPIIScanResult:
    def test_finding_count(self) -> None:
        result = PIIScanResult()
        assert result.finding_count == 0

    def test_pii_types_found_empty(self) -> None:
        result = PIIScanResult()
        assert result.pii_types_found == set()
