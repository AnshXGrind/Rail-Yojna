from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

PLAN_PATH = ROOT / "optimization/results/maintenance_plan_v2.parquet"


def _read_plan() -> pd.DataFrame:
    parquet = PLAN_PATH

    if parquet.exists():
        return pd.read_parquet(parquet)

    csv_path = parquet.with_suffix(".csv")
    if csv_path.exists():
        return pd.read_csv(csv_path)

    raise FileNotFoundError(
        f"Maintenance plan not found: {parquet} or {csv_path}"
    )


@lru_cache(maxsize=1)
def load_plan() -> pd.DataFrame:
    df = _read_plan().copy()

    required = {
        "task_id",
        "asset_id",
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
        "selected",
    }

    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(
            f"Maintenance plan missing required columns: {missing}"
        )

    return df


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def explain_task(row: pd.Series) -> dict[str, Any]:
    risk = float(row["calibrated_risk"])
    condition = float(row["condition_score"])
    degradation = float(row["degradation_rate"])
    criticality = float(row["criticality"])
    priority = str(row["priority"])
    block_required = bool(row["block_required"])

    reasons: list[str] = []

    if risk >= 0.50:
        reasons.append("critical predicted failure risk")
    elif risk >= 0.20:
        reasons.append("high predicted failure risk")
    elif risk >= 0.05:
        reasons.append("moderate predicted failure risk")
    else:
        reasons.append("low predicted failure risk")

    if condition < 40:
        reasons.append("poor current condition")
    elif condition < 60:
        reasons.append("degraded current condition")

    if degradation > 0:
        reasons.append("positive degradation trend")

    if criticality >= 0.80:
        reasons.append("high asset criticality")

    if priority == "P1":
        reasons.append("highest maintenance priority")

    if block_required:
        reasons.append("requires a planned block")

    return {
        "primary_reason": reasons[0],
        "reasons": reasons,
        "risk_probability": risk,
        "condition_score": condition,
        "degradation_rate": degradation,
        "criticality": criticality,
        "priority": priority,
        "block_required": block_required,
        "explanation_mode": "deterministic_rule_summary",
    }


def _row_to_dict(row: pd.Series) -> dict[str, Any]:
    item = {
        "task_id": row["task_id"],
        "asset_id": row["asset_id"],
        "section_id": row.get("section_id"),
        "track_id": row.get("track_id"),
        "calibrated_risk": row["calibrated_risk"],
        "condition_score": row["condition_score"],
        "degradation_rate": row["degradation_rate"],
        "task_type": row["task_type"],
        "priority": row["priority"],
        "criticality": row["criticality"],
        "estimated_duration_minutes": row["estimated_duration_minutes"],
        "planned_date": row["planned_date"],
        "block_required": row["block_required"],
        "value": row["value"],
        "selected": row["selected"],
        "explanation": explain_task(row),
        "data_mode": "synthetic",
    }

    return {k: _clean_value(v) for k, v in item.items()}


def get_plan(limit: int = 50) -> list[dict]:
    df = load_plan()
    limit = max(1, min(int(limit), 500))

    selected = (
        df[df["selected"] == 1]
        .sort_values("value", ascending=False)
        .head(limit)
    )

    return [_row_to_dict(row) for _, row in selected.iterrows()]


def get_plan_task(task_id: str) -> dict:
    df = load_plan()

    matches = df[df["task_id"].astype(str) == str(task_id)]
    if matches.empty:
        raise KeyError(task_id)

    return _row_to_dict(matches.iloc[0])


def get_plan_summary() -> dict:
    df = load_plan()

    selected = df[df["selected"] == 1]

    minutes = int(selected["estimated_duration_minutes"].sum())

    return {
        "candidate_tasks": int(len(df)),
        "selected_tasks": int(len(selected)),
        "deferred_tasks": int(len(df) - len(selected)),
        "selected_minutes": minutes,
        "selected_hours": float(minutes / 60),
        "risk_mass": float(selected["calibrated_risk"].sum()),
        "data_mode": "synthetic",
        "planner_version": "maintenance_plan_v2",
    }


def get_plan_metrics() -> dict:
    df = load_plan()

    selected = df[df["selected"] == 1]

    risk = selected["calibrated_risk"].astype(float)

    return {
        "selected_tasks": int(len(selected)),
        "selected_hours": float(
            selected["estimated_duration_minutes"].sum() / 60
        ),
        "risk_mass": float(risk.sum()),
        "mean_selected_risk": float(risk.mean()) if len(risk) else 0.0,
        "high_risk_tasks": int((risk >= 0.20).sum()),
        "critical_risk_tasks": int((risk >= 0.50).sum()),
        "block_required_tasks": int(selected["block_required"].astype(bool).sum()),
        "p1_tasks": int((selected["priority"].astype(str) == "P1").sum()),
        "planner_version": "maintenance_plan_v2",
    }


def clear_plan_cache() -> None:
    load_plan.cache_clear()
