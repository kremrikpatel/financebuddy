from __future__ import annotations

import json
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The well-known key shipped in .env.example; fine for dev/demo, never for production.
DEV_DEK = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    app_env: str = "development"  # development | demo | production
    app_name: str = "FinanceBuddy"
    secret_key: str = "dev-secret-key-change-me-must-be-32-bytes-minimum"
    database_url: str = "postgresql+asyncpg://financebuddy:financebuddy@localhost:5432/financebuddy"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = '["http://localhost:5173","tauri://localhost","http://tauri.localhost"]'
    data_encryption_key: str = "00" * 32
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    # LLM
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    ollama_base_url: str | None = None
    llm_primary_model: str = "gpt-4o-mini"
    llm_fallback_model: str = "claude-3-5-haiku-latest"
    llm_local_model: str = "llama3.1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # Bank providers
    plaid_client_id: str | None = None
    plaid_secret: str | None = None
    plaid_env: str = "sandbox"
    gocardless_secret_id: str | None = None
    gocardless_secret_key: str | None = None
    gocardless_env: str = "sandbox"
    basiq_api_key: str | None = None
    basiq_env: str = "sandbox"
    stripe_api_key: str | None = None
    stripe_webhook_secret: str | None = None

    fx_api_base: str = "https://open.er-api.com/v6/latest"

    # Social OAuth
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None

    # Observability
    langchain_tracing_v2: bool = False
    langsmith_api_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    phoenix_endpoint: str | None = None
    opik_api_key: str | None = None
    comet_project_name: str = "financebuddy"

    tesseract_cmd: str | None = None

    # JEV: deterministic pre-LLM layer (rules / direct service routing / cache)
    jev_enabled: bool = True
    jev_min_confidence: float = 0.8
    jev_cache_ttl_seconds: int = 300

    @field_validator("data_encryption_key")
    @classmethod
    def _check_dek(cls, v: str) -> str:
        if len(bytes.fromhex(v)) != 32:
            raise ValueError("DATA_ENCRYPTION_KEY must be 32 bytes hex")
        return v

    @model_validator(mode="after")
    def _refuse_dev_defaults_in_production(self) -> "Settings":
        """A live deployment must never boot on the development/demo secrets or database."""
        if not self.is_prod:
            return self
        weak = []
        if len(self.secret_key) < 32 or "change-me" in self.secret_key:
            weak.append("SECRET_KEY")
        if self.data_encryption_key in (DEV_DEK, "00" * 32):
            weak.append("DATA_ENCRYPTION_KEY")
        if "financebuddy:financebuddy@" in self.database_url or "_demo" in self.database_url:
            weak.append("DATABASE_URL")
        if weak:
            raise ValueError(f"APP_ENV=production refuses development values for: {', '.join(weak)}")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        try:
            parsed = json.loads(self.cors_origins)
            return list(parsed) if isinstance(parsed, list) else ["*"]
        except json.JSONDecodeError:
            return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
