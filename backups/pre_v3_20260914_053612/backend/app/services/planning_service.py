from pathlib import Path
from functools import lru_cache

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

PLAN_PATH = (
    ROOT /
    "optimization/results/maintenance_plan_v1.parquet"
)


@lru_cache(maxsize=1)
def load_plan() -> pd.DataFrame:
    if not PLAN_PATH.exists():
        raise FileNotFoundError(
            f"Maintenance plan not found: {PLAN_PATH}"
        )

    return pd.read_parquet(PLAN_PATH)


def get_plan(limit: int = 50) -> list[dict]:
    df = load_plan()

    limit = max(1, min(limit, 500))

    selected = (
        df[df["selected"] == 1]
        .sort_values(
            "value",
            ascending=False,
        )
        .head(limit)
    )

    return selected[
        [
            "task_id",
            "asset_id",
            "section_id",
            "track_id",
            "calibrated_risk",
            "condition_score",
            "degradation_rate",
            "task_type",
            "priority",
            "criticality",
            "estimated_duration_minutes",
            "planned_date",
            "block_required",
            "value",
        ]
    ].to_dict(orient="records")


def get_plan_summary() -> dict:
    df = load_plan()

    selected = df[df["selected"] == 1]

    return {
        "candidate_tasks": int(len(df)),
        "selected_tasks": int(len(selected)),
        "deferred_tasks": int(
            len(df) - len(selected)
        ),
        "selected_minutes": int(
            selected["estimated_duration_minutes"].sum()
        ),
        "selected_hours": float(
            selected["estimated_duration_minutes"].sum() / 60
        ),
        "risk_mass": float(
            selected["calibrated_risk"].sum()
        ),
        "data_mode": "synthetic",
    }
