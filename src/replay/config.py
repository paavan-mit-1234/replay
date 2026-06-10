"""Configuration loaded from environment via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Read once, from the environment."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database.
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/replay",
        alias="REPLAY_DATABASE_URL",
    )

    # Vault.
    vault_key: str = Field(default="", alias="REPLAY_VAULT_KEY")
    vault_keys_old: str = Field(default="", alias="REPLAY_VAULT_KEYS_OLD")

    # Supabase auth.
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_jwks_url: str = Field(default="", alias="SUPABASE_JWKS_URL")
    supabase_jwt_aud: str = Field(default="authenticated", alias="SUPABASE_JWT_AUD")

    # Proxy.
    max_body_bytes: int = Field(default=2_097_152, alias="REPLAY_MAX_BODY_BYTES")
    upstream_connect_timeout: float = Field(default=10.0, alias="REPLAY_UPSTREAM_CONNECT_TIMEOUT")
    upstream_read_timeout: float = Field(default=600.0, alias="REPLAY_UPSTREAM_READ_TIMEOUT")

    # Retention.
    retention_days: int = Field(default=30, alias="REPLAY_RETENTION_DAYS")

    # Logging.
    log_level: str = Field(default="INFO", alias="REPLAY_LOG_LEVEL")

    # CLI.
    api_url: str = Field(default="http://localhost:8000", alias="REPLAY_API_URL")

    # Dashboard CORS. Comma separated list of allowed origins.
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173", alias="REPLAY_CORS_ORIGINS"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def auth_enabled(self) -> bool:
        """JWT verification is active only when Supabase is configured."""
        return bool(self.supabase_jwks_url)

    @property
    def vault_decrypt_keys(self) -> list[str]:
        """Primary key first, then any rotation keys, for decryption attempts."""
        keys = [self.vault_key] if self.vault_key else []
        if self.vault_keys_old:
            keys.extend(k.strip() for k in self.vault_keys_old.split(",") if k.strip())
        return keys


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
