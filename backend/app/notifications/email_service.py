"""Email notification service for agentic actions.

Sends transactional emails (risk summaries, purchase-order requests) via SMTP.
Configuration is read from application settings (SMTP host/port/credentials and
default sender/recipient). The service is deliberately small and dependency-free
(standard-library ``smtplib``) so it is easy to test and reason about.

A :class:`EmailSender` protocol is exposed so a fake sender can be substituted in
tests without opening a real SMTP connection.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol, runtime_checkable

from app.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SentEmail:
    """Result of a send attempt (used for API responses and audit)."""

    subject: str
    recipient: str
    sender: str


@runtime_checkable
class EmailSender(Protocol):
    """Port for the low-level transport that delivers a composed message."""

    def deliver(self, message: EmailMessage) -> None:
        """Deliver an already-composed message, or raise on failure."""
        ...


class SmtpEmailSender:
    """SMTP transport using STARTTLS (e.g. Gmail on port 587)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def deliver(self, message: EmailMessage) -> None:
        s = self._settings
        context = ssl.create_default_context()
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as server:
            if s.smtp_use_tls:
                server.starttls(context=context)
            if s.smtp_username and s.smtp_password:
                server.login(s.smtp_username, s.smtp_password)
            server.send_message(message)


class EmailService:
    """Composes and sends HTML emails for the agentic actions.

    The underlying transport is injected (defaults to SMTP) so tests can capture
    messages without network access. Configuration is validated lazily on send so
    importing this module never requires SMTP connectivity.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        sender: EmailSender | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._sender = sender or SmtpEmailSender(self._settings)

    def _ensure_configured(self) -> None:
        s = self._settings
        missing = [
            name
            for name, value in (
                ("SMTP_HOST", s.smtp_host),
                ("SMTP_USERNAME", s.smtp_username),
                ("SMTP_PASSWORD", s.smtp_password),
                ("ALERT_EMAIL_FROM", s.alert_email_from),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(
                "Email is not configured; missing: " + ", ".join(missing) + "."
            )

    def resolve_recipient(self, to: str | None = None) -> str:
        """Return the recipient that would be used (for previews)."""
        return to or self._settings.alert_email_to or "(no recipient configured)"

    def send_html(
        self,
        subject: str,
        html_body: str,
        *,
        text_body: str | None = None,
        to: str | None = None,
    ) -> SentEmail:
        """Send an HTML email and return a :class:`SentEmail` receipt."""
        self._ensure_configured()
        recipient = to or self._settings.alert_email_to
        if not recipient:
            raise ConfigurationError(
                "No recipient configured; set ALERT_EMAIL_TO or pass 'to'."
            )
        sender = self._settings.alert_email_from
        assert sender is not None  # guaranteed by _ensure_configured

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = recipient
        message.set_content(
            text_body or "This message requires an HTML-capable email client."
        )
        message.add_alternative(html_body, subtype="html")

        logger.info("Sending email '%s' to %s", subject, recipient)
        self._sender.deliver(message)
        logger.info("Email '%s' delivered to %s", subject, recipient)
        return SentEmail(subject=subject, recipient=recipient, sender=sender)
