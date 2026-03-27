"""Tests for application configuration and security checks."""

from __future__ import annotations

from app.config import Settings

_DEFAULT_JWT = "change-me-in-production"  # noqa: S105
_STRONG_JWT = "super-secure-random-key-1234567890"  # noqa: S105
_GH_SECRET = "gh-webhook-secret"  # noqa: S105


def test_check_production_secrets_warns_on_default_jwt() -> None:
    """In production, using the default JWT_SECRET triggers a warning."""
    s = Settings(ENVIRONMENT="production", JWT_SECRET=_DEFAULT_JWT)
    warnings = s.check_production_secrets()
    assert len(warnings) >= 1
    assert any("JWT_SECRET" in w for w in warnings)


def test_check_production_secrets_warns_on_missing_github_secret() -> None:
    """In production, missing GITHUB_CLIENT_SECRET triggers a warning."""
    s = Settings(
        ENVIRONMENT="production",
        JWT_SECRET=_STRONG_JWT,
        GITHUB_CLIENT_SECRET=None,
    )
    warnings = s.check_production_secrets()
    assert any("GITHUB_CLIENT_SECRET" in w for w in warnings)


def test_check_production_secrets_no_warnings_when_configured() -> None:
    """Properly configured production settings produce no warnings."""
    s = Settings(
        ENVIRONMENT="production",
        JWT_SECRET=_STRONG_JWT,
        GITHUB_CLIENT_SECRET=_GH_SECRET,
    )
    warnings = s.check_production_secrets()
    assert warnings == []


def test_check_production_secrets_no_warnings_in_dev() -> None:
    """Development environment never produces production warnings."""
    s = Settings(ENVIRONMENT="development", JWT_SECRET=_DEFAULT_JWT)
    warnings = s.check_production_secrets()
    assert warnings == []


def test_cors_origins_from_string() -> None:
    """CORS_ORIGINS can be parsed from a comma-separated string."""
    s = Settings(CORS_ORIGINS="http://a.com, http://b.com")  # type: ignore[arg-type]
    assert s.CORS_ORIGINS == ["http://a.com", "http://b.com"]


def test_log_level_normalised_to_upper() -> None:
    """LOG_LEVEL is normalised to uppercase."""
    s = Settings(LOG_LEVEL="debug")
    assert s.LOG_LEVEL == "DEBUG"
