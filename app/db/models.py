"""
SQLAlchemy ORM models for ERCA&RIS.

Runs against SQLite by default (zero-setup) and against PostgreSQL+pgvector
transparently if DATABASE_URL points at one. The `embedding` column is stored
as JSON (list[float]) so it works identically on both backends; when the
dialect is postgres and pgvector is installed, app/rag/vector_store.py will
additionally maintain a native `vector` column for fast ANN search.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, Enum, Boolean
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class IncidentStatus(str, enum.Enum):
    OPEN = "OPEN"
    ANALYZING = "ANALYZING"
    RCA_READY = "RCA_READY"
    ASSIGNED = "ASSIGNED"
    FIX_GENERATED = "FIX_GENERATED"
    TESTING = "TESTING"
    PR_CREATED = "PR_CREATED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(64), unique=True, index=True, nullable=False)
    service = Column(String(128), nullable=False)
    scenario = Column(String(128), nullable=True)
    error_message = Column(Text, nullable=False)
    environment = Column(String(64), default="production")
    severity = Column(String(32), default="MEDIUM")
    priority = Column(String(32), default="P3")
    status = Column(String(32), default=IncidentStatus.OPEN.value, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    analyses = relationship("IncidentAnalysis", back_populates="incident", cascade="all, delete-orphan")
    evidence = relationship("IncidentEvidence", back_populates="incident", cascade="all, delete-orphan")
    ownerships = relationship("Ownership", back_populates="incident", cascade="all, delete-orphan")
    remediations = relationship("Remediation", back_populates="incident", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="incident", cascade="all, delete-orphan")
    knowledge_documents = relationship("KnowledgeDocument", back_populates="incident", cascade="all, delete-orphan")
    transitions = relationship("IncidentTransition", back_populates="incident", cascade="all, delete-orphan")


class IncidentTransition(Base):
    """Persists every lifecycle state transition (append-only audit trail)."""
    __tablename__ = "incident_transitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=False, index=True)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    incident = relationship("Incident", back_populates="transitions")


class IncidentAnalysis(Base):
    __tablename__ = "incident_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=False, index=True)
    root_cause = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    agreement_ratio = Column(Float, default=0.0)
    recommended_resolution = Column(Text, nullable=True)
    recommended_prevention = Column(Text, nullable=True)
    analysis_status = Column(String(16), default="LOW")  # LOW|MEDIUM|HIGH|UNVERIFIED
    novel_incident = Column(Boolean, default=False)
    requires_manual_review = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    incident = relationship("Incident", back_populates="analyses")


class IncidentEvidence(Base):
    __tablename__ = "incident_evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=False, index=True)
    source_type = Column(String(32), nullable=False)  # code | rag_history | knowledge_document
    source_reference = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    similarity_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    incident = relationship("Incident", back_populates="evidence")


class Ownership(Base):
    __tablename__ = "ownership"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=False, index=True)
    owner = Column(String(128), nullable=True)
    team = Column(String(128), nullable=True)
    developer = Column(String(128), nullable=True)
    developer_username = Column(String(128), nullable=True)
    developer_email = Column(String(256), nullable=True)
    developer_active = Column(Boolean, default=True)
    resolution_source = Column(String(64), nullable=True)
    exception_type = Column(String(128), nullable=True)
    file_path = Column(String(512), nullable=True)
    function_name = Column(String(256), nullable=True)
    line_number = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    incident = relationship("Incident", back_populates="ownerships")


class Remediation(Base):
    __tablename__ = "remediation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=False, index=True)
    branch_name = Column(String(256), nullable=True)
    patch = Column(Text, nullable=True)
    test_result = Column(Text, nullable=True)
    github_pr_url = Column(String(512), nullable=True)
    github_pr_number = Column(Integer, nullable=True)
    status = Column(String(32), default="PENDING")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    incident = relationship("Incident", back_populates="remediations")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=False, index=True)
    recipient = Column(String(256), nullable=True)
    channel = Column(String(32), nullable=False)  # email | slack | github
    message = Column(Text, nullable=True)
    status = Column(String(32), default="PENDING")  # PENDING|SENT|FAILED|MOCKED
    sent_at = Column(DateTime(timezone=True), nullable=True)

    incident = relationship("Incident", back_populates="notifications")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(64), ForeignKey("incidents.incident_id"), nullable=True, index=True)
    document = Column(Text, nullable=False)
    doc_metadata = Column(JSON, default=dict)
    embedding = Column(JSON, nullable=True)  # list[float]
    created_at = Column(DateTime(timezone=True), default=utcnow)

    incident = relationship("Incident", back_populates="knowledge_documents")


def new_incident_code() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"INC-{today}-{suffix}"
