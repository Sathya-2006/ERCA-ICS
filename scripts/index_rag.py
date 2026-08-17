"""
Re-indexes every RESOLVED incident currently in the database into the RAG
knowledge store. Useful after a bulk import, or after switching embedding
providers (EMBEDDING_PROVIDER) and wanting to regenerate all vectors.

Usage:
    python -m scripts.index_rag
"""
import logging

from app.db.database import session_scope
from app.db.models import Incident, IncidentAnalysis, Ownership, Remediation
from app.rag.indexer import index_resolved_incident

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("erca_ris.index_rag")


def run():
    with session_scope() as db:
        resolved = db.query(Incident).filter_by(status="RESOLVED").all()
        for incident in resolved:
            analysis = db.query(IncidentAnalysis).filter_by(incident_id=incident.incident_id).order_by(IncidentAnalysis.id.desc()).first()
            ownership = db.query(Ownership).filter_by(incident_id=incident.incident_id).order_by(Ownership.id.desc()).first()
            remediation = db.query(Remediation).filter_by(incident_id=incident.incident_id).order_by(Remediation.id.desc()).first()
            index_resolved_incident(db, incident, analysis, ownership, remediation)
            logger.info("Re-indexed %s", incident.incident_id)
        logger.info("Re-indexed %s resolved incidents.", len(resolved))


if __name__ == "__main__":
    run()
