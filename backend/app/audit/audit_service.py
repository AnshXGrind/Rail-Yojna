from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
AUDIT_DIR = ROOT / "data" / "audit"
AUDIT_FILE = AUDIT_DIR / "decision_events.jsonl"


def record_event(
    event_type: str,
    *,
    actor: str = "system",
    asset_id: str | None = None,
    recommendation_id: str | None = None,
    model_version: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "asset_id": asset_id,
        "recommendation_id": recommendation_id,
        "model_version": model_version,
        "payload": payload or {},
    }

    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")

    return event


def list_events(
    *,
    limit: int = 100,
    event_type: str | None = None,
    asset_id: str | None = None,
) -> list[dict[str, Any]]:

    if not AUDIT_FILE.exists():
        return []

    limit = max(1, min(int(limit), 500))
    events: list[dict[str, Any]] = []

    with AUDIT_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event_type and event.get("event_type") != event_type:
                continue

            if asset_id and event.get("asset_id") != asset_id:
                continue

            events.append(event)

    events.sort(
        key=lambda x: x.get("timestamp", ""),
        reverse=True,
    )

    return events[:limit]
