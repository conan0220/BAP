"""Typed Backend settings loaded from environment and an optional .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BAP_",
        env_file="C:/BAP/config/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    bind_host: str = "0.0.0.0"
    bind_port: int = 12345
    database_url: str = "sqlite:///./bap-dev.db"
    jwt_signing_key: str = "development-only-key"
    access_token_minutes: int = Field(default=30, gt=0)
    refresh_token_days: int = Field(default=30, gt=0)
    log_dir: Path = Path("./logs")
    commit_sha: str = "development"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "BackendSettings":
        if self.env.lower() == "production":
            if self.jwt_signing_key == "development-only-key" or len(self.jwt_signing_key) < 32:
                raise ValueError("Production requires a non-default JWT signing key of at least 32 characters")
            if not self.database_url:
                raise ValueError("Production requires BAP_DATABASE_URL")
        return self
