"""Notification services (email) for the agentic actions."""

from __future__ import annotations

from app.notifications.email_service import (
    EmailSender,
    EmailService,
    SentEmail,
    SmtpEmailSender,
)
from app.notifications.reports import ROLES, REPORT_META, render_report_email
from app.notifications.templates import (
    render_purchase_order_email,
    render_risk_email,
)

__all__ = [
    "EmailSender",
    "EmailService",
    "SentEmail",
    "SmtpEmailSender",
    "ROLES",
    "REPORT_META",
    "render_report_email",
    "render_purchase_order_email",
    "render_risk_email",
]
