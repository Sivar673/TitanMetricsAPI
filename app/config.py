"""Environment-driven configuration with production guardrails.

Every setting reads from a TITAN_-prefixed environment variable (or a
local .env file). Development gets safe defaults; production refuses to
boot with dev secrets or wildcard CORS.
"""

from typing import List, Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "titan-metrics-dev-secret-do-not-use-in-prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TITAN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "production"] = "development"
    database_url: str = "sqlite:///./titan_metrics.db"
    jwt_secret: str = DEV_JWT_SECRET
    token_ttl_seconds: int = 7 * 24 * 3600
    # Comma-separated exact origins, e.g. "https://app.titanmetrics.com"
    cors_origins: str = "http://localhost:8081"
    # AI Physique Coach. Unset = feature returns 503 (not configured).
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"
    # Financial guardrail: max Anthropic evaluations per user per 24h.
    ai_daily_evaluation_limit: int = 2
    upload_dir: str = "./uploads"

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _enforce_production_hardening(self) -> "Settings":
        if self.env != "production":
            return self

        problems = []
        if self.jwt_secret == DEV_JWT_SECRET:
            problems.append("TITAN_JWT_SECRET must be overridden in production")
        elif len(self.jwt_secret) < 32:
            problems.append("TITAN_JWT_SECRET must be at least 32 bytes (RFC 7518 §3.2)")
        if "*" in self.cors_origin_list:
            problems.append("TITAN_CORS_ORIGINS must list exact origins, not '*'")
        if not self.cors_origin_list:
            problems.append("TITAN_CORS_ORIGINS must not be empty")

        if problems:
            raise ValueError("; ".join(problems))
        return self


settings = Settings()
