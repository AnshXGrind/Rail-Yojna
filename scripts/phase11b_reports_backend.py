from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]

API_DIR = ROOT / "backend/app/api"
SCHEMA_DIR = ROOT / "backend/app/schemas"
SERVICE_DIR = ROOT / "backend/app/services"
DATA_DIR = ROOT / "data/reports"

API_DIR.mkdir(parents=True, exist_ok=True)
SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
SERVICE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------

(SCHEMA_DIR / "reports.py").write_text(
r'''
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
'''
,
encoding="utf-8",
)

# ---------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------

(SERVICE_DIR / "report_service.py").write_text(
r'''
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from backend.app.schemas.reports import (
    Report,
    ReportCreate,
    ReportStatus,
    ReportStatusUpdate,
)

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "data" / "reports" / "reports.json"

_LOCK = Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load() -> list[dict]:
    if not REPORT_PATH.exists():
        return []

    try:
        return json.loads(REPORT_PATH.read_text())
    except Exception:
        return []


def _save(items: list[dict]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    temp_path = REPORT_PATH.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n"
    )
    temp_path.replace(REPORT_PATH)


def list_reports(
    *,
    asset_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[Report]:
    with _LOCK:
        items = _load()

    if asset_id:
        items = [
            item for item in items
            if item.get("asset_id") == asset_id
        ]

    if status:
        items = [
            item for item in items
            if item.get("status") == status
        ]

    items = sorted(
        items,
        key=lambda item: item.get("created_at", ""),
        reverse=True,
    )

    return [Report(**item) for item in items[:limit]]


def get_report(report_id: str) -> Report | None:
    with _LOCK:
        items = _load()

    for item in items:
        if item.get("report_id") == report_id:
            return Report(**item)

    return None


def create_report(payload: ReportCreate) -> Report:
    now = _now()

    report = Report(
        report_id=f"REP-{uuid4().hex[:10].upper()}",
        asset_id=payload.asset_id,
        reporter=payload.reporter,
        problem_type=payload.problem_type,
        severity=payload.severity,
        description=payload.description,
        status="NEW",
        created_at=now,
        updated_at=now,
        last_actor=payload.reporter,
    )

    with _LOCK:
        items = _load()
        items.append(report.model_dump(mode="json"))
        _save(items)

    return report


def update_report_status(
    report_id: str,
    payload: ReportStatusUpdate,
) -> Report | None:
    now = _now()

    with _LOCK:
        items = _load()

        target = next(
            (
                item
                for item in items
                if item.get("report_id") == report_id
            ),
            None,
        )

        if target is None:
            return None

        target["status"] = payload.status
        target["updated_at"] = now.isoformat()
        target["last_actor"] = payload.actor
        target["last_note"] = payload.note

        if payload.status == "CLOSED":
            target["closed_at"] = now.isoformat()

        _save(items)

        return Report(**target)
'''
,
encoding="utf-8",
)

# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------

(API_DIR / "report_routes.py").write_text(
r'''
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.audit.audit_service import record_event
from backend.app.schemas.reports import (
    Report,
    ReportCreate,
    ReportStatusUpdate,
)
from backend.app.services.report_service import (
    create_report,
    get_report,
    list_reports,
    update_report_status,
)

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["reports"],
)


@router.post("", response_model=Report, status_code=201)
def create(payload: ReportCreate):
    report = create_report(payload)

    record_event(
        "REPORT_CREATED",
        actor=payload.reporter,
        asset_id=payload.asset_id,
        payload=report.model_dump(mode="json"),
    )

    return report


@router.get("", response_model=list[Report])
def list_all(
    asset_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return list_reports(
        asset_id=asset_id,
        status=status,
        limit=limit,
    )


@router.get("/{report_id}", response_model=Report)
def get_one(report_id: str):
    report = get_report(report_id)

    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Report {report_id} not found.",
        )

    return report


@router.get("/asset/{asset_id}", response_model=list[Report])
def list_for_asset(
    asset_id: str,
    limit: int = Query(default=100, ge=1, le=500),
):
    return list_reports(
        asset_id=asset_id,
        limit=limit,
    )


@router.patch(
    "/{report_id}/status",
    response_model=Report,
)
def update_status(
    report_id: str,
    payload: ReportStatusUpdate,
):
    report = update_report_status(
        report_id,
        payload,
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Report {report_id} not found.",
        )

    record_event(
        "REPORT_STATUS_CHANGED",
        actor=payload.actor,
        asset_id=report.asset_id,
        payload={
            "report_id": report.report_id,
            "status": report.status,
            "note": payload.note,
        },
    )

    return report
'''
,
encoding="utf-8",
)

# ---------------------------------------------------------------------
# Register router
# ---------------------------------------------------------------------

main_path = ROOT / "backend/app/main.py"
main = main_path.read_text(encoding="utf-8")

if "report_routes" not in main:
    if "from backend.app.api import" in main:
        main = main.replace(
            "from backend.app.api import",
            "from backend.app.api import",
            1,
        )

    import_anchor = (
        "from backend.app.api.inference_routes import router as inference_router"
    )

    if import_anchor in main:
        main = main.replace(
            import_anchor,
            import_anchor
            + "\nfrom backend.app.api.report_routes import router as report_router",
            1,
        )
    else:
        main = (
            "from backend.app.api.report_routes import router as report_router\n"
            + main
        )

    if "app.include_router(report_router)" not in main:
        main += "\n\napp.include_router(report_router)\n"

    main_path.write_text(main, encoding="utf-8")

# ---------------------------------------------------------------------
# Create empty report store
# ---------------------------------------------------------------------

report_store = DATA_DIR / "reports.json"

if not report_store.exists():
    report_store.write_text("[]\n", encoding="utf-8")

print("Phase 11B Reports backend created.")
print()
print("Created:")
print("  backend/app/schemas/reports.py")
print("  backend/app/services/report_service.py")
print("  backend/app/api/report_routes.py")
print("  data/reports/reports.json")
print()
print("Updated:")
print("  backend/app/main.py")
