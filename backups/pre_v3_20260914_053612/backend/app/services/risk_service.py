from pathlib import Path
from functools import lru_cache

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

RISK_PATH = ROOT / "ml/models/asset_risk_state_test.parquet"


@lru_cache(maxsize=1)
def load_risk_state() -> pd.DataFrame:
    if not RISK_PATH.exists():
        raise FileNotFoundError(
            f"Risk state not found: {RISK_PATH}"
        )

    df = pd.read_parquet(RISK_PATH)

    required = {
        "asset_id",
        "calibrated_risk",
        "condition_score",
        "degradation_rate",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Risk state missing columns: {sorted(missing)}"
        )

    return df


def get_asset_risk(asset_id: str) -> dict:
    df = load_risk_state()

    rows = df[df["asset_id"] == asset_id]

    if rows.empty:
        raise KeyError(
            f"Asset not found in risk state: {asset_id}"
        )

    row = rows.iloc[0]

    return {
        "asset_id": str(row["asset_id"]),
        "risk": float(row["calibrated_risk"]),
        "condition_score": float(row["condition_score"]),
        "degradation_rate": float(row["degradation_rate"]),
        "risk_horizon_days": 30,
        "prediction_timestamp": (
            str(row["prediction_timestamp"])
            if "prediction_timestamp" in row.index
            else None
        ),
        "data_mode": "synthetic",
    }


def get_top_risk_assets(limit: int = 20) -> list[dict]:
    df = load_risk_state()

    limit = max(1, min(limit, 100))

    result = (
        df.sort_values(
            "calibrated_risk",
            ascending=False,
        )
        .head(limit)
    )

    return result[
        [
            "asset_id",
            "calibrated_risk",
            "condition_score",
            "degradation_rate",
        ]
    ].rename(
        columns={
            "calibrated_risk": "risk",
        }
    ).to_dict(orient="records")
