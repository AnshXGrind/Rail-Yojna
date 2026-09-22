
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
