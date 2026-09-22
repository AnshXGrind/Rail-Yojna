
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
