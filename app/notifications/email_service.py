from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from app.config import get_settings

logger = logging.getLogger("erca_ris.notifications.email")
settings = get_settings()


def send_email(recipient: str, subject: str, body: str) -> dict:
    if not (settings.SMTP_HOST and settings.SMTP_USERNAME and settings.SMTP_PASSWORD):
        logger.info("[MOCK EMAIL] to=%s subject=%s", recipient, subject)
        return {"status": "MOCKED", "channel": "email", "recipient": recipient}

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.NOTIFY_EMAIL_FROM
        msg["To"] = recipient

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(settings.NOTIFY_EMAIL_FROM, [recipient], msg.as_string())

        return {"status": "SENT", "channel": "email", "recipient": recipient}
    except Exception as exc:
        logger.warning("Email send failed: %s", exc)
        return {"status": "FAILED", "channel": "email", "recipient": recipient, "error": str(exc)}
