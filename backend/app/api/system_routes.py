from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter


ROOT = Path(__file__).resolve().parents[3]

MODEL_PATH = ROOT / "ml/models/failure_30d_v3_logistic.joblib"
CALIBRATOR_PATH = (
    ROOT / "ml/models/failure_30d_v3_probability_calibrator.joblib"
)
METADATA_PATH = ROOT / "ml/models/failure_30d_v3_metadata.json"
RULES_PATH = ROOT / "railway/india/rules/risk_rules.yaml"

router = APIRouter(
    prefix="/api/v1/system",
    tags=["system"],
)


def _artifact_status(path: Path) -> dict:
    return {
        "path": str(path.relative_to(ROOT)),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def _load_metadata() -> dict:
    if not METADATA_PATH.exists():
        return {}

    with METADATA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/status")
def system_status():
    metadata = _load_metadata()

    return {
        "project": "Rail-Yojna",
        "version": "3.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": "synthetic",
        "mode": "decision_support",

        "model": {
            "name": metadata.get(
                "model_name",
                "failure_30d_v3_logistic",
            ),
            "version": "failure_30d_v3_logistic",
            "target": metadata.get(
                "target",
                "failure_within_30_days",
            ),
            "horizon_days": metadata.get(
                "horizon_days",
                30,
            ),
            "feature_count": metadata.get(
                "feature_count",
                23,
            ),
            "calibration": "platt_sigmoid",
        },

        "artifacts": {
            "model": _artifact_status(MODEL_PATH),
            "calibrator": _artifact_status(CALIBRATOR_PATH),
            "metadata": _artifact_status(METADATA_PATH),
            "rules": _artifact_status(RULES_PATH),
        },

        "safety_policy": {
            "human_approval_required": True,
            "autonomous_signalling": False,
            "autonomous_train_control": False,
            "autonomous_block_authority": False,
        },
    }
