"""Agentic action endpoints: send professional emails from planning results.

These endpoints turn planning insights into real-world actions (notifying the
team of risks, requesting material replenishment, emailing per-tab reports) by
composing professional emails and dispatching them via SMTP. They never mutate
the schedule.

Every send action supports a ``preview`` mode that renders the email and returns
it (subject + HTML) without sending, powering the preview-before-send modal.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends

from app.analytics.deliveries import build_delivery_drift, build_delivery_report
from app.analytics.materials import build_materials_report
from app.analytics.shopfloor import build_shopfloor_status
from app.analytics.weekly import build_weekly_plan
from app.api.v1.deps import get_data_source, get_email_service, get_results_store
from app.api.v1.schemas import (
    EmailActionResponse,
    EmailPreviewResponse,
    EmailReportRequest,
    EmailRisksRequest,
    PlaceOrderRequest,
    RolesResponse,
)
from app.core.exceptions import DataIngestionError, NotFoundError
from app.ingestion import CsvDataSource
from app.notifications import (
    ROLES,
    EmailService,
    render_purchase_order_email,
    render_report_email,
    render_risk_email,
)
from app.services import ResultsStore
from app.utils.datetime_utils import parse_business_date

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


def _build_report_context(
    report_type: str,
    business_date: str,
    request: EmailReportRequest,
    store: ResultsStore,
    source: CsvDataSource,
) -> dict:
    """Load the extra per-tab data a report needs beyond the summary + KPIs."""
    ctx: dict = {}
    if request.scenario_type:
        ctx["scenario_type"] = request.scenario_type

    def _state():
        try:
            return source.load(business_date)
        except DataIngestionError:
            return None

    schedule = store.load_schedule(business_date)

    if report_type in ("weekly", "daily_progress"):
        state = _state()
        if state is not None and schedule is not None:
            ctx["weekly"] = build_weekly_plan(state, schedule, as_of=business_date)
    elif report_type in ("orders", "deliveries", "drift"):
        state = _state()
        if state is not None and schedule is not None:
            current = build_delivery_report(state, schedule)
            ctx["deliveries"] = current
            if report_type == "drift":
                anchor = parse_business_date(business_date)
                for back in range(1, 8):
                    prev_date = (anchor - timedelta(days=back)).isoformat()
                    prev_schedule = store.load_schedule(prev_date)
                    if prev_schedule is None:
                        continue
                    try:
                        prev_state = source.load(prev_date)
                    except DataIngestionError:
                        continue
                    prev = build_delivery_report(prev_state, prev_schedule)
                    ctx["drift"] = build_delivery_drift(current, prev)
                    break
    elif report_type == "materials":
        state = _state()
        if state is not None:
            ctx["materials"] = build_materials_report(state)
    elif report_type == "current_plan":
        ctx["modifications"] = store.load_modifications(business_date)
    elif report_type == "live_ops":
        state = _state()
        if state is not None:
            # Live-ops email deliberately excludes the risk section.
            ctx["shopfloor"] = build_shopfloor_status(state, None)

    return ctx


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
    source: Annotated[CsvDataSource, Depends(get_data_source)],
) -> EmailActionResponse | EmailPreviewResponse:
    """Compose and send (or preview) a professional report email for a tab."""
    summary = store.load_summary(business_date)
    kpis = store.load_kpis(business_date)
    if summary is None or kpis is None:
        raise NotFoundError(
            f"No results for {business_date}; run the pipeline first.",
            details={"business_date": business_date},
        )
    context = _build_report_context(
        request.report_type, business_date, request, store, source
    )
    subject, html, text = render_report_email(
        request.report_type,
        business_date,
        summary,
        kpis,
        role=request.role,
        context=context,
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
