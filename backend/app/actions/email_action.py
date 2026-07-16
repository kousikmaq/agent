"""Email action. Sends an alert via SMTP+STARTTLS when configured, otherwise writes to a
local outbox (simulation mode). Recipient is validated; credentials are never logged."""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage

from app.config import EXPORTS_DIR, OUTBOX_DIR, settings

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_SUBJECT = 200
MAX_BODY = 10000
MAX_IMAGE_BYTES = 6_000_000
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_OUTBOX = os.path.join(OUTBOX_DIR, "email_outbox.jsonl")


def _log_outbox(record: dict) -> None:
    with open(_OUTBOX, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _safe_attachment(name: str | None) -> str | None:
    """Resolve an attachment filename to a path inside EXPORTS_DIR only (no traversal)."""
    if not name:
        return None
    base = os.path.basename(name)
    path = os.path.join(EXPORTS_DIR, base)
    return path if os.path.isfile(path) else None


def _format_body(subject: str, body: str) -> str:
    """Wrap the message with a greeting and a professional signature so every email is properly
    formatted (never attachment-only)."""
    core = (body or "").strip() or (
        f"This is an automated notification from the Production & Scheduling Assistant "
        f"regarding: {subject}."
    )
    stamp = datetime.now().strftime("%d-%m-%Y %H:%M")
    return (
        "Hello,\n\n"
        f"{core}\n\n"
        "Regards,\n"
        "Production & Scheduling Assistant\n"
        f"Generated on {stamp}. This is an automated message — please do not reply."
    )


def send_alert_email(subject: str, body: str, to: str | None = None,
                     attachment: str | None = None) -> dict:
    """Send (or simulate) an email, optionally attaching a chart PNG from the exports folder.
    Returns a status dict; never raises on bad input."""
    recipient = (to or settings.alert_email_to).strip()
    subject = (subject or "").strip()[:MAX_SUBJECT]
    body = _format_body(subject, (body or "")[:MAX_BODY])
    attach_path = _safe_attachment(attachment)

    if not EMAIL_RE.match(recipient):
        return {"status": "error", "error": "invalid recipient email address"}
    if not subject:
        return {"status": "error", "error": "subject is required"}

    record = {
        "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        "to": recipient,
        "from": settings.alert_email_from,
        "subject": subject,
        "body": body,
        "attachment": os.path.basename(attach_path) if attach_path else None,
    }

    if not settings.has_smtp:
        _log_outbox({**record, "mode": "simulated"})
        return {"status": "simulated", "to": recipient, "subject": subject,
                "note": "SMTP not configured - written to local outbox"}

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.alert_email_from
        msg["To"] = recipient
        msg.set_content(body)
        if attach_path:
            with open(attach_path, "rb") as fh:
                msg.add_attachment(fh.read(), maintype="image", subtype="png",
                                   filename=os.path.basename(attach_path))
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls(context=context)
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            server.send_message(msg)
        _log_outbox({**record, "mode": "sent"})
        return {"status": "sent", "to": recipient, "subject": subject,
                "attachment": record["attachment"]}
    except Exception as exc:  # noqa: BLE001 - surface a safe message, no secrets
        return {"status": "error", "error": f"send failed: {type(exc).__name__}"}


def send_image_email(subject: str, body: str, to: str | None, image_base64: str) -> dict:
    """Decode a client-captured PNG (base64 or data URL), save it under EXPORTS_DIR with a
    server-generated name, and email it as an attachment. Path is never client-controlled."""
    raw = (image_base64 or "").split(",", 1)[-1].strip()
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return {"status": "error", "error": "invalid image data"}
    if not data.startswith(_PNG_MAGIC):
        return {"status": "error", "error": "image must be a PNG"}
    if len(data) > MAX_IMAGE_BYTES:
        return {"status": "error", "error": "image too large"}

    fname = f"insights_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
    with open(os.path.join(EXPORTS_DIR, fname), "wb") as fh:
        fh.write(data)
    return send_alert_email(subject or "Production insights", body or "Please find the attached insights report.",
                            to, attachment=fname)
