"""MAF tests: foundation (Phase 1) + Data/Validation integration (Phase 2).

Data and Validation agents run against the REAL existing services (simulator,
CSV loader, validators) using temp datasets. Remaining agents stay mock. Also
verifies the legacy PlanningOrchestrator is unaffected.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents import (
    AgentStatus,
    AgentWorkflow,
    BaseAgent,
    WorkflowContext,
    WorkflowOrchestrator,
    WorkflowState,
)
from app.agents.contracts import DataAgentOutput
from app.agents.analytics_agent import (
    AnalyticsAgent,
    ANALYTICS_FACTS_KEY,
    KPIS_KEY,
)
from app.agents.data_agent import DataAgent, FACTORY_STATE_KEY
from app.agents.di import ServiceContainer
from app.agents.errors import CriticalAgentError, RecoverableAgentError
from app.agents.planning_agent import (
    PlanningAgent,
    RULE_POLICY_KEY,
    SCHEDULE_RESULT_KEY,
)
from app.agents.recommendation_agent import (
    RECOMMENDATION_SET_KEY,
    RecommendationAgent,
)
from app.agents.registration import (
    build_default_workflow,
    build_maf_service,
    build_orchestrator,
)
from app.agents.retry import NO_RETRY, RetryPolicy
from app.agents.risk_agent import RISK_REPORT_KEY, RiskAgent
from app.agents.scenario_agent import SCENARIO_COMPARISON_KEY, ScenarioAgent
from app.agents.explanation_agent import (
    EXPLANATION_CONTEXT_KEY,
    EXPLANATION_SUMMARY_KEY,
    ExplanationAgent,
)
from app.agents.explanation_backend import ChatAnswer, ExplanationChatUnavailable
from app.explanation.schema import ExplanationSummary
from app.agents.validation_agent import VALIDATION_RESULT_KEY, ValidationAgent
from app.domain.enums import OrderStatus, SolverStatus
from app.domain.models.factory_state import FactoryState
from app.domain.models.machine import Machine
from app.domain.models.production_order import ProductionOrder
from app.domain.models.schedule import ScheduleResult
from app.ingestion import CsvDataSource, SnapshotManager
from app.main import create_app
from app.optimization import SolverOptions
from simulator.config import SimulatorConfig
from simulator.engine import SimulatorEngine

BIZ = "2026-07-17"
BIZ_DATE = date(2026, 7, 17)

EXPECTED_ORDER = [
    "data_agent",
    "validation_agent",
    "planning_agent",
    "analytics_agent",
    "risk_agent",
    "recommendation_agent",
    "scenario_agent",
    "explanation_agent",
]


def _small_config() -> SimulatorConfig:
    return SimulatorConfig(
        num_finished_products=3,
        num_raw_materials=4,
        machines_per_work_center=2,
        num_workers=8,
        initial_production_orders=4,
        initial_open_purchase_orders=3,
    )


def _ctx() -> WorkflowContext:
    return WorkflowContext(run_id="test-run", business_date=BIZ)


def _data_agent(datasets_dir: Path) -> DataAgent:
    return DataAgent(
        data_source=CsvDataSource(datasets_dir),
        snapshot=SnapshotManager(datasets_dir),
        simulator=SimulatorEngine(config=_small_config(), datasets_dir=datasets_dir),
        datasets_dir=datasets_dir,
    )


# ---------------------------------------------------------------------------
# Foundation (Phase 1)
# ---------------------------------------------------------------------------
def test_default_workflow_has_eight_agents_in_order(tmp_path: Path) -> None:
    assert build_default_workflow(tmp_path).describe() == EXPECTED_ORDER


def test_critical_failure_stops_workflow(tmp_path: Path) -> None:
    class BoomAgent(BaseAgent):
        name = "boom_agent"

        def execute(self, context: WorkflowContext):
            raise CriticalAgentError("boom")

    from app.agents.planning_agent import PlanningAgent

    workflow = AgentWorkflow(
        name="broken", agents=[_data_agent(tmp_path), BoomAgent(), PlanningAgent()]
    )
    result = WorkflowOrchestrator(workflow, NO_RETRY).run(BIZ)
    assert result.state == WorkflowState.FAILED.value
    assert "boom_agent" in [s.agent for s in result.steps]
    assert "planning_agent" not in result.completed_agents


def test_recoverable_failure_is_retried_then_succeeds() -> None:
    class FlakyAgent(BaseAgent):
        name = "flaky_agent"

        def __init__(self) -> None:
            self.calls = 0

        def execute(self, context: WorkflowContext):
            self.calls += 1
            if self.calls < 2:
                raise RecoverableAgentError("transient")
            return DataAgentOutput(agent=self.name, business_date=context.business_date)

    agent = FlakyAgent()
    result = agent.run(_ctx(), RetryPolicy(max_attempts=3, sleep=lambda _d: None))
    assert result.status is AgentStatus.SUCCESS
    assert result.attempts == 2


def test_recoverable_failure_exhausts_retries() -> None:
    class AlwaysFlaky(BaseAgent):
        name = "always_flaky"

        def execute(self, context: WorkflowContext):
            raise RecoverableAgentError("still transient")

    result = AlwaysFlaky().run(_ctx(), RetryPolicy(max_attempts=2, sleep=lambda _d: None))
    assert result.status is AgentStatus.FAILED
    assert result.attempts == 2


def test_service_container_resolves_instances_and_factories() -> None:
    container = ServiceContainer()
    container.register_instance("a", 123)
    calls = {"n": 0}

    def factory() -> str:
        calls["n"] += 1
        return "built"

    container.register_factory("b", factory)
    assert container.resolve("a") == 123
    assert container.resolve("b") == "built"
    assert container.resolve("b") == "built"
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# Phase 2 - Data & Validation integration (real services)
# ---------------------------------------------------------------------------
def test_data_agent_builds_factory_state(tmp_path: Path) -> None:
    agent = _data_agent(tmp_path)
    context = _ctx()
    result = agent.run(context, NO_RETRY)

    assert result.status is AgentStatus.SUCCESS
    state = context.shared[FACTORY_STATE_KEY]
    assert isinstance(state, FactoryState)
    assert state.business_date == BIZ
    assert state.machines and state.production_orders and state.routings
    # Snapshot was generated on disk by the existing simulator.
    assert (tmp_path / BIZ).exists()


def test_validation_agent_returns_result_and_passes(tmp_path: Path) -> None:
    context = _ctx()
    _data_agent(tmp_path).run(context, NO_RETRY)

    result = ValidationAgent().run(context, NO_RETRY)
    assert result.status is AgentStatus.SUCCESS
    validation = context.shared[VALIDATION_RESULT_KEY]
    assert validation.has_errors is False


def test_validation_agent_fails_on_invalid_state() -> None:
    context = _ctx()
    # A production order referencing a non-existent product is a fatal error.
    context.shared[FACTORY_STATE_KEY] = FactoryState(
        business_date=BIZ,
        production_orders=[
            ProductionOrder(
                order_id="O-1", product_id="GHOST", quantity=1,
                release_date=BIZ_DATE, due_date=BIZ_DATE + timedelta(days=3),
                status=OrderStatus.RELEASED,
            )
        ],
        products=[],
        machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
    )

    result = ValidationAgent().run(context, NO_RETRY)
    assert result.status is AgentStatus.FAILED
    validation = context.shared[VALIDATION_RESULT_KEY]
    assert validation.has_errors is True


def test_workflow_stops_on_validation_failure() -> None:
    from app.agents.planning_agent import PlanningAgent

    class BadDataAgent(BaseAgent):
        name = "data_agent"

        def execute(self, context: WorkflowContext) -> DataAgentOutput:
            context.shared[FACTORY_STATE_KEY] = FactoryState(
                business_date=context.business_date,
                production_orders=[
                    ProductionOrder(
                        order_id="O-1", product_id="GHOST", quantity=1,
                        release_date=BIZ_DATE, due_date=BIZ_DATE + timedelta(days=3),
                    )
                ],
                machines=[Machine(machine_id="M-1", name="X", work_center="WC")],
            )
            return DataAgentOutput(agent=self.name, business_date=context.business_date)

    workflow = AgentWorkflow(
        name="failing", agents=[BadDataAgent(), ValidationAgent(), PlanningAgent()]
    )
    result = WorkflowOrchestrator(workflow, NO_RETRY).run(BIZ)
    assert result.state == WorkflowState.FAILED.value
    assert "validation_agent" not in result.completed_agents
    assert "planning_agent" not in result.completed_agents


def test_workflow_continues_on_success(tmp_path: Path) -> None:
    # Pre-seed a small dataset so the real solver runs quickly.
    SimulatorEngine(config=_small_config(), datasets_dir=tmp_path).generate_day(BIZ_DATE)
    orchestrator = build_orchestrator(
        datasets_dir=tmp_path,
        retry=NO_RETRY,
        options=SolverOptions(max_time_seconds=5, num_search_workers=4),
    )
    result = orchestrator.run(BIZ)
    assert result.state == WorkflowState.COMPLETED.value
    assert result.completed_agents == EXPECTED_ORDER
    assert len(result.steps) == 8


def test_orchestrate_endpoint_runs_workflow(tmp_path: Path) -> None:
    from app.api.v1 import routes_orchestrate

    datasets = tmp_path / "datasets"
    outputs = tmp_path / "outputs"
    SimulatorEngine(config=_small_config(), datasets_dir=datasets).generate_day(BIZ_DATE)
    app = create_app()
    app.dependency_overrides[routes_orchestrate._service] = lambda: build_maf_service(
        datasets_dir=datasets,
        outputs_dir=outputs,
        options=SolverOptions(max_time_seconds=5, num_search_workers=4),
        retry=NO_RETRY,
        chat_backend=_FakeChatBackend(answer="Because it minimises makespan."),
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/orchestrate/run",
        json={"business_date": BIZ, "question": "Why this schedule?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "COMPLETED"
    assert body["completed_agents"] == EXPECTED_ORDER
    assert body["schedule"] is not None
    assert body["answer"] == "Because it minimises makespan."
    assert body["persisted"] is True


# ---------------------------------------------------------------------------
# Phase 3 - Planning integration (real BusinessRulesEngine + OR-Tools solver)
# ---------------------------------------------------------------------------
def test_planning_agent_invokes_solver_and_stores_results(tmp_path: Path) -> None:
    context = _ctx()
    _data_agent(tmp_path).run(context, NO_RETRY)
    ValidationAgent().run(context, NO_RETRY)

    agent = PlanningAgent(options=SolverOptions(max_time_seconds=5, num_search_workers=4))
    result = agent.run(context, NO_RETRY)

    assert result.status is AgentStatus.SUCCESS
    schedule = context.shared[SCHEDULE_RESULT_KEY]
    assert isinstance(schedule, ScheduleResult)
    assert schedule.status.value in ("OPTIMAL", "FEASIBLE")
    assert len(schedule.scheduled_operations) > 0
    # RulePolicy is resolved by the existing engine and stored.
    policy = context.shared[RULE_POLICY_KEY]
    assert policy.business_date == BIZ


def test_workflow_stops_on_infeasible_solver(tmp_path: Path) -> None:
    class InfeasibleSolver:
        def solve(self, state, policy) -> ScheduleResult:
            return ScheduleResult(
                business_date=state.business_date,
                status=SolverStatus.INFEASIBLE,
                scheduled_operations=[],
            )

    context = _ctx()
    _data_agent(tmp_path).run(context, NO_RETRY)
    ValidationAgent().run(context, NO_RETRY)

    result = PlanningAgent(solver=InfeasibleSolver()).run(context, NO_RETRY)
    assert result.status is AgentStatus.FAILED
    # Diagnostics: the infeasible schedule is still recorded in context.
    assert context.shared[SCHEDULE_RESULT_KEY].status is SolverStatus.INFEASIBLE


def test_legacy_and_maf_produce_identical_schedule(tmp_path: Path) -> None:
    from app.services import PlanningOrchestrator

    datasets = tmp_path / "datasets"
    outputs = tmp_path / "outputs"
    SimulatorEngine(config=_small_config(), datasets_dir=datasets).generate_day(BIZ_DATE)

    # Identical solver options (single worker => fully deterministic CP-SAT).
    options = SolverOptions(max_time_seconds=10, num_search_workers=1, random_seed=42)

    legacy = PlanningOrchestrator(datasets, outputs, options).run(BIZ).schedule

    context = _ctx()
    DataAgent(
        data_source=CsvDataSource(datasets),
        snapshot=SnapshotManager(datasets),
        simulator=SimulatorEngine(config=_small_config(), datasets_dir=datasets),
        datasets_dir=datasets,
    ).run(context, NO_RETRY)
    ValidationAgent().run(context, NO_RETRY)
    PlanningAgent(options=options).run(context, NO_RETRY)
    maf = context.shared[SCHEDULE_RESULT_KEY]

    # Schedules must match; wall-clock solve time naturally varies.
    assert maf.model_dump(mode="json", exclude={"solve_time_seconds"}) == legacy.model_dump(
        mode="json", exclude={"solve_time_seconds"}
    )


# ---------------------------------------------------------------------------
# Phase 4 - Analytics integration (real AnalyticsEngine)
# ---------------------------------------------------------------------------
def test_analytics_agent_computes_kpis_and_facts(tmp_path: Path) -> None:
    options = SolverOptions(max_time_seconds=5, num_search_workers=4)
    context = _ctx()
    _data_agent(tmp_path).run(context, NO_RETRY)
    ValidationAgent().run(context, NO_RETRY)
    PlanningAgent(options=options).run(context, NO_RETRY)

    result = AnalyticsAgent().run(context, NO_RETRY)
    assert result.status is AgentStatus.SUCCESS

    kpis = context.shared[KPIS_KEY]
    facts = context.shared[ANALYTICS_FACTS_KEY]
    assert kpis.business_date == BIZ
    assert "makespan_minutes" in kpis.metrics
    assert facts.business_date == BIZ
    assert facts.machine_utilization  # per-machine utilisation computed


def test_analytics_agent_fails_without_schedule() -> None:
    result = AnalyticsAgent().run(_ctx(), NO_RETRY)
    assert result.status is AgentStatus.FAILED


def test_legacy_and_maf_produce_identical_analytics(tmp_path: Path) -> None:
    from app.services import PlanningOrchestrator

    datasets = tmp_path / "datasets"
    outputs = tmp_path / "outputs"
    SimulatorEngine(config=_small_config(), datasets_dir=datasets).generate_day(BIZ_DATE)
    options = SolverOptions(max_time_seconds=10, num_search_workers=1, random_seed=42)

    legacy = PlanningOrchestrator(datasets, outputs, options).run(BIZ).kpis

    context = _ctx()
    DataAgent(
        data_source=CsvDataSource(datasets),
        snapshot=SnapshotManager(datasets),
        simulator=SimulatorEngine(config=_small_config(), datasets_dir=datasets),
        datasets_dir=datasets,
    ).run(context, NO_RETRY)
    ValidationAgent().run(context, NO_RETRY)
    PlanningAgent(options=options).run(context, NO_RETRY)
    AnalyticsAgent().run(context, NO_RETRY)
    maf = context.shared[KPIS_KEY]

    assert maf.model_dump(mode="json") == legacy.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Phase 5 - Risk integration (real RiskDetectionEngine)
# ---------------------------------------------------------------------------
def _run_through_analytics(context, datasets_dir: Path, options: SolverOptions) -> None:
    _data_agent(datasets_dir).run(context, NO_RETRY)
    ValidationAgent().run(context, NO_RETRY)
    PlanningAgent(options=options).run(context, NO_RETRY)
    AnalyticsAgent().run(context, NO_RETRY)


def test_risk_agent_detects_and_stores_report(tmp_path: Path) -> None:
    options = SolverOptions(max_time_seconds=5, num_search_workers=4)
    context = _ctx()
    _run_through_analytics(context, tmp_path, options)

    result = RiskAgent().run(context, NO_RETRY)
    assert result.status is AgentStatus.SUCCESS
    report = context.shared[RISK_REPORT_KEY]
    assert report.business_date == BIZ
    # Every risk uses a valid severity from the existing enum.
    assert all(
        r.severity.value in ("LOW", "MEDIUM", "HIGH", "CRITICAL") for r in report.risks
    )


def test_risk_agent_fails_without_schedule_or_kpis() -> None:
    # No schedule/kpis in context.
    assert RiskAgent().run(_ctx(), NO_RETRY).status is AgentStatus.FAILED


def test_legacy_and_maf_produce_identical_risks(tmp_path: Path) -> None:
    from app.services import PlanningOrchestrator

    datasets = tmp_path / "datasets"
    outputs = tmp_path / "outputs"
    SimulatorEngine(config=_small_config(), datasets_dir=datasets).generate_day(BIZ_DATE)
    options = SolverOptions(max_time_seconds=10, num_search_workers=1, random_seed=42)

    legacy = PlanningOrchestrator(datasets, outputs, options).run(BIZ).risks

    context = _ctx()
    _run_through_analytics(context, datasets, options)
    RiskAgent().run(context, NO_RETRY)
    maf = context.shared[RISK_REPORT_KEY]

    assert maf.model_dump(mode="json") == legacy.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Phase 6 - Recommendation integration (real RecommendationEngine)
# ---------------------------------------------------------------------------
def _run_through_risk(context, datasets_dir: Path, options: SolverOptions) -> None:
    _run_through_analytics(context, datasets_dir, options)
    RiskAgent().run(context, NO_RETRY)


def test_recommendation_agent_generates_and_stores_set(tmp_path: Path) -> None:
    options = SolverOptions(max_time_seconds=5, num_search_workers=4)
    context = _ctx()
    _run_through_risk(context, tmp_path, options)

    result = RecommendationAgent().run(context, NO_RETRY)
    assert result.status is AgentStatus.SUCCESS
    rec_set = context.shared[RECOMMENDATION_SET_KEY]
    assert rec_set.business_date == BIZ
    # Priority-sorted (descending) as the existing engine guarantees.
    priorities = [r.priority for r in rec_set.recommendations]
    assert priorities == sorted(priorities, reverse=True)


def test_recommendation_agent_fails_without_risk_report() -> None:
    assert RecommendationAgent().run(_ctx(), NO_RETRY).status is AgentStatus.FAILED


def test_legacy_and_maf_produce_identical_recommendations(tmp_path: Path) -> None:
    from app.services import PlanningOrchestrator

    datasets = tmp_path / "datasets"
    outputs = tmp_path / "outputs"
    SimulatorEngine(config=_small_config(), datasets_dir=datasets).generate_day(BIZ_DATE)
    options = SolverOptions(max_time_seconds=10, num_search_workers=1, random_seed=42)

    legacy = PlanningOrchestrator(datasets, outputs, options).run(BIZ).recommendations

    context = _ctx()
    _run_through_risk(context, datasets, options)
    RecommendationAgent().run(context, NO_RETRY)
    maf = context.shared[RECOMMENDATION_SET_KEY]

    assert maf.model_dump(mode="json") == legacy.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Phase 7 - Scenario integration (real ScenarioPlanningEngine)
# ---------------------------------------------------------------------------
def test_scenario_agent_compares_and_stores(tmp_path: Path) -> None:
    options = SolverOptions(max_time_seconds=3, num_search_workers=4)
    context = _ctx()
    _data_agent(tmp_path).run(context, NO_RETRY)
    ValidationAgent().run(context, NO_RETRY)
    PlanningAgent(options=options).run(context, NO_RETRY)

    result = ScenarioAgent(options=options).run(context, NO_RETRY)
    assert result.status is AgentStatus.SUCCESS
    comparison = context.shared[SCENARIO_COMPARISON_KEY]
    assert comparison.business_date == BIZ
    assert len(comparison.results) == 4  # current + overtime + alt machines + shift
    assert any(r.is_baseline for r in comparison.results)


def test_scenario_agent_fails_without_baseline_schedule() -> None:
    assert ScenarioAgent().run(_ctx(), NO_RETRY).status is AgentStatus.FAILED


def test_legacy_and_maf_produce_identical_scenarios(tmp_path: Path) -> None:
    from app.services import PlanningOrchestrator

    datasets = tmp_path / "datasets"
    outputs = tmp_path / "outputs"
    SimulatorEngine(config=_small_config(), datasets_dir=datasets).generate_day(BIZ_DATE)
    options = SolverOptions(max_time_seconds=10, num_search_workers=1, random_seed=42)

    legacy = PlanningOrchestrator(datasets, outputs, options).run(BIZ).scenario_comparison

    context = _ctx()
    _data_agent(datasets).run(context, NO_RETRY)
    ValidationAgent().run(context, NO_RETRY)
    PlanningAgent(options=options).run(context, NO_RETRY)
    ScenarioAgent(options=options).run(context, NO_RETRY)
    maf = context.shared[SCENARIO_COMPARISON_KEY]

    assert maf.model_dump(mode="json") == legacy.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Phase 8 - Explanation integration (context builder + MAF ChatAgent)
# ---------------------------------------------------------------------------
class _FakeChatBackend:
    """A fake explain-only backend; records the summary it was grounded on."""

    def __init__(self, answer: str = "MC-0001 is the bottleneck.") -> None:
        self.answer = answer
        self.received_summary = None

    def explain(self, summary, question: str) -> ChatAnswer:
        self.received_summary = summary
        return ChatAnswer(
            answer=self.answer, model="fake", prompt_tokens=12,
            completion_tokens=8, total_tokens=20, latency_ms=2.0,
        )


class _UnavailableChatBackend:
    def explain(self, summary, question: str) -> ChatAnswer:
        raise ExplanationChatUnavailable("Azure OpenAI unavailable in test.")


def _run_through_scenario(context, datasets_dir: Path, options: SolverOptions) -> None:
    _run_through_risk(context, datasets_dir, options)
    RecommendationAgent().run(context, NO_RETRY)
    ScenarioAgent(options=options).run(context, NO_RETRY)


def test_explanation_agent_builds_context(tmp_path: Path) -> None:
    options = SolverOptions(max_time_seconds=3, num_search_workers=4)
    context = WorkflowContext(run_id="t", business_date=BIZ)
    _run_through_scenario(context, tmp_path, options)

    result = ExplanationAgent(chat_backend=_FakeChatBackend()).run(context, NO_RETRY)
    assert result.status is AgentStatus.SUCCESS
    assert EXPLANATION_CONTEXT_KEY in context.shared
    assert EXPLANATION_SUMMARY_KEY in context.shared
    ctx = context.shared[EXPLANATION_CONTEXT_KEY]
    assert ctx.business_date == BIZ


def test_explanation_agent_answers_question_grounded_on_summary(tmp_path: Path) -> None:
    options = SolverOptions(max_time_seconds=3, num_search_workers=4)
    context = WorkflowContext(
        run_id="t", business_date=BIZ,
        params={"question": "Which scenario performed best?"},
    )
    _run_through_scenario(context, tmp_path, options)

    fake = _FakeChatBackend(answer="Additional Shift performed best.")
    agent = ExplanationAgent(chat_backend=fake)
    output = agent.execute(context)  # inspect the contract directly

    assert output.answer == "Additional Shift performed best."
    # The ChatAgent was grounded ONLY on the curated ExplanationSummary.
    assert isinstance(fake.received_summary, ExplanationSummary)


def test_explanation_graceful_when_chat_unavailable(tmp_path: Path) -> None:
    options = SolverOptions(max_time_seconds=3, num_search_workers=4)
    context = WorkflowContext(
        run_id="t", business_date=BIZ, params={"question": "Why is order late?"}
    )
    _run_through_scenario(context, tmp_path, options)

    result = ExplanationAgent(chat_backend=_UnavailableChatBackend()).run(context, NO_RETRY)
    # Graceful: workflow succeeds, deterministic outputs preserved, no narrative.
    assert result.status is AgentStatus.SUCCESS
    assert EXPLANATION_CONTEXT_KEY in context.shared


def test_explanation_agent_fails_without_upstream_outputs() -> None:
    result = ExplanationAgent(chat_backend=_FakeChatBackend()).run(_ctx(), NO_RETRY)
    assert result.status is AgentStatus.FAILED


def test_explanation_path_does_not_import_deterministic_engines() -> None:
    import app.agents.explanation_agent as ea
    import app.agents.explanation_backend as eb

    forbidden = [
        "from app.optimization",
        "SchedulingSolver",
        "BusinessRulesEngine",
        "AnalyticsEngine",
        "RiskDetectionEngine",
        "RecommendationEngine",
        "ScenarioPlanningEngine",
    ]
    for module in (ea, eb):
        with open(module.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for token in forbidden:
            assert token not in source, f"{module.__name__} must not reference {token}"


# ---------------------------------------------------------------------------
# MAF orchestration service - full outputs + persistence
# ---------------------------------------------------------------------------
def test_maf_service_returns_and_persists_all_artifacts(tmp_path: Path) -> None:
    datasets = tmp_path / "datasets"
    outputs = tmp_path / "outputs"
    SimulatorEngine(config=_small_config(), datasets_dir=datasets).generate_day(BIZ_DATE)

    service = build_maf_service(
        datasets_dir=datasets,
        outputs_dir=outputs,
        options=SolverOptions(max_time_seconds=5, num_search_workers=4),
        retry=NO_RETRY,
        chat_backend=_FakeChatBackend(answer="Additional Shift performed best."),
    )
    result = service.run(BIZ, question="Which scenario performed best?")

    assert result.state == "COMPLETED"
    # Every deterministic artifact is surfaced.
    assert result.schedule is not None
    assert result.kpis is not None
    assert result.risks is not None
    assert result.recommendations is not None
    assert result.scenario_comparison is not None
    assert result.explanation_summary is not None
    # Explain-only narration present (via the injected backend).
    assert result.answer == "Additional Shift performed best."
    # Persisted so the existing GET endpoints/frontend can read the results.
    assert result.persisted is True
    assert (outputs / BIZ / "schedule.json").exists()
    assert (outputs / BIZ / "explanation_context.json").exists()


# ---------------------------------------------------------------------------
# Human-in-the-Loop approval gates
# ---------------------------------------------------------------------------
def _hitl_service(tmp_path: Path):
    datasets = tmp_path / "datasets"
    outputs = tmp_path / "outputs"
    SimulatorEngine(config=_small_config(), datasets_dir=datasets).generate_day(BIZ_DATE)
    return build_maf_service(
        datasets_dir=datasets,
        outputs_dir=outputs,
        options=SolverOptions(max_time_seconds=5, num_search_workers=4),
        retry=NO_RETRY,
        chat_backend=_FakeChatBackend(),
    ), outputs


def test_hitl_pauses_at_gate(tmp_path: Path) -> None:
    service, outputs = _hitl_service(tmp_path)
    result = service.run(BIZ, pause_after=["planning_agent"])

    assert result.state == "AWAITING_APPROVAL"
    assert result.pending_gate == "planning_agent"
    assert result.completed_agents == ["data_agent", "validation_agent", "planning_agent"]
    # Downstream agents have not run; nothing persisted yet.
    assert result.kpis is None
    assert result.persisted is False
    assert not (outputs / BIZ / "schedule.json").exists()


def test_hitl_resume_approve_completes(tmp_path: Path) -> None:
    service, outputs = _hitl_service(tmp_path)
    paused = service.run(BIZ, pause_after=["planning_agent"])

    resumed = service.resume(paused.run_id, approve=True)
    assert resumed.state == "COMPLETED"
    assert resumed.completed_agents == EXPECTED_ORDER
    assert resumed.persisted is True
    assert (outputs / BIZ / "schedule.json").exists()


def test_hitl_resume_reject_cancels(tmp_path: Path) -> None:
    service, outputs = _hitl_service(tmp_path)
    paused = service.run(BIZ, pause_after=["planning_agent"])

    cancelled = service.resume(paused.run_id, approve=False)
    assert cancelled.state == "CANCELLED"
    assert cancelled.persisted is False
    assert not (outputs / BIZ / "schedule.json").exists()


def test_hitl_resume_unknown_run_raises(tmp_path: Path) -> None:
    from app.core.exceptions import NotFoundError

    service, _ = _hitl_service(tmp_path)
    with pytest.raises(NotFoundError):
        service.resume("does-not-exist", approve=True)


def test_hitl_multiple_gates_pause_sequentially(tmp_path: Path) -> None:
    service, _ = _hitl_service(tmp_path)
    first = service.run(BIZ, pause_after=["planning_agent", "scenario_agent"])
    assert first.pending_gate == "planning_agent"

    second = service.resume(first.run_id, approve=True)
    # Continues to the next gate rather than finishing.
    assert second.state == "AWAITING_APPROVAL"
    assert second.pending_gate == "scenario_agent"

    third = service.resume(second.run_id, approve=True)
    assert third.state == "COMPLETED"
    assert third.completed_agents == EXPECTED_ORDER


# ---------------------------------------------------------------------------
# Legacy path must remain unchanged
# ---------------------------------------------------------------------------
def test_legacy_planning_orchestrator_unchanged(tmp_path: Path) -> None:
    from app.optimization import SolverOptions
    from app.services import PlanningOrchestrator

    datasets = tmp_path / "datasets"
    outputs = tmp_path / "outputs"
    SimulatorEngine(config=_small_config(), datasets_dir=datasets).generate_day(BIZ_DATE)

    orchestrator = PlanningOrchestrator(
        datasets_dir=datasets,
        outputs_dir=outputs,
        options=SolverOptions(max_time_seconds=3, num_search_workers=4),
    )
    result = orchestrator.run(BIZ)
    assert result.schedule.business_date == BIZ
    assert result.schedule.status.value in ("OPTIMAL", "FEASIBLE")
    assert len(result.schedule.scheduled_operations) > 0
