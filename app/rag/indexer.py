from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models import Incident, IncidentAnalysis, Ownership, Remediation
from app.rag.vector_store import add_document

logger = logging.getLogger("erca_ris.rag.indexer")


def build_knowledge_text(
    incident: Incident,
    analysis: IncidentAnalysis | None,
    ownership: Ownership | None,
    remediation: Remediation | None,
) -> str:
    """Builds the structured knowledge-document text described in the spec."""
    lines = [
        f"Incident: {incident.incident_id}",
        f"Service: {incident.service}",
        f"Scenario: {incident.scenario or 'n/a'}",
        f"Error: {incident.error_message}",
    ]
    if analysis:
        lines += [
            f"Root Cause: {analysis.root_cause or 'n/a'}",
            f"Resolution: {analysis.recommended_resolution or 'n/a'}",
            f"Prevention: {analysis.recommended_prevention or 'n/a'}",
        ]
    if ownership:
        lines += [
            f"Owner: {ownership.owner or 'n/a'} ({ownership.team or 'n/a'})",
            f"Developer: {ownership.developer or 'n/a'}",
            f"Code: {ownership.file_path or 'n/a'}::{ownership.function_name or 'n/a'}",
        ]
    if remediation:
        lines += [
            f"PR: {remediation.github_pr_url or 'n/a'}",
            f"Test Result: {remediation.test_result or 'n/a'}",
        ]
    return "\n".join(lines)


def index_resolved_incident(
    db: Session,
    incident: Incident,
    analysis: IncidentAnalysis | None,
    ownership: Ownership | None,
    remediation: Remediation | None,
) -> None:
    """Converts a resolved incident into retrievable RAG knowledge (the feedback loop)."""
    document = build_knowledge_text(incident, analysis, ownership, remediation)
    metadata = {
        "incident_id": incident.incident_id,
        "service": incident.service,
        "scenario": incident.scenario,
        "root_cause": analysis.root_cause if analysis else None,
        "status": "RESOLVED",
    }
    add_document(db, document=document, metadata=metadata, incident_id=incident.incident_id)
    logger.info("Indexed resolved incident %s into RAG knowledge base", incident.incident_id)


def index_raw_document(db: Session, document: str, metadata: dict, incident_id: str | None = None):
    return add_document(db, document=document, metadata=metadata, incident_id=incident_id)
