from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.code_intelligence.scanner import analyze_code
from app.code_intelligence.codeowners import find_owner
from app.rag.rag_service import get_historical_evidence, detect_known_incident
from app.rca.llm_provider import generate_rca
from app.db.models import Incident

logger = logging.getLogger("erca_ris.rca.engine")


def run_rca(db: Session, incident: Incident) -> dict:
    """
    Full RCA pipeline for a single incident:
      1. Code intelligence (AST scan + service mapping)
      2. CODEOWNERS resolution
      3. RAG historical retrieval
      4. Known-incident detection
      5. Structured LLM (or offline reasoner) RCA generation
    Returns a dict with all sub-results plus the RCA schema output.
    """
    code_evidence = analyze_code(incident.error_message, service=incident.service)
    ownership = find_owner(code_evidence.get("file"))
    rag_evidence = get_historical_evidence(db, incident.error_message, incident.service)
    known_incident = detect_known_incident(rag_evidence)

    rca = generate_rca({
        "service": incident.service,
        "error_message": incident.error_message,
        "code_evidence": code_evidence,
        "rag_evidence": rag_evidence,
        "ownership": ownership,
    })

    return {
        "code_evidence": code_evidence,
        "ownership": ownership,
        "rag_evidence": rag_evidence,
        "known_incident": known_incident,
        "rca": rca,
    }
