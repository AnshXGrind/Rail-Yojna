from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanningSummary(BaseModel):
    candidate_tasks: int
    selected_tasks: int
    deferred_tasks: int
    selected_minutes: int
    selected_hours: float
    risk_mass: float
    data_mode: str
    planner_version: str = "maintenance_plan_v2"


class PlanningDecisionRequest(BaseModel):
    decision: str = Field(
        pattern="^(approve|modify|reject)$"
    )
    actor: str = Field(default="planner", min_length=1, max_length=100)
    note: str = Field(default="", max_length=2000)


class PlanningDecisionResponse(BaseModel):
    decision_id: str
    task_id: str
    decision: str
    actor: str
    note: str
    human_approval_required: bool = True
    decision_mode: str = "decision_support"


class PlanningTaskResponse(BaseModel):
    task_id: str
    asset_id: str
    section_id: Any | None = None
    track_id: Any | None = None
    calibrated_risk: float
    condition_score: float
    degradation_rate: float
    task_type: str
    priority: str
    criticality: float
    estimated_duration_minutes: int
    planned_date: Any | None = None
    block_required: bool
    value: float
    selected: int
    explanation: dict[str, Any]
    data_mode: str


class AuditEventResponse(BaseModel):
    event_id: str
    event_type: str
    timestamp: str
    actor: str
    asset_id: str | None = None
    recommendation_id: str | None = None
    model_version: str | None = None
    payload: dict[str, Any]
