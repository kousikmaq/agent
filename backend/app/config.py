"""Application configuration loaded from environment / .env (no secrets in code)."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---- paths (resolved relative to this file, not the CWD) --------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(APP_DIR)
PROJECT_DIR = os.path.dirname(BACKEND_DIR)

DATA_DIR = os.path.join(BACKEND_DIR, "data", "star")
MODELS_DIR = os.path.join(BACKEND_DIR, "models")
EXPORTS_DIR = os.path.join(BACKEND_DIR, "exports")
OUTBOX_DIR = os.path.join(APP_DIR, "actions", "outbox")
CACHE_DB = os.path.join(BACKEND_DIR, "semantic_cache.db")

for _d in (MODELS_DIR, EXPORTS_DIR, OUTBOX_DIR):
    os.makedirs(_d, exist_ok=True)

_PLACEHOLDERS = {"", "key", "replace-with-your-key", "your-key-here"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(PROJECT_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Azure OpenAI (LLM only)
    azure_openai_endpoint: str = Field(default="https://maqopenai.openai.azure.com/")
    azure_openai_api_key: SecretStr = Field(default=SecretStr(""))
    azure_openai_api_version: str = Field(default="2024-12-01-preview")
    azure_openai_deployment: str = Field(default="gpt-4o")

    # SMTP for the email action (optional -> simulation mode if unset)
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_username: str = Field(default="")
    smtp_password: SecretStr = Field(default=SecretStr(""))
    alert_email_from: str = Field(default="planner-agent@example.com")
    alert_email_to: str = Field(default="operations@example.com")

    # App
    app_env: str = Field(default="local")
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")
    auto_setup: bool = Field(default=True)  # train models on startup if missing

    @property
    def has_azure(self) -> bool:
        return self.azure_openai_api_key.get_secret_value() not in _PLACEHOLDERS

    @property
    def has_smtp(self) -> bool:
        return bool(self.smtp_host) and self.smtp_password.get_secret_value() != ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
