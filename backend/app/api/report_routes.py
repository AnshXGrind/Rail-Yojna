
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.audit.audit_service import record_event
from backend.app.schemas.reports import (
    Report,
    ReportCreate,
    ReportStatusUpdate,
)
from backend.app.services.event_stream import publish
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

    publish(
        "REPORT_CREATED",
        report.model_dump(mode="json"),
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

    publish(
        "REPORT_STATUS_CHANGED",
        report.model_dump(mode="json"),
    )

    return report
