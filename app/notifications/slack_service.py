from __future__ import annotations

import logging

import requests

from app.config import get_settings

logger = logging.getLogger("erca_ris.notifications.slack")
settings = get_settings()


def send_slack(message: str) -> dict:
    if not settings.SLACK_WEBHOOK_URL:
        logger.info("[MOCK SLACK] %s", message[:120])
        return {"status": "MOCKED", "channel": "slack"}

    try:
        resp = requests.post(settings.SLACK_WEBHOOK_URL, json={"text": message}, timeout=10)
        resp.raise_for_status()
        return {"status": "SENT", "channel": "slack"}
    except Exception as exc:
        logger.warning("Slack send failed: %s", exc)
        return {"status": "FAILED", "channel": "slack", "error": str(exc)}
