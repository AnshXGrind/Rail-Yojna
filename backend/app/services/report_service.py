
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
