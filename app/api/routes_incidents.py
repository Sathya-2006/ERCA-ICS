from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import (
    Incident, IncidentAnalysis, IncidentEvidence, Ownership, Remediation, IncidentTransition, Notification, KnowledgeDocument
)
from app.schemas import IncidentCreate, NotifyRequest
from app.services import incident_service

logger = logging.getLogger("erca_ris.api.incidents")
router = APIRouter(prefix="/api/incidents", tags=["incidents"])


def _get_or_404(db: Session, incident_id: str) -> Incident:
    incident = db.query(Incident).filter_by(incident_id=incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident


@router.post("")
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db)):
    incident = incident_service.create_incident(db, payload)
    # Kick off analysis automatically so the demo app gets a full result in one call,
    # matching the "capture -> create -> analyze" flow described in the spec.
    result = incident_service.analyze_incident(db, incident)
    return _serialize_full(db, incident, result)


@router.get("")
def list_incidents(db: Session = Depends(get_db)):
    rows = db.query(Incident).order_by(Incident.created_at.desc()).all()
    return [_serialize_incident(r) for r in rows]


@router.get("/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    incident = _get_or_404(db, incident_id)
    return _serialize_full(db, incident)


@router.post("/{incident_id}/analyze")
def analyze(incident_id: str, db: Session = Depends(get_db)):
    incident = _get_or_404(db, incident_id)
    result = incident_service.analyze_incident(db, incident)
    return _serialize_full(db, incident, result)


@router.get("/{incident_id}/evidence")
def get_evidence(incident_id: str, db: Session = Depends(get_db)):
    _get_or_404(db, incident_id)
    rows = db.query(IncidentEvidence).filter_by(incident_id=incident_id).all()
    return [
        {"source_type": r.source_type, "source_reference": r.source_reference,
         "content": r.content, "similarity_score": r.similarity_score}
        for r in rows
    ]


@router.get("/{incident_id}/ownership")
def get_ownership(incident_id: str, db: Session = Depends(get_db)):
    _get_or_404(db, incident_id)
    row = db.query(Ownership).filter_by(incident_id=incident_id).order_by(Ownership.id.desc()).first()
    if not row:
        return {}
    return {
        "owner": row.owner, "team": row.team, "developer": row.developer,
        "developer_username": row.developer_username, "developer_email": row.developer_email,
        "developer_active": row.developer_active, "resolution_source": row.resolution_source,
        "exception_type": row.exception_type,
        "file_path": row.file_path, "function_name": row.function_name, "line_number": row.line_number,
    }


@router.post("/{incident_id}/remediation")
def generate_fix(incident_id: str, db: Session = Depends(get_db)):
    incident = _get_or_404(db, incident_id)
    result = incident_service.generate_fix(db, incident)
    remediation = result["remediation"]
    return {
        "branch_name": remediation.branch_name,
        "patch": remediation.patch,
        "status": remediation.status,
        "branch_info": result["branch_info"],
    }


@router.post("/{incident_id}/tests")
def run_tests(incident_id: str, db: Session = Depends(get_db)):
    incident = _get_or_404(db, incident_id)
    return incident_service.run_tests_for_incident(db, incident)


@router.post("/{incident_id}/github-pr")
def create_pr(incident_id: str, db: Session = Depends(get_db)):
    incident = _get_or_404(db, incident_id)
    return incident_service.create_github_pr(db, incident)


@router.post("/{incident_id}/notify")
def notify(incident_id: str, payload: NotifyRequest, db: Session = Depends(get_db)):
    incident = _get_or_404(db, incident_id)
    results = incident_service.notify(db, incident, payload.channels, payload.recipient)
    return {"results": results}


@router.post("/{incident_id}/resolve")
def resolve(incident_id: str, db: Session = Depends(get_db)):
    incident = _get_or_404(db, incident_id)
    incident_service.resolve_incident(db, incident)
    return _serialize_full(db, incident)


@router.get("/{incident_id}/timeline")
def timeline(incident_id: str, db: Session = Depends(get_db)):
    _get_or_404(db, incident_id)
    rows = db.query(IncidentTransition).filter_by(incident_id=incident_id).order_by(IncidentTransition.created_at.asc()).all()
    return [
        {"from_status": r.from_status, "to_status": r.to_status, "note": r.note,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]


@router.get("/{incident_id}/code")
def get_code_context(incident_id: str, db: Session = Depends(get_db)):
    """Return a safe source snippet around the code location identified by RCA."""
    incident = _get_or_404(db, incident_id)
    ownership = db.query(Ownership).filter_by(incident_id=incident_id).order_by(Ownership.id.desc()).first()
    if not ownership or not ownership.file_path:
        return {"found": False, "message": "No code location was identified."}

    from pathlib import Path
    from app.config import get_settings
    settings = get_settings()
    root = settings.PROJECT_ROOT.resolve()
    path = (root / ownership.file_path).resolve()
    source_root = settings.SOURCE_ROOT.resolve()
    try:
        path.relative_to(source_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Code path is outside the configured source repository")
    if not path.exists() or not path.is_file():
        return {"found": False, "file": ownership.file_path, "message": "Source file is not available locally."}

    lines = path.read_text(encoding="utf-8").splitlines()
    line = ownership.line_number or 1
    start = max(1, line - 5)
    end = min(len(lines), line + 5)
    snippet = [
        {"line": number, "text": lines[number - 1], "highlight": number == line}
        for number in range(start, end + 1)
    ]
    return {"found": True, "file": ownership.file_path, "function": ownership.function_name,
            "line": line, "snippet": snippet, "error_message": incident.error_message}


@router.get("/{incident_id}/notifications")
def get_notifications(incident_id: str, db: Session = Depends(get_db)):
    _get_or_404(db, incident_id)
    rows = db.query(Notification).filter_by(incident_id=incident_id).order_by(Notification.id.desc()).all()
    return [{"channel": r.channel, "recipient": r.recipient, "status": r.status, "message": r.message,
             "sent_at": r.sent_at.isoformat() if r.sent_at else None} for r in rows]


def _serialize_incident(incident: Incident) -> dict:
    return {
        "incident_id": incident.incident_id,
        "service": incident.service,
        "scenario": incident.scenario,
        "error_message": incident.error_message,
        "environment": incident.environment,
        "severity": incident.severity,
        "priority": incident.priority,
        "status": incident.status,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "updated_at": incident.updated_at.isoformat() if incident.updated_at else None,
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
    }


def _serialize_full(db: Session, incident: Incident, live_result: dict | None = None) -> dict:
    base = _serialize_incident(incident)

    analysis = db.query(IncidentAnalysis).filter_by(incident_id=incident.incident_id).order_by(IncidentAnalysis.id.desc()).first()
    ownership = db.query(Ownership).filter_by(incident_id=incident.incident_id).order_by(Ownership.id.desc()).first()
    remediation = db.query(Remediation).filter_by(incident_id=incident.incident_id).order_by(Remediation.id.desc()).first()
    evidence = db.query(IncidentEvidence).filter_by(incident_id=incident.incident_id).all()

    base["analysis"] = {
        "root_cause": analysis.root_cause, "confidence": analysis.confidence,
        "agreement_ratio": analysis.agreement_ratio,
        "recommended_resolution": analysis.recommended_resolution,
        "recommended_prevention": analysis.recommended_prevention,
        "analysis_status": analysis.analysis_status,
    } if analysis else None

    base["ownership"] = {
        "owner": ownership.owner, "team": ownership.team, "developer": ownership.developer,
        "developer_username": ownership.developer_username, "developer_email": ownership.developer_email,
        "developer_active": ownership.developer_active, "resolution_source": ownership.resolution_source,
        "exception_type": ownership.exception_type,
        "file_path": ownership.file_path, "function_name": ownership.function_name,
        "line_number": ownership.line_number,
    } if ownership else None

    base["remediation"] = {
        "branch_name": remediation.branch_name, "patch": remediation.patch,
        "test_result": remediation.test_result, "github_pr_url": remediation.github_pr_url,
        "github_pr_number": remediation.github_pr_number, "status": remediation.status,
    } if remediation else None

    base["evidence"] = [
        {"source_type": e.source_type, "source_reference": e.source_reference,
         "content": e.content, "similarity_score": e.similarity_score}
        for e in evidence
    ]

    known = live_result.get("known_incident") if live_result else None
    if known is None:
        threshold = __import__("app.config", fromlist=["get_settings"]).get_settings().RAG_KNOWN_INCIDENT_THRESHOLD
        historical = [e for e in evidence if e.source_type == "rag_history" and e.similarity_score is not None]
        if historical and historical[0].similarity_score >= threshold:
            doc = db.query(KnowledgeDocument).filter_by(incident_id=historical[0].source_reference).order_by(KnowledgeDocument.id.desc()).first()
            known = {
                "previous_incident_id": historical[0].source_reference,
                "similarity": historical[0].similarity_score,
                "previous_root_cause": (doc.doc_metadata or {}).get("root_cause") if doc else None,
            }
    base["known_incident"] = known

    return base
