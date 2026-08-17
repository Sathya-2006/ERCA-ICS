from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class IncidentCreate(BaseModel):
    service: str
    scenario: Optional[str] = None
    error_message: str
    environment: str = "production"
    severity: str = "MEDIUM"
    priority: str = "P3"


class IncidentOut(BaseModel):
    incident_id: str
    service: str
    scenario: Optional[str]
    error_message: str
    environment: str
    severity: str
    priority: str
    status: str
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class EvidenceOut(BaseModel):
    source_type: str
    source_reference: Optional[str]
    content: Optional[str]
    similarity_score: Optional[float]

    model_config = ConfigDict(from_attributes=True)


class OwnershipOut(BaseModel):
    owner: Optional[str]
    team: Optional[str]
    developer: Optional[str]
    file_path: Optional[str]
    function_name: Optional[str]
    line_number: Optional[int]

    model_config = ConfigDict(from_attributes=True)


class AnalysisOut(BaseModel):
    root_cause: Optional[str]
    confidence: float
    agreement_ratio: float
    recommended_resolution: Optional[str]
    recommended_prevention: Optional[str]
    analysis_status: str
    novel_incident: bool = False
    requires_manual_review: bool = False

    model_config = ConfigDict(from_attributes=True)


class RemediationOut(BaseModel):
    branch_name: Optional[str]
    patch: Optional[str]
    test_result: Optional[str]
    github_pr_url: Optional[str]
    github_pr_number: Optional[int]
    status: str

    model_config = ConfigDict(from_attributes=True)


class TimelineEntry(BaseModel):
    from_status: Optional[str]
    to_status: str
    note: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RagSearchRequest(BaseModel):
    query: str
    top_k: int = 5


class RagIndexRequest(BaseModel):
    document: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    incident_id: Optional[str] = None


class NotifyRequest(BaseModel):
    channels: list[str] = Field(default_factory=lambda: ["email", "slack"])
    recipient: Optional[str] = None
