
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


ReportStatus = Literal[
    "NEW",
    "TRIAGED",
    "VERIFIED",
    "ASSIGNED",
    "IN_PROGRESS",
    "RESOLVED",
    "CLOSED",
]

ReportSeverity = Literal[
    "Low",
    "Medium",
    "High",
    "Critical",
]


class ReportCreate(BaseModel):
    asset_id: str = Field(min_length=1, max_length=128)
    reporter: str = Field(min_length=1, max_length=128)
    problem_type: str = Field(min_length=1, max_length=128)
    severity: ReportSeverity = "Medium"
    description: str = Field(min_length=1, max_length=5000)


class ReportStatusUpdate(BaseModel):
    status: ReportStatus
    actor: str = Field(min_length=1, max_length=128)
    note: str = Field(default="", max_length=2000)


class Report(BaseModel):
    report_id: str
    asset_id: str
    reporter: str
    problem_type: str
    severity: ReportSeverity
    description: str
    status: ReportStatus
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    last_actor: str | None = None
    last_note: str | None = None
