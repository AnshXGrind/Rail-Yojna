from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DecisionContext(BaseModel):
    asset_id: str
    observation_timestamp: datetime
    risk_probability: float = Field(ge=0.0, le=1.0)
    risk_level: str
    model_version: str
    calibration: str
    data_mode: str
    rules_triggered: list[str] = Field(default_factory=list)
    human_approval_required: bool = True


class MaintenanceRecommendation(BaseModel):
    recommendation_id: str
    asset_id: str
    created_at: datetime
    risk_probability: float = Field(ge=0.0, le=1.0)
    risk_level: str
    action: str
    rationale: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    status: str = "PENDING_REVIEW"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    event_id: str
    event_type: str
    timestamp: datetime
    actor: str
    asset_id: str | None = None
    recommendation_id: str | None = None
    model_version: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
