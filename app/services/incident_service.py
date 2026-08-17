from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import (
    Incident, IncidentAnalysis, IncidentEvidence, Ownership, Remediation,
    Notification, new_incident_code,
)
from app.rca.engine import run_rca
from app.remediation.patch_generator import generate_patch
from app.remediation.fixer import create_remediation_branch
from app.remediation.test_runner import run_all as run_all_tests
from app.remediation.pr_service import open_remediation_pr
from app.notifications.notifier import notify_developer
from app.rag.indexer import index_resolved_incident

logger = logging.getLogger("erca_ris.services.incident_service")


def _transition(db: Session, incident: Incident, to_status: str, note: str | None = None):
    from app.db.models import IncidentTransition
    db.add(IncidentTransition(
        incident_id=incident.incident_id,
        from_status=incident.status,
        to_status=to_status,
        note=note,
    ))
    incident.status = to_status
    db.add(incident)
    db.commit()
    db.refresh(incident)


def create_incident(db: Session, payload) -> Incident:
    incident = Incident(
        incident_id=new_incident_code(),
        service=payload.service,
        scenario=payload.scenario,
        error_message=payload.error_message,
        environment=payload.environment,
        severity=payload.severity,
        priority=payload.priority,
        status="OPEN",
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    _transition(db, incident, "OPEN", note="Incident created")
    logger.info("Created incident %s for service %s", incident.incident_id, incident.service)
    return incident


def analyze_incident(db: Session, incident: Incident) -> dict:
    """Runs the full OPEN -> ANALYZING -> RCA_READY -> ASSIGNED pipeline."""
    _transition(db, incident, "ANALYZING", note="RAG retrieval + code intelligence + RCA started")

    result = run_rca(db, incident)
    code_evidence = result["code_evidence"]
    ownership = result["ownership"]
    rag_evidence = result["rag_evidence"]
    rca = result["rca"]

    # Persist evidence
    if code_evidence.get("found"):
        db.add(IncidentEvidence(
            incident_id=incident.incident_id,
            source_type="code",
            source_reference=code_evidence.get("file"),
            content=code_evidence.get("code"),
            similarity_score=None,
        ))
    for item in rag_evidence:
        db.add(IncidentEvidence(
            incident_id=incident.incident_id,
            source_type="rag_history",
            source_reference=item.get("incident_id"),
            content=item.get("document"),
            similarity_score=item.get("similarity"),
        ))

    db.add(Ownership(
        incident_id=incident.incident_id,
        owner=ownership.get("owner"),
        team=ownership.get("team"),
        developer=ownership.get("developer"),
        developer_username=ownership.get("username"),
        developer_email=ownership.get("email"),
        developer_active=ownership.get("active", True),
        resolution_source=ownership.get("resolution_source"),
        exception_type=code_evidence.get("exception_type"),
        file_path=code_evidence.get("file"),
        function_name=code_evidence.get("function"),
        line_number=code_evidence.get("line"),
    ))

    db.add(IncidentAnalysis(
        incident_id=incident.incident_id,
        root_cause=rca["root_cause"],
        confidence=rca["confidence"],
        agreement_ratio=rca["agreement_ratio"],
        recommended_resolution=rca["recommended_resolution"],
        recommended_prevention=rca["recommended_prevention"],
        analysis_status=rca["status"],
        novel_incident=rca.get("novel_incident", False),
        requires_manual_review=rca.get("requires_manual_review", False),
    ))
    db.commit()

    _transition(db, incident, "RCA_READY", note=f"RCA complete: {rca['status']} confidence")
    _transition(db, incident, "ASSIGNED", note=f"Assigned to {ownership.get('developer')}")

    return {**result, "incident": incident}


def generate_fix(db: Session, incident: Incident) -> dict:
    analysis = db.query(IncidentAnalysis).filter_by(incident_id=incident.incident_id).order_by(IncidentAnalysis.id.desc()).first()
    ownership = db.query(Ownership).filter_by(incident_id=incident.incident_id).order_by(Ownership.id.desc()).first()
    code_evidence = {
        "file": ownership.file_path if ownership else None,
        "function": ownership.function_name if ownership else None,
        "line": ownership.line_number if ownership else None,
        "exception_type": ownership.exception_type if ownership else None,
        "found": bool(ownership and ownership.file_path),
    }
    rca = {
        "root_cause": analysis.root_cause if analysis else None,
        "recommended_resolution": analysis.recommended_resolution if analysis else None,
    }

    patch_text = generate_patch(code_evidence, rca)
    branch_info = create_remediation_branch(incident.incident_id, patch_text)

    remediation = Remediation(
        incident_id=incident.incident_id,
        branch_name=branch_info["branch_name"],
        patch=patch_text,
        status="PATCH_GENERATED",
    )
    db.add(remediation)
    db.commit()
    db.refresh(remediation)

    _transition(db, incident, "FIX_GENERATED", note=f"Patch generated on branch {branch_info['branch_name']}")
    return {"remediation": remediation, "branch_info": branch_info}


def run_tests_for_incident(db: Session, incident: Incident) -> dict:
    _transition(db, incident, "TESTING", note="Running automated tests, lint, and security scan")
    results = run_all_tests()

    remediation = db.query(Remediation).filter_by(incident_id=incident.incident_id).order_by(Remediation.id.desc()).first()
    if remediation:
        remediation.test_result = "PASSED" if results["passed"] else "FAILED"
        remediation.status = "TESTED"
        db.add(remediation)
        db.commit()

    return results


def create_github_pr(db: Session, incident: Incident) -> dict:
    analysis_row = db.query(IncidentAnalysis).filter_by(incident_id=incident.incident_id).order_by(IncidentAnalysis.id.desc()).first()
    ownership_row = db.query(Ownership).filter_by(incident_id=incident.incident_id).order_by(Ownership.id.desc()).first()
    remediation = db.query(Remediation).filter_by(incident_id=incident.incident_id).order_by(Remediation.id.desc()).first()
    evidence_rows = db.query(IncidentEvidence).filter_by(incident_id=incident.incident_id, source_type="rag_history").all()

    analysis = {
        "root_cause": analysis_row.root_cause if analysis_row else None,
        "recommended_resolution": analysis_row.recommended_resolution if analysis_row else None,
        "recommended_prevention": analysis_row.recommended_prevention if analysis_row else None,
    }
    ownership = {
        "owner": ownership_row.owner if ownership_row else None,
        "team": ownership_row.team if ownership_row else None,
        "developer": ownership_row.developer if ownership_row else None,
        "username": ownership_row.developer_username if ownership_row else None,
        "email": ownership_row.developer_email if ownership_row else None,
        "team": ownership_row.team if ownership_row else None,
        "resolution_source": ownership_row.resolution_source if ownership_row else None,
        "candidates": [],
    }
    code_evidence = {
        "file": ownership_row.file_path if ownership_row else None,
        "function": ownership_row.function_name if ownership_row else None,
        "line": ownership_row.line_number if ownership_row else None,
        "exception_type": ownership_row.exception_type if ownership_row else None,
    }
    rag_evidence = [
        {"incident_id": e.source_reference, "similarity": e.similarity_score, "metadata": {"root_cause": None}}
        for e in evidence_rows
    ]
    test_results = {"passed": remediation.test_result == "PASSED"} if remediation else {}

    if analysis_row and analysis_row.requires_manual_review:
        return {
            "blocked": True,
            "reason": "RCA requires manual review; no automated PR was created.",
            "status": "MANUAL_REVIEW_REQUIRED",
        }
    if remediation and remediation.test_result and remediation.test_result != "PASSED":
        return {
            "blocked": True,
            "reason": "Automated validation did not pass; PR creation is blocked until tests pass.",
            "status": "TEST_FAILED",
        }

    pr = open_remediation_pr(
        incident, analysis, code_evidence, ownership, rag_evidence,
        branch_name=remediation.branch_name if remediation else f"erca-ris/fix-{incident.incident_id.lower()}",
        patch_text=remediation.patch if remediation else "",
        test_results=test_results,
    )

    if remediation:
        remediation.github_pr_url = pr["url"]
        remediation.github_pr_number = pr["number"]
        remediation.status = "PR_CREATED"
        db.add(remediation)
        db.commit()

    _transition(db, incident, "PR_CREATED", note=f"PR opened: {pr['url']}")
    _transition(db, incident, "WAITING_FOR_APPROVAL", note="Awaiting developer review/approval")
    return pr


def notify(db: Session, incident: Incident, channels: list[str], recipient: str | None) -> list[dict]:
    analysis_row = db.query(IncidentAnalysis).filter_by(incident_id=incident.incident_id).order_by(IncidentAnalysis.id.desc()).first()
    ownership_row = db.query(Ownership).filter_by(incident_id=incident.incident_id).order_by(Ownership.id.desc()).first()
    remediation = db.query(Remediation).filter_by(incident_id=incident.incident_id).order_by(Remediation.id.desc()).first()

    analysis = {
        "root_cause": analysis_row.root_cause if analysis_row else None,
        "confidence": analysis_row.confidence if analysis_row else None,
        "recommended_resolution": analysis_row.recommended_resolution if analysis_row else None,
    }
    ownership = {
        "owner": ownership_row.owner if ownership_row else None,
        "developer": ownership_row.developer if ownership_row else None,
        "username": ownership_row.developer_username if ownership_row else None,
        "email": ownership_row.developer_email if ownership_row else None,
    }
    code_evidence = {
        "file": ownership_row.file_path if ownership_row else None,
        "function": ownership_row.function_name if ownership_row else None,
        "line": ownership_row.line_number if ownership_row else None,
    }

    results = notify_developer(
        incident, analysis, code_evidence, ownership,
        pr_url=remediation.github_pr_url if remediation else None,
        channels=channels, recipient=recipient,
    )

    for r in results:
        channel = r.get("channel", "unknown")
        resolved_recipient = r.get("recipient") or (ownership.get("email") if channel == "email" else None) or (ownership.get("team") if channel == "slack" else None) or recipient or ""
        status = r.get("status", "UNKNOWN")
        detail = r.get("reason") or r.get("error") or "Incident notification dispatched"
        db.add(Notification(
            incident_id=incident.incident_id,
            recipient=resolved_recipient,
            channel=channel,
            message=detail,
            status=status,
            sent_at=datetime.now(timezone.utc),
        ))
    db.commit()
    return results


def resolve_incident(db: Session, incident: Incident) -> Incident:
    incident.resolved_at = datetime.now(timezone.utc)
    db.add(incident)
    _transition(db, incident, "RESOLVED", note="Developer approved and merged the remediation")

    analysis = db.query(IncidentAnalysis).filter_by(incident_id=incident.incident_id).order_by(IncidentAnalysis.id.desc()).first()
    ownership = db.query(Ownership).filter_by(incident_id=incident.incident_id).order_by(Ownership.id.desc()).first()
    remediation = db.query(Remediation).filter_by(incident_id=incident.incident_id).order_by(Remediation.id.desc()).first()

    # Feedback loop: resolved incident becomes retrievable RAG knowledge for future incidents.
    index_resolved_incident(db, incident, analysis, ownership, remediation)

    return incident
