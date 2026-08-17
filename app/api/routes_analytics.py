from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Incident, IncidentAnalysis, Ownership, Notification, Remediation

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics/summary")
def analytics_summary(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    incidents = db.query(Incident).filter(Incident.created_at >= since).all()
    all_incidents = db.query(Incident).all()
    analyses = db.query(IncidentAnalysis).all()
    owners = db.query(Ownership).all()

    severity = Counter((i.severity or "UNKNOWN").upper() for i in incidents)
    status = Counter((i.status or "UNKNOWN").upper() for i in incidents)
    services = Counter(i.service for i in incidents)
    causes = Counter(a.root_cause for a in analyses if a.root_cause)
    known = sum(1 for a in analyses if not a.novel_incident)
    novel = sum(1 for a in analyses if a.novel_incident)
    confidence_values = [a.confidence for a in analyses if a.confidence is not None]
    resolved = sum(1 for i in all_incidents if i.status == "RESOLVED")
    rca_completed = sum(1 for i in all_incidents if db.query(IncidentAnalysis).filter_by(incident_id=i.incident_id).first())

    return {
        "period_days": days,
        "total_incidents": len(all_incidents),
        "period_incidents": len(incidents),
        "open_incidents": sum(1 for i in all_incidents if i.status != "RESOLVED"),
        "critical_incidents": sum(1 for i in all_incidents if (i.severity or "").upper() == "CRITICAL"),
        "resolved_incidents": resolved,
        "rca_completed": rca_completed,
        "avg_rca_confidence": round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else 0,
        "rca_success_rate": round(resolved / len(all_incidents), 4) if all_incidents else 0,
        "known_incidents": known,
        "novel_incidents": novel,
        "severity": dict(severity),
        "status": dict(status),
        "top_services": services.most_common(8),
        "top_root_causes": causes.most_common(8),
        "owners": Counter(o.team for o in owners if o.team).most_common(8),
    }


@router.get("/analytics/timeseries")
def analytics_timeseries(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).date()
    buckets = defaultdict(int)
    for i in range(days):
        buckets[(start + timedelta(days=i)).isoformat()] = 0
    rows = db.query(Incident).filter(Incident.created_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)).all()
    for incident in rows:
        key = incident.created_at.date().isoformat()
        if key in buckets:
            buckets[key] += 1
    return [{"date": key, "count": buckets[key]} for key in sorted(buckets)]


@router.get("/notifications")
def list_notifications(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.query(Notification).order_by(Notification.id.desc()).limit(limit).all()
    return [{"id": r.id, "incident_id": r.incident_id, "channel": r.channel,
             "recipient": r.recipient, "status": r.status, "message": r.message,
             "sent_at": r.sent_at.isoformat() if r.sent_at else None} for r in rows]


@router.get("/ownership")
def list_ownership(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.query(Ownership).order_by(Ownership.id.desc()).limit(limit).all()
    return [{"incident_id": r.incident_id, "owner": r.owner, "team": r.team,
             "developer": r.developer, "developer_username": r.developer_username,
             "developer_email": r.developer_email, "developer_active": r.developer_active,
             "resolution_source": r.resolution_source, "exception_type": r.exception_type, "file_path": r.file_path,
             "function_name": r.function_name, "line_number": r.line_number} for r in rows]


@router.get("/reports/incidents.csv")
def incidents_csv(db: Session = Depends(get_db)):
    rows = db.query(Incident).order_by(Incident.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["incident_id", "service", "scenario", "error_message", "environment", "severity", "priority", "status", "created_at", "updated_at", "resolved_at"])
    for r in rows:
        writer.writerow([r.incident_id, r.service, r.scenario, r.error_message, r.environment, r.severity, r.priority,
                         r.status, r.created_at, r.updated_at, r.resolved_at])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=erca_ris_incidents.csv"})

@router.get("/remediation")
def list_remediation(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.query(Remediation).order_by(Remediation.id.desc()).limit(limit).all()
    return [{"incident_id": r.incident_id, "branch_name": r.branch_name, "test_result": r.test_result,
             "github_pr_url": r.github_pr_url, "github_pr_number": r.github_pr_number, "status": r.status,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.get("/pull-requests")
def list_pull_requests(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.query(Remediation).filter(Remediation.github_pr_url.is_not(None)).order_by(Remediation.id.desc()).limit(limit).all()
    return [{"incident_id": r.incident_id, "url": r.github_pr_url, "number": r.github_pr_number,
             "status": r.status, "test_result": r.test_result} for r in rows]
