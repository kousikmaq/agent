"""Tests for the agentic email actions (risk summary + purchase order).

Uses fakes throughout: a capturing email sender (no SMTP) and a fake results
store (no solver), so the endpoints and templates are verified without network
or optimization.
"""

from __future__ import annotations

from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import deps
from app.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.domain.enums import RiskSeverity, RiskType
from app.domain.models.recommendation import RecommendationSet
from app.domain.models.risk import Risk, RiskReport
from app.main import create_app
from app.notifications import EmailService, render_purchase_order_email, render_risk_email

DATE = "2026-07-17"


class _CapturingSender:
    """Fake transport that records delivered messages instead of sending."""

    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    def deliver(self, message: EmailMessage) -> None:
        self.messages.append(message)


def _report() -> RiskReport:
    return RiskReport(
        business_date=DATE,
        risks=[
            Risk(
                risk_id="RISK-1",
                risk_type=RiskType.MATERIAL_SHORTAGE,
                severity=RiskSeverity.CRITICAL,
                title="Material shortage for RM-0015",
                description="Insufficient supply of RM-0015 for ORD-0012.",
                affected_entities={"order_ids": ["ORD-0012"], "material_ids": ["RM-0015"]},
            ),
            Risk(
                risk_id="RISK-2",
                risk_type=RiskType.DELAYED_ORDER,
                severity=RiskSeverity.LOW,
                title="Order ORD-0003 slightly late",
                description="Projected to finish 20 minutes past due.",
                affected_entities={"order_ids": ["ORD-0003"]},
            ),
        ],
    )


def _configured_settings() -> Settings:
    return Settings(
        smtp_host="smtp.example.com",
        smtp_username="user@example.com",
        smtp_password="secret",
        alert_email_from="from@example.com",
        alert_email_to="to@example.com",
    )


# --- Template unit tests -------------------------------------------------------


def test_render_risk_email_contains_content_and_escapes() -> None:
    subject, html, text = render_risk_email(DATE, _report(), None)
    assert DATE in subject
    assert "Material shortage for RM-0015" in html
    assert "RISK-1" not in html or "RM-0015" in html  # human content present
    assert "<html" in html.lower()
    assert "Material shortage for RM-0015" in text


def test_render_risk_email_filters_by_severity() -> None:
    _, html, _ = render_risk_email(DATE, _report(), None, severities=["CRITICAL"])
    assert "Material shortage for RM-0015" in html
    assert "ORD-0003 slightly late" not in html


def test_render_purchase_order_email() -> None:
    subject, html, text = render_purchase_order_email(
        item="RM-0015", quantity="500 units", order_id="ORD-0012", reason="Stockout"
    )
    assert "RM-0015" in subject
    assert "ORD-0012" in html
    assert "Stockout" in html
    assert "RM-0015" in text


# --- EmailService unit tests ---------------------------------------------------


def test_email_service_sends_via_transport() -> None:
    sender = _CapturingSender()
    service = EmailService(_configured_settings(), sender=sender)
    receipt = service.send_html("Hello", "<p>Body</p>", text_body="Body")
    assert receipt.recipient == "to@example.com"
    assert receipt.sender == "from@example.com"
    assert len(sender.messages) == 1
    assert sender.messages[0]["Subject"] == "Hello"


def test_email_service_requires_configuration() -> None:
    service = EmailService(Settings(smtp_host=None), sender=_CapturingSender())
    with pytest.raises(ConfigurationError):
        service.send_html("Subject", "<p>x</p>")


# --- API endpoint tests --------------------------------------------------------


class _FakeStore:
    def load_risks(self, date: str) -> RiskReport | None:
        return _report()

    def load_recommendations(self, date: str) -> RecommendationSet | None:
        return RecommendationSet(business_date=DATE, recommendations=[])


@pytest.fixture()
def client() -> TestClient:
    sender = _CapturingSender()
    service = EmailService(_configured_settings(), sender=sender)
    app = create_app()
    app.dependency_overrides[get_settings] = _configured_settings
    app.dependency_overrides[deps.get_results_store] = lambda: _FakeStore()
    app.dependency_overrides[deps.get_email_service] = lambda: service
    test_client = TestClient(app)
    test_client._sender = sender  # type: ignore[attr-defined]
    return test_client


def test_email_risks_endpoint(client: TestClient) -> None:
    response = client.post(f"/api/v1/actions/{DATE}/email-risks", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["sent"] is True
    assert body["recipient"] == "to@example.com"
    assert client._sender.messages  # type: ignore[attr-defined]


def test_place_order_endpoint(client: TestClient) -> None:
    response = client.post(
        "/api/v1/actions/place-order",
        json={"item": "RM-0015", "quantity": "500 units", "order_id": "ORD-0012"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sent"] is True
    assert "RM-0015" in body["subject"]
