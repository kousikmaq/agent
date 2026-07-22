"""Phase 13 tests: the FastAPI endpoints.

Drives the API end to end with the TestClient: generate a small snapshot, run
the pipeline, then retrieve every artifact and exercise the chat endpoint with a
fake (dependency-overridden) chat client.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import deps
from app.chat.responder import ChatResponse
from app.config import Settings, get_settings
from app.main import create_app
from app.services import PlanningOrchestrator, ResultsStore
from app.optimization import SolverOptions
from simulator.config import SimulatorConfig
from simulator.engine import SimulatorEngine

BIZ = "2026-07-17"


class _FakeResponder:
    """Stand-in chat responder that echoes a canned answer."""

    def answer(self, context, question: str) -> ChatResponse:
        return ChatResponse(
            business_date=context.business_date,
            question=question,
            answer="Grounded test answer.",
        )

    def answer_from_summary(self, summary, question: str) -> ChatResponse:
        return ChatResponse(
            business_date=summary.business_date,
            question=question,
            answer="Grounded test answer.",
        )


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    """A TestClient with datasets/outputs redirected to a temp directory."""
    datasets = tmp_path / "datasets"
    outputs = tmp_path / "outputs"

    settings = Settings(datasets_dir=datasets, outputs_dir=outputs)

    # Small factory + fast solver keep the pipeline quick for tests.
    config = SimulatorConfig(
        num_finished_products=3,
        num_raw_materials=4,
        machines_per_work_center=2,
        num_workers=8,
        initial_production_orders=4,
        initial_open_purchase_orders=3,
    )
    orchestrator = PlanningOrchestrator(
        datasets_dir=datasets,
        outputs_dir=outputs,
        options=SolverOptions(max_time_seconds=3, num_search_workers=4),
    )
    sim_engine = SimulatorEngine(config=config, datasets_dir=datasets)

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.get_orchestrator] = lambda: orchestrator
    app.dependency_overrides[deps.get_results_store] = lambda: orchestrator.store
    app.dependency_overrides[deps.get_simulator_engine] = lambda: sim_engine
    app.dependency_overrides[deps.get_chat_responder] = lambda: _FakeResponder()
    return TestClient(app)


def test_health_still_works(client: TestClient) -> None:
    assert client.get("/api/v1/health").status_code == 200


def test_generate_then_run_then_fetch_all(client: TestClient) -> None:
    # 1. Generate a daily snapshot.
    gen = client.post("/api/v1/data/generate", json={"business_date": BIZ})
    assert gen.status_code == 200
    assert gen.json()["business_date"] == BIZ

    # Dates now list the generated snapshot.
    dates = client.get("/api/v1/data/dates").json()["dates"]
    assert BIZ in dates

    # Snapshot retrieval returns a factory state.
    snap = client.get(f"/api/v1/data/{BIZ}")
    assert snap.status_code == 200
    assert snap.json()["business_date"] == BIZ
    assert snap.json()["machines"]

    # 2. Run the planning pipeline.
    run = client.post("/api/v1/schedule/run", json={"business_date": BIZ})
    assert run.status_code == 200
    assert run.json()["business_date"] == BIZ

    # 3. Fetch every persisted artifact.
    assert client.get(f"/api/v1/schedule/{BIZ}").status_code == 200
    assert client.get(f"/api/v1/analytics/{BIZ}").status_code == 200
    assert client.get(f"/api/v1/risks/{BIZ}").status_code == 200
    assert client.get(f"/api/v1/recommendations/{BIZ}").status_code == 200
    assert client.get(f"/api/v1/scenarios/{BIZ}").status_code == 200
    assert client.get(f"/api/v1/chat/{BIZ}/context").status_code == 200


def test_chat_endpoint_answers(client: TestClient) -> None:
    client.post("/api/v1/data/generate", json={"business_date": BIZ})
    client.post("/api/v1/schedule/run", json={"business_date": BIZ})

    response = client.post(
        f"/api/v1/chat/{BIZ}", json={"question": "Is the schedule feasible?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Grounded test answer."
    assert body["question"] == "Is the schedule feasible?"


def test_missing_results_return_404(client: TestClient) -> None:
    assert client.get("/api/v1/schedule/2099-01-01").status_code == 404
    assert client.get("/api/v1/analytics/2099-01-01").status_code == 404
    assert client.get("/api/v1/risks/2099-01-01").status_code == 404


def test_invalid_date_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/data/not-a-date")
    assert response.status_code == 422
