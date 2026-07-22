"""Application configuration management.

Centralised, type-safe settings loaded from environment variables and
``.env`` files using ``pydantic-settings``. A single cached ``Settings``
instance is exposed via :func:`get_settings` so it can be injected as a
FastAPI dependency without re-parsing the environment on every request.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
# previously: from typing import Literal
# now:
from typing import Annotated, Literal

from pydantic import Field, field_validator
# previously: from pydantic_settings import BaseSettings, SettingsConfigDict
# now:
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Resolve important base directories relative to this file so the app behaves
# consistently regardless of the current working directory.
APP_DIR = Path(__file__).resolve().parent          # .../backend/app
BACKEND_DIR = APP_DIR.parent                        # .../backend
PROJECT_ROOT = BACKEND_DIR.parent                   # repository root


class Settings(BaseSettings):
    """Strongly-typed application settings.

    All values can be overridden through environment variables (optionally
    supplied via a ``.env`` file). Environment variables are matched
    case-insensitively and may be prefixed to avoid collisions.
    """

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        env_prefix="PPO_",  # Production Planning & Optimization
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application metadata ---
    app_name: str = "Production Planning & Schedule Optimization Agent"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True

    # --- API ---
    api_v1_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000

    # --- CORS (comma-separated list in the environment) ---
    # previously:
    # cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    # now: NoDecode prevents pydantic-settings from JSON-decoding the value so the
    #      comma-separated string is handled by the field_validator below.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # --- Logging ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False  # emit structured JSON logs when True

    # --- Data / output directories (used by later phases) ---
    datasets_dir: Path = BACKEND_DIR / "datasets"
    outputs_dir: Path = BACKEND_DIR / "outputs"

    # --- Optimization solver defaults (used by the optimization phase) ---
    solver_max_time_seconds: float = 30.0
    solver_random_seed: int = 42

    # --- Azure OpenAI (used by the explanation/chat phase; optional here) ---
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    # Optional API key. When set, key auth is used; otherwise Azure AD token
    # auth (DefaultAzureCredential) is used.
    azure_openai_api_key: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Allow CORS origins to be provided as a comma-separated string."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        """Return ``True`` when running in the production environment."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Using ``lru_cache`` ensures the environment is parsed once per process,
    and provides a natural seam for dependency injection / test overrides.
    """
    return Settings()
