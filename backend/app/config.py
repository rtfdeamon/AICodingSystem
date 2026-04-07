"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the AI Coding Pipeline backend.

    All values are read from environment variables (or a `.env` file located in
    the project root).  Secrets such as API keys should **never** be committed
    to version control.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Core ────────────────────────────────────────────────────────────
    APP_NAME: str = "AI Coding Pipeline"
    ENVIRONMENT: str = Field(
        default="development",
        description="Runtime environment: 'development', 'staging', or 'production'.",
    )
    LOG_LEVEL: str = "INFO"

    # ── Database ────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./aicoding.db",
        description="Async database connection string. Use postgresql+asyncpg:// for production.",
    )

    # ── Redis ───────────────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL used for caching, rate-limiting, and pub/sub.",
    )

    # ── JWT ──────────────────────────────────────────────────────────────
    JWT_SECRET: str = Field(
        default="change-me-in-production",
        description="Secret key used to sign JWTs.",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # ── AI Provider Keys (optional) ─────────────────────────────────────
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GOOGLE_AI_API_KEY: str | None = None

    # ── GitHub OAuth (optional) ─────────────────────────────────────────
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None
    GITHUB_TOKEN: str | None = None
    GITHUB_OWNER: str | None = None
    GITHUB_REPO: str | None = None

    # ── n8n Workflow Engine (optional) ──────────────────────────────────
    N8N_BASE_URL: str | None = None
    N8N_WEBHOOK_SECRET: str | None = None

    # ── Pipeline ───────────────────────────────────────────────────────
    REPO_BASE_PATH: str = "./repos"
    PROMETHEUS_URL: str = "http://prometheus:9090"

    # ── Messaging (optional) ────────────────────────────────────────────
    SLACK_BOT_TOKEN: str | None = None
    TELEGRAM_BOT_TOKEN: str | None = None

    # ── CORS ────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Accept a comma-separated string **or** a JSON list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def normalise_log_level(cls, v: str) -> str:
        return v.upper()

    def check_production_secrets(self) -> list[str]:
        """Return a list of warnings for insecure defaults in production."""
        warnings: list[str] = []
        if self.ENVIRONMENT == "production":
            if self.JWT_SECRET == "change-me-in-production":
                warnings.append(
                    "CRITICAL: JWT_SECRET still uses default value in production. "
                    "Set a strong random secret via the JWT_SECRET env var."
                )
            if not self.GITHUB_CLIENT_SECRET:
                warnings.append(
                    "WARNING: GITHUB_CLIENT_SECRET not set — GitHub webhooks will be rejected."
                )
        return warnings


settings = Settings()
