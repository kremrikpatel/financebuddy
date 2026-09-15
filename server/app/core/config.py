from __future__ import annotations

import json
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    app_env: str = "development"
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

    @field_validator("data_encryption_key")
    @classmethod
    def _check_dek(cls, v: str) -> str:
        if len(bytes.fromhex(v)) != 32:
            raise ValueError("DATA_ENCRYPTION_KEY must be 32 bytes hex")
        return v

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
