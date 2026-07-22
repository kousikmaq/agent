"""Foundation-phase tests for the health and root endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_health_endpoint_returns_ok() -> None:
    """The liveness probe should report an ``ok`` status."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["service"]


def test_ready_endpoint_returns_ready() -> None:
    """The readiness probe should report a ``ready`` status."""
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_root_endpoint_returns_service_descriptor() -> None:
    """The service root should return a descriptor with docs and health links."""
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["docs"] == "/docs"
    assert body["health"] == "/api/v1/health"
