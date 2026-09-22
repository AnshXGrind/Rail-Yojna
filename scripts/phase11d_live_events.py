from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "backend/app/services/event_stream.py"
ROUTES = ROOT / "backend/app/api/event_routes.py"
MAIN = ROOT / "backend/app/main.py"
APP = ROOT / "frontend/src/App.jsx"
CSS = ROOT / "frontend/src/App.css"

SERVICE.parent.mkdir(parents=True, exist_ok=True)
ROUTES.parent.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------
# Backend event stream
# ------------------------------------------------------------------

SERVICE.write_text(
r'''
from __future__ import annotations

import asyncio
import json
from typing import Any

_subscribers: set[asyncio.Queue] = set()


def publish(event_type: str, payload: dict[str, Any]) -> None:
    event = {
        "type": event_type,
        "payload": payload,
    }

    for queue in list(_subscribers):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass


async def subscribe():
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.add(queue)

    try:
        while True:
            yield await queue.get()
    finally:
        _subscribers.discard(queue)


async def heartbeat():
    while True:
        await asyncio.sleep(15)
        yield {
            "type": "heartbeat",
            "payload": {},
        }
''',
encoding="utf-8",
)

# ------------------------------------------------------------------
# SSE route
# ------------------------------------------------------------------

ROUTES.write_text(
r'''
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.app.services.event_stream import subscribe


router = APIRouter(
    prefix="/api/v1/events",
    tags=["events"],
)


@router.get("/stream")
async def event_stream():
    async def generator():
        async for event in subscribe():
            yield (
                "event: rail_yojna\n"
                f"data: {json.dumps(event)}\n\n"
            )

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
''',
encoding="utf-8",
)

# ------------------------------------------------------------------
# Register router
# ------------------------------------------------------------------

main = MAIN.read_text(encoding="utf-8")

if "event_routes" not in main:
    import_line = (
        "from backend.app.api.event_routes import router as event_router"
    )

    main = import_line + "\n" + main

if "app.include_router(event_router)" not in main:
    main += "\napp.include_router(event_router)\n"

MAIN.write_text(main, encoding="utf-8")

# ------------------------------------------------------------------
# Publish report events
# ------------------------------------------------------------------

report_service = ROOT / "backend/app/services/report_service.py"
report_routes = ROOT / "backend/app/api/report_routes.py"

for path in (report_service, report_routes):
    if not path.exists():
        raise SystemExit(f"Missing expected file: {path}")

routes = report_routes.read_text(encoding="utf-8")

if "from backend.app.services.event_stream import publish" not in routes:
    routes = routes.replace(
        "from backend.app.services.report_service import (",
        "from backend.app.services.event_stream import publish\n"
        "from backend.app.services.report_service import (",
        1,
    )

needle = '''    record_event(
        "REPORT_CREATED",
        actor=payload.reporter,
        asset_id=payload.asset_id,
        payload=report.model_dump(mode="json"),
    )

    return report
'''

replacement = '''    record_event(
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
'''

if needle in routes:
    routes = routes.replace(needle, replacement, 1)

needle = '''    record_event(
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

replacement = '''    record_event(
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
'''

if needle in routes:
    routes = routes.replace(needle, replacement, 1)

report_routes.write_text(routes, encoding="utf-8")

# ------------------------------------------------------------------
# Frontend: switch Live Reports to SSE
# ------------------------------------------------------------------

app = APP.read_text(encoding="utf-8")

old = '''  useEffect(() => {
    loadLiveReports(setLiveReports);

    const interval = window.setInterval(() => {
      loadLiveReports(setLiveReports);
    }, 5000);

    return () => window.clearInterval(interval);
  }, []);
'''

new = '''  useEffect(() => {
    loadLiveReports(setLiveReports);

    const source = new EventSource(
      `${API}/events/stream`,
    );

    source.addEventListener("rail_yojna", (event) => {
      try {
        const message = JSON.parse(event.data);

        if (
          message.type === "REPORT_CREATED" ||
          message.type === "REPORT_STATUS_CHANGED"
        ) {
          loadLiveReports(setLiveReports);
        }
      } catch {
        // Keep the dashboard alive if an event is malformed.
      }
    });

    return () => {
      source.close();
    };
  }, []);
'''

if old in app:
    app = app.replace(old, new, 1)
else:
    print("Polling effect not found; frontend SSE patch skipped.")

APP.write_text(app, encoding="utf-8")

# ------------------------------------------------------------------
# CSS connection indicator
# ------------------------------------------------------------------

css = CSS.read_text(encoding="utf-8")

css += r'''

/* Phase 11D — true live event state */

.live-reports-button.has-new {
  animation: reportPulse 1.6s ease-in-out infinite;
}

@keyframes reportPulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(232, 146, 47, 0);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(232, 146, 47, 0.10);
  }
}
'''

CSS.write_text(css, encoding="utf-8")

print("Phase 11D SSE live-event infrastructure installed.")
