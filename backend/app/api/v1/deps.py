"""API dependency providers.

Constructs singletons (orchestrator, results store, chat responder) wired from
application settings, for injection into route handlers via ``Depends``.
"""

from __future__ import annotations

from functools import lru_cache

from app.chat import AzureOpenAIChatClient, ChatResponder
from app.config import get_settings
from app.ingestion import CsvDataSource
from app.notifications import EmailService
from app.services import PlanningOrchestrator, ResultsStore
from simulator.config import SimulatorConfig
from simulator.engine import SimulatorEngine


@lru_cache
def get_orchestrator() -> PlanningOrchestrator:
    """Return the shared planning orchestrator."""
    settings = get_settings()
    return PlanningOrchestrator(
        datasets_dir=settings.datasets_dir, outputs_dir=settings.outputs_dir
    )


@lru_cache
def get_results_store() -> ResultsStore:
    """Return the shared results store."""
    return get_orchestrator().store


@lru_cache
def get_data_source() -> CsvDataSource:
    """Return the CSV data source over the datasets directory."""
    return CsvDataSource(get_settings().datasets_dir)


@lru_cache
def get_simulator_engine() -> SimulatorEngine:
    """Return the stateful simulator engine for on-demand data generation."""
    settings = get_settings()
    return SimulatorEngine(config=SimulatorConfig(), datasets_dir=settings.datasets_dir)


@lru_cache
def get_chat_responder() -> ChatResponder:
    """Return the explain-only chat responder backed by Azure OpenAI."""
    return ChatResponder(AzureOpenAIChatClient())


@lru_cache
def get_email_service() -> EmailService:
    """Return the shared email service for agentic notification actions."""
    return EmailService(get_settings())
