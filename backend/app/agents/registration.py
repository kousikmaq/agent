"""Workflow and dependency registration.

Builds the default planning workflow (the eight agents in order), registers them
and the orchestrator in a :class:`ServiceContainer`, and exposes a cached
accessor for the API layer. This is the single wiring point for the MAF layer.

Phase 2: the Data and Validation agents are wired to the real existing services
(simulator, snapshot manager, CSV loader, validators). The remaining agents stay
as Phase-1 mocks.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.agents.analytics_agent import AnalyticsAgent
from app.agents.data_agent import DataAgent
from app.agents.di import ServiceContainer
from app.agents.explanation_agent import ExplanationAgent
from app.agents.orchestrator import WorkflowOrchestrator
from app.agents.planning_agent import PlanningAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.retry import RetryPolicy
from app.agents.risk_agent import RiskAgent
from app.agents.scenario_agent import ScenarioAgent
from app.agents.service import MafOrchestrationService
from app.agents.validation_agent import ValidationAgent
from app.agents.workflow import AgentWorkflow
from app.config import get_settings
from app.ingestion import CsvDataSource, SnapshotManager
from app.optimization import SolverOptions
from app.services import ResultsStore
from simulator.config import SimulatorConfig
from simulator.engine import SimulatorEngine

WORKFLOW_NAME = "daily_planning"


def _build_data_agent(datasets_dir: Path) -> DataAgent:
    """Construct the Data Agent wired to the existing data services."""
    return DataAgent(
        data_source=CsvDataSource(datasets_dir),
        snapshot=SnapshotManager(datasets_dir),
        simulator=SimulatorEngine(config=SimulatorConfig(), datasets_dir=datasets_dir),
        datasets_dir=datasets_dir,
    )


def build_default_workflow(
    datasets_dir: Path | None = None,
    options: SolverOptions | None = None,
    chat_backend=None,
) -> AgentWorkflow:
    """Construct the default planning workflow with the eight agents in order.

    All agents use the real services. ``chat_backend`` overrides the Explanation
    agent's chat backend (defaults to MAF ChatAgent with an Azure OpenAI SDK
    fallback).
    """
    dd = datasets_dir or get_settings().datasets_dir
    return AgentWorkflow(
        name=WORKFLOW_NAME,
        agents=[
            _build_data_agent(dd),
            ValidationAgent(),
            PlanningAgent(options=options),
            AnalyticsAgent(),
            RiskAgent(),
            RecommendationAgent(),
            ScenarioAgent(options=options),
            ExplanationAgent(chat_backend=chat_backend),
        ],
    )


def build_orchestrator(
    datasets_dir: Path | None = None,
    retry: RetryPolicy | None = None,
    options: SolverOptions | None = None,
    chat_backend=None,
) -> WorkflowOrchestrator:
    """Build a workflow orchestrator (optionally over a custom datasets dir)."""
    return WorkflowOrchestrator(
        build_default_workflow(datasets_dir, options, chat_backend), retry or RetryPolicy()
    )


def build_maf_service(
    datasets_dir: Path | None = None,
    outputs_dir: Path | None = None,
    options: SolverOptions | None = None,
    retry: RetryPolicy | None = None,
    chat_backend=None,
) -> MafOrchestrationService:
    """Build the MAF orchestration service (workflow runner + results store)."""
    settings = get_settings()
    orchestrator = build_orchestrator(datasets_dir, retry, options, chat_backend)
    store = ResultsStore(outputs_dir or settings.outputs_dir)
    return MafOrchestrationService(orchestrator, store)


def register_dependencies(datasets_dir: Path | None = None) -> ServiceContainer:
    """Register the workflow, retry policy, and orchestrator in a container."""
    dd = datasets_dir or get_settings().datasets_dir
    container = ServiceContainer()
    container.register_instance("retry_policy", RetryPolicy())
    container.register_factory("workflow", lambda: build_default_workflow(dd))
    container.register_factory(
        "orchestrator",
        lambda: WorkflowOrchestrator(
            container.resolve("workflow"), container.resolve("retry_policy")
        ),
    )
    return container


@lru_cache
def get_maf_orchestrator() -> WorkflowOrchestrator:
    """Return the shared MAF workflow orchestrator (cached)."""
    return register_dependencies().resolve("orchestrator")


@lru_cache
def get_maf_service() -> MafOrchestrationService:
    """Return the shared MAF orchestration service (cached)."""
    return build_maf_service()
