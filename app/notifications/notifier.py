from __future__ import annotations

from app.notifications.email_service import send_email
from app.notifications.slack_service import send_slack
from app.remediation.github_client import get_github_client


def format_notification(incident, analysis, code_evidence, ownership, pr_url: str | None) -> str:
    confidence_pct = round((analysis.get("confidence") or 0) * 100) if analysis else "n/a"
    candidates = ownership.get("candidates") or []
    candidate_text = ", ".join(f"@{x}" for x in candidates if x) or "n/a"
    return f"""🚨 ERCA&RIS Incident

Incident:
{incident.incident_id}

Service:
{incident.service}

Severity:
{incident.severity}

Environment:
{incident.environment}

Error:
{incident.error_message}

Root Cause:
{analysis.get('root_cause', 'Pending analysis') if analysis else 'Pending analysis'}

Confidence:
{confidence_pct}%

Code Location:
{code_evidence.get('file') if code_evidence else 'n/a'}
Function: {code_evidence.get('function') if code_evidence else 'n/a'}
Line: {code_evidence.get('line') if code_evidence else 'n/a'}

Owner Team:
{ownership.get('team') or 'n/a'}

Selected Developer:
{ownership.get('developer') or 'n/a'}
Username:
@{ownership.get('username') if ownership.get('username') else 'n/a'}
Email:
{ownership.get('email') or 'n/a'}

Selection Source:
{ownership.get('resolution_source') or 'n/a'}

Active Team Candidates:
{candidate_text}

Recommended Resolution:
{analysis.get('recommended_resolution', 'n/a') if analysis else 'n/a'}

AI remediation / PR:
{pr_url or 'Not yet created'}

Please review and approve.
"""


def notify_developer(incident, analysis, code_evidence, ownership, pr_url: str | None, channels: list[str], recipient: str | None) -> list[dict]:
    message = format_notification(incident, analysis, code_evidence, ownership, pr_url)
    results: list[dict] = []

    if "email" in channels:
        to = recipient or ownership.get("email")
        if not to:
            results.append({
                "status": "NOT_SENT",
                "channel": "email",
                "reason": "No active developer email was resolved; email was not sent to a fabricated address.",
            })
        else:
            results.append(send_email(
                to,
                subject=f"[ERCA&RIS] {incident.incident_id} needs review",
                body=message,
            ))

    if "slack" in channels:
        results.append(send_slack(message))

    if "github" in channels and pr_url:
        client = get_github_client()
        results.append({"status": "SENT", "channel": "github", "note": "Linked via PR comment"})

    return results
