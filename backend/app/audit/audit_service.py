from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUDIT_DIR = Path("data/audit")
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
