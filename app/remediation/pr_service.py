from __future__ import annotations

from app.remediation.github_client import get_github_client

SERVICE_LABELS = {
    "payment": "service:payment", "auth": "service:auth", "orders": "service:orders",
    "inventory": "service:inventory", "notification": "service:notification",
    "search": "service:search", "storage": "service:storage", "reports": "service:reports",
}


def build_pr_description(incident, analysis, code_evidence, ownership, rag_evidence, test_results) -> str:
    rag_lines = "\n".join(
        f"- {item['incident_id']} (similarity {item['similarity']}): "
        f"{(item['metadata'] or {}).get('root_cause', 'n/a')}"
        for item in (rag_evidence or [])[:5]
    ) or "- No sufficiently similar historical incidents found."

    return f"""## ERCA&RIS Automated Remediation

**Incident ID:** {incident.incident_id}
**Error:** {incident.error_message}

### Root Cause
{analysis.get('root_cause', 'n/a')}

### Evidence
- File: `{code_evidence.get('file')}`
- Function: `{code_evidence.get('function')}`
- Line: `{code_evidence.get('line')}`
- Exception type: `{code_evidence.get('exception_type')}`

### Affected Component
- Owner: {ownership.get('owner')}
- Team: {ownership.get('team')}
- Developer: {ownership.get('developer')}

### Recommended Fix
{analysis.get('recommended_resolution', 'n/a')}

### Test Results
- Passed: {test_results.get('passed') if test_results else 'not run yet'}

### Prevention
{analysis.get('recommended_prevention', 'n/a')}

### RAG Historical Evidence
{rag_lines}

---
*This PR was opened automatically by ERCA&RIS. It does not modify main/master
directly and requires developer review and approval before merge.*
"""


def open_remediation_pr(incident, analysis, code_evidence, ownership, rag_evidence, branch_name, patch_text, test_results) -> dict:
    client = get_github_client()

    client.create_branch(branch_name)

    patch_path = f"remediation_patches/{incident.incident_id}.patch"
    client.commit_patch(
        branch_name, patch_path, patch_text,
        message=f"ERCA&RIS: proposed remediation for {incident.incident_id}",
    )

    body = build_pr_description(incident, analysis, code_evidence, ownership, rag_evidence, test_results)
    pr = client.create_pull_request(
        branch_name=branch_name,
        title=f"[ERCA&RIS] Fix {incident.incident_id}: {incident.error_message[:60]}",
        body=body,
    )

    labels = ["erca-ris", "auto-remediation"]
    service_label = SERVICE_LABELS.get((incident.service or "").lower())
    if service_label:
        labels.append(service_label)
    client.add_labels(pr["number"], labels)
    # Git hosting APIs require a real username/login, not a display label.
    assignee = ownership.get("username")
    if assignee:
        client.assign(pr["number"], [assignee])
    client.comment(pr["number"], f"RCA summary for {incident.incident_id}:\n\n{analysis.get('root_cause', 'n/a')}")

    return pr
