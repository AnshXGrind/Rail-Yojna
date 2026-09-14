from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter


router = APIRouter(
    prefix="/api/v1/system",
    tags=["system"],
)


@router.get("/status")
def system_status():
    return {
        "project": "Rail-Yojna",
        "version": "3.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": "synthetic",
        "mode": "decision_support",
        "human_approval_required": True,
        "autonomous_signalling": False,
        "autonomous_train_control": False,
        "autonomous_block_authority": False,
    }
