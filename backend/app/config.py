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

    # --- Data persistence ---
    # When True, daily factory snapshots are additionally stored in a single
    # SQLite database (``datasets/factory.db``) which becomes the primary read
    # source. CSV snapshots are still written and are used as an automatic
    # fallback, so the existing flow is never disrupted. Set False for the
    # legacy CSV-only behaviour.
    sqlite_enabled: bool = True

    # Master-data catalog scale for the simulator. 1.0 = the default tuned plant.
    # Raising it grows the catalog (products, materials, customers, suppliers,
    # POs, and derived inventory/BOMs/routings/operations) toward 500-1000+ rows
    # while keeping the schedulable working set (orders/workers/machines) at its
    # solver-healthy size. Applies to every snapshot generated from now on.
    simulator_scale_factor: float = Field(default=1.0, gt=0)

    # --- Optimization solver defaults (used by the optimization phase) ---
    solver_max_time_seconds: float = 60.0
    solver_random_seed: int = 42

    # --- Automated planning cadence ---
    # When True, a background thread refreshes the plan for the current day and,
    # on Saturdays, publishes the next week's plans (Mon-Sat). Idempotent: days
    # already planned are skipped, so it never recomputes an existing plan.
    enable_scheduler: bool = True

    # --- Autonomous remediation ---
    # When True, after a fresh daily plan the agent auto-detects prioritised
    # orders that are late and re-plans to prioritise them (a reversible, logged
    # action). ``auto_replan_priority_max`` is the highest display priority
    # (0 = most urgent) that triggers it; the default (9) spans every prioritised
    # order so a single run remediates all the critical late orders together
    # rather than only the top one or two. ``auto_notify_email`` emails a
    # risk + replan summary to ``alert_email_to`` when an auto-action runs.
    auto_replan_enabled: bool = False
    auto_replan_priority_max: int = 9
    auto_notify_email: bool = False

    # When True, after a fresh daily plan the agent auto-places purchase orders
    # for materials below BOTH safety stock and reorder point (once per day per
    # material, de-duplicated against orders already placed that day).
    auto_reorder_enabled: bool = False

    # Safety cap on how many purchase orders a single auto-reorder run may place
    # (prioritised: below-safety first, then largest shortage). Prevents an email
    # / PO flood when the catalog is large (e.g. hundreds of items below reorder).
    # Auto-reorder sends ONE digest email per run, not one per PO.
    auto_reorder_max_per_run: int = 20

    # Auto-commit the best what-if scenario when it clearly beats the committed
    # plan: on-time delivery improves by >= gain AND cost rises by <= increase.
    # Enabled by default so each fresh daily plan adopts the best plan on its own
    # (still gated by the thresholds below, so a day with no clearly better
    # what-if correctly stays on the Current Plan).
    auto_commit_best_enabled: bool = True
    auto_commit_min_otd_gain: float = 0.03
    auto_commit_max_cost_increase: float = 15000.0

    # Auto-rebalance a machine bottleneck: when the busiest machine is at/above
    # ``util_threshold`` while another sits below ``alt_util_max``, apply the
    # Alternate-Machines plan if it shortens makespan or raises on-time delivery.
    auto_rebalance_enabled: bool = False
    auto_rebalance_util_threshold: float = 0.95
    auto_rebalance_alt_util_max: float = 0.6

    # Email one daily briefing (plan summary + what the agent did) after the
    # morning cycle; flags a risk alert when critical risks reach the threshold.
    auto_briefing_enabled: bool = False
    briefing_critical_risk_threshold: int = 20

    # Auto-resolve simple conflicts (reassign worker / reschedule maintenance)
    # and email a summary of actions to the supervisor.
    auto_resolve_conflicts_enabled: bool = False
    supervisor_email: str | None = None

    # Trigger overtime when delivery risk is high: apply the Overtime plan (if
    # it improves on-time delivery) once at-risk + late orders reach the count.
    auto_overtime_on_risk_enabled: bool = False
    overtime_risk_threshold: int = 15

    # Escalate by email when at least ``escalation_min_orders`` orders are
    # projected late by >= ``escalation_lateness_days`` days.
    auto_escalation_enabled: bool = False
    escalation_lateness_days: int = 3
    escalation_min_orders: int = 1
    escalation_email: str | None = None

    # --- Azure OpenAI (used by the explanation/chat phase; optional here) ---
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    # Optional API key. When set, key auth is used; otherwise Azure AD token
    # auth (DefaultAzureCredential) is used.
    azure_openai_api_key: str | None = None

    # --- Email / SMTP (agentic notification actions) ---
    # Uses the standard PPO_ prefix, e.g. PPO_SMTP_HOST, PPO_ALERT_EMAIL_TO.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    alert_email_from: str | None = None
    alert_email_to: str | None = None

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

    @property
    def factory_db_path(self) -> Path:
        """Path to the single global SQLite snapshot database."""
        return self.datasets_dir / "factory.db"


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Using ``lru_cache`` ensures the environment is parsed once per process,
    and provides a natural seam for dependency injection / test overrides.
    """
    return Settings()
