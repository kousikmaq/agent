"""Agentic action endpoints: send professional emails from planning results.

These endpoints turn planning insights into real-world actions (notifying the
team of risks, requesting material replenishment, emailing per-tab reports) by
composing professional emails and dispatching them via SMTP. They never mutate
the schedule.

Every send action supports a ``preview`` mode that renders the email and returns
it (subject + HTML) without sending, powering the preview-before-send modal.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_email_service, get_results_store
from app.api.v1.schemas import (
    EmailActionResponse,
    EmailPreviewResponse,
    EmailReportRequest,
    EmailRisksRequest,
    PlaceOrderRequest,
    RolesResponse,
)
from app.core.exceptions import NotFoundError
from app.notifications import (
    ROLES,
    EmailService,
    render_purchase_order_email,
    render_report_email,
    render_risk_email,
)
from app.services import ResultsStore

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("/roles", response_model=RolesResponse, summary="List report roles")
async def list_roles() -> RolesResponse:
    """Return the operational roles a report can be addressed to."""
    return RolesResponse(roles=list(ROLES))


def _dispatch(
    email: EmailService,
    subject: str,
    html: str,
    text: str,
    *,
    to: str | None,
    preview: bool,
) -> EmailActionResponse | EmailPreviewResponse:
    """Either return a preview or send, based on the ``preview`` flag."""
    if preview:
        return EmailPreviewResponse(
            subject=subject, html=html, recipient=email.resolve_recipient(to)
        )
    receipt = email.send_html(subject, html, text_body=text, to=to)
    return EmailActionResponse(
        sent=True, subject=receipt.subject, recipient=receipt.recipient
    )


@router.post(
    "/{business_date}/email-report",
    response_model=EmailActionResponse | EmailPreviewResponse,
    summary="Email (or preview) a per-tab report",
)
async def email_report(
    business_date: str,
    request: EmailReportRequest,
    store: Annotated[ResultsStore, Depends(get_results_store)],
    email: Annotated[EmailService, Depends(get_email_service)],
) -> EmailActionResponse | EmailPreviewResponse:
    """Compose and send (or preview) a professional report email for a tab."""
    summary = store.load_summary(business_date)
    kpis = store.load_kpis(business_date)
    if summary is None or kpis is None:
        raise NotFoundError(
            f"No results for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    subject, html, text = render_report_email(
        request.report_type, business_date, summary, kpis, role=request.role
    )
    return _dispatch(
        email, subject, html, text, to=request.to, preview=request.preview
    )


@router.post(
    "/{business_date}/email-risks",
    response_model=EmailActionResponse | EmailPreviewResponse,
    summary="Email (or preview) the day's risk summary",
)
async def email_risks(
    business_date: str,
    request: EmailRisksRequest,
    store: Annotated[ResultsStore, Depends(get_results_store)],
    email: Annotated[EmailService, Depends(get_email_service)],
) -> EmailActionResponse | EmailPreviewResponse:
    """Compose and send (or preview) a professional risk-summary email."""
    report = store.load_risks(business_date)
    if report is None:
        raise NotFoundError(
            f"No risk report for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    recommendations = store.load_recommendations(business_date)
    subject, html, text = render_risk_email(
        business_date, report, recommendations, severities=request.severities
    )
    return _dispatch(
        email, subject, html, text, to=request.to, preview=request.preview
    )


@router.post(
    "/place-order",
    response_model=EmailActionResponse | EmailPreviewResponse,
    summary="Email (or preview) a purchase-order / material replenishment request",
)
async def place_order(
    request: PlaceOrderRequest,
    email: Annotated[EmailService, Depends(get_email_service)],
) -> EmailActionResponse | EmailPreviewResponse:
    """Compose and send (or preview) a professional purchase-order request email."""
    subject, html, text = render_purchase_order_email(
        item=request.item,
        quantity=request.quantity,
        supplier=request.supplier,
        order_id=request.order_id,
        needed_by=request.needed_by,
        reason=request.reason,
    )
    return _dispatch(
        email, subject, html, text, to=request.to, preview=request.preview
    )
