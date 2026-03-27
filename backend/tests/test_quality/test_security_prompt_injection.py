"""Tests for Security-Aware Prompt Injection module."""

from __future__ import annotations

from app.quality.security_prompt_injection import (
    CodeDomain,
    SecurityLevel,
    clear_enrichment_history,
    detect_domains,
    determine_security_level,
    enrich_prompt,
    get_enrichment_history,
    get_enrichment_stats,
)

SL = SecurityLevel
CD = CodeDomain


class TestDomainDetection:
    """Detect security domains from code/prompt text."""

    def test_detect_auth_domain(self) -> None:
        code = "def login(password, username):\n    token = create_jwt()"
        assert CD.AUTH in detect_domains(code)

    def test_detect_crypto_domain(self) -> None:
        code = "from cryptography.fernet import Fernet\nencrypt(data)"
        assert CD.CRYPTO in detect_domains(code)

    def test_detect_payments_domain(self) -> None:
        assert CD.PAYMENTS in detect_domains("stripe.Charge.create(amount=1000)")

    def test_detect_database_domain(self) -> None:
        assert CD.DATABASE in detect_domains("SELECT * FROM users WHERE id = ?")

    def test_detect_file_io_domain(self) -> None:
        code = "with open(file_path, 'r') as f:\n    data = f.read()"
        assert CD.FILE_IO in detect_domains(code)

    def test_detect_network_domain(self) -> None:
        assert CD.NETWORK in detect_domains("response = requests.get(url)")

    def test_detect_user_input_domain(self) -> None:
        assert CD.USER_INPUT in detect_domains("data = Body(...)\nname = Query(None)")

    def test_detect_multiple_domains(self) -> None:
        code = (
            "password = request.form['pass']\n"
            "token = create_jwt()\ncursor.execute(sql)"
        )
        domains = detect_domains(code)
        assert CD.AUTH in domains
        assert CD.DATABASE in domains

    def test_no_domains_for_simple_code(self) -> None:
        assert len(detect_domains("x = 1 + 2\nprint(x)")) == 0

    def test_case_insensitive(self) -> None:
        assert CD.AUTH in detect_domains("PASSWORD = get_credentials()")


class TestSecurityLevel:
    """Determine security level from domains."""

    def test_standard_no_domains(self) -> None:
        assert determine_security_level([]) == SL.STANDARD

    def test_standard_general(self) -> None:
        assert determine_security_level([CD.GENERAL]) == SL.STANDARD

    def test_elevated_database(self) -> None:
        assert determine_security_level([CD.DATABASE]) == SL.ELEVATED

    def test_elevated_file_io(self) -> None:
        assert determine_security_level([CD.FILE_IO]) == SL.ELEVATED

    def test_elevated_network(self) -> None:
        assert determine_security_level([CD.NETWORK]) == SL.ELEVATED

    def test_critical_auth(self) -> None:
        assert determine_security_level([CD.AUTH]) == SL.CRITICAL

    def test_critical_crypto(self) -> None:
        assert determine_security_level([CD.CRYPTO]) == SL.CRITICAL

    def test_critical_payments(self) -> None:
        assert determine_security_level([CD.PAYMENTS]) == SL.CRITICAL

    def test_critical_overrides_elevated(self) -> None:
        level = determine_security_level([CD.DATABASE, CD.AUTH])
        assert level == SL.CRITICAL


class TestPromptEnrichment:
    """Prompt enrichment tests."""

    def setup_method(self) -> None:
        clear_enrichment_history()

    def test_basic_enrichment(self) -> None:
        enriched, record = enrich_prompt("Write a hello world function")
        assert "SECURITY REQUIREMENTS" in enriched
        assert record.rules_injected >= 8
        assert record.enriched_prompt_length > record.original_prompt_length

    def test_auth_code_adds_auth_rules(self) -> None:
        enriched, record = enrich_prompt(
            "Implement login endpoint",
            code_context="def login(password):\n    token = jwt.encode()",
        )
        assert "AUTH-SPECIFIC" in enriched
        assert CD.AUTH in record.domains_detected
        assert record.security_level == SL.CRITICAL

    def test_payments_elevates_to_critical(self) -> None:
        enriched, record = enrich_prompt(
            "Add checkout",
            code_context="stripe.Charge.create(amount=100)",
        )
        assert record.security_level == SL.CRITICAL
        assert "CRITICAL SECURITY CONTEXT" in enriched

    def test_database_code(self) -> None:
        enriched, record = enrich_prompt(
            "Write query",
            code_context="cursor.execute(sql)",
        )
        assert "DATABASE-SPECIFIC" in enriched
        assert CD.DATABASE in record.domains_detected

    def test_force_level(self) -> None:
        _, record = enrich_prompt("simple code", force_level=SL.CRITICAL)
        assert record.security_level == SL.CRITICAL

    def test_preserves_original_prompt(self) -> None:
        original = "Write a function to sort a list"
        enriched, _ = enrich_prompt(original)
        assert original in enriched

    def test_enrichment_record_id(self) -> None:
        _, record = enrich_prompt("test")
        assert record.id
        assert record.timestamp


class TestEnrichmentHistory:
    """History and analytics tests."""

    def setup_method(self) -> None:
        clear_enrichment_history()

    def test_history_recorded(self) -> None:
        enrich_prompt("test 1")
        enrich_prompt("test 2")
        assert len(get_enrichment_history()) == 2

    def test_clear_history(self) -> None:
        enrich_prompt("test")
        clear_enrichment_history()
        assert len(get_enrichment_history()) == 0

    def test_empty_stats(self) -> None:
        stats = get_enrichment_stats()
        assert stats["total_enrichments"] == 0

    def test_stats_computed(self) -> None:
        enrich_prompt("simple code")
        enrich_prompt("login with password", code_context="jwt.encode()")
        stats = get_enrichment_stats()
        assert stats["total_enrichments"] == 2
        assert "by_level" in stats
        assert "domain_frequency" in stats
        assert stats["avg_rules_per_enrichment"] >= 8

    def test_stats_by_level(self) -> None:
        enrich_prompt("x = 1")
        enrich_prompt("password auth", code_context="bcrypt.hash(password)")
        stats = get_enrichment_stats()
        assert (
            SL.STANDARD in stats["by_level"]
            or SL.CRITICAL in stats["by_level"]
        )

    def test_domain_frequency(self) -> None:
        enrich_prompt("login", code_context="password = get_pass()")
        enrich_prompt("checkout", code_context="stripe.Charge.create()")
        stats = get_enrichment_stats()
        assert stats["domain_frequency"]
