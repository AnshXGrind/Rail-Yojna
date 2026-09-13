from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = ROOT / "optimization/results/maintenance_plan_v1.parquet"

CAPACITY_PER_DAY = 10_000


def select_greedy(df, sort_columns, ascending):
    selected = []

    ordered = df.sort_values(
        sort_columns,
        ascending=ascending,
    )

    used_by_day = {}

    for row in ordered.itertuples():
        day = row.planned_date.normalize()
        used = used_by_day.get(day, 0)
        duration = int(row.estimated_duration_minutes)

        if used + duration <= CAPACITY_PER_DAY:
            selected.append(row.task_id)
            used_by_day[day] = used + duration

    return df[df["task_id"].isin(selected)].copy()


def metrics(frame):
    return {
        "tasks": len(frame),
        "minutes": int(frame["estimated_duration_minutes"].sum()),
        "risk_mass": float(frame["calibrated_risk"].sum()),
        "mean_risk": float(frame["calibrated_risk"].mean()),
        "p1_tasks": int((frame["priority"] == "P1").sum()),
        "high_risk_tasks": int(
            (frame["calibrated_risk"] >= 0.20).sum()
        ),
    }


def main():
    df = pd.read_parquet(PLAN_PATH)

    # Chronological baseline.
    chronological = select_greedy(
        df,
        ["planned_date", "task_id"],
        [True, True],
    )

    # Stronger ML-only baseline.
    risk_only = select_greedy(
        df,
        ["calibrated_risk", "task_id"],
        [False, True],
    )

    # Rail-Yojna V1.
    rail_yojna = df[df["selected"] == 1].copy()

    comparison = pd.DataFrame(
        {
            "chronological": metrics(chronological),
            "risk_only": metrics(risk_only),
            "rail_yojna_v1": metrics(rail_yojna),
        }
    )

    print("=" * 80)
    print("RAIL-YOJNA V1 — THREE-WAY BASELINE COMPARISON")
    print("=" * 80)

    print("\nComparison:")
    print(comparison.to_string())

    print("\nRisk-mass improvement over risk-only:")
    print(
        rail_yojna["calibrated_risk"].sum()
        - risk_only["calibrated_risk"].sum()
    )

    print("\nMean-risk improvement over risk-only:")
    print(
        rail_yojna["calibrated_risk"].mean()
        - risk_only["calibrated_risk"].mean()
    )

    print("\nHigh-risk task difference vs risk-only:")
    print(
        int(
            (rail_yojna["calibrated_risk"] >= 0.20).sum()
        )
        -
        int(
            (risk_only["calibrated_risk"] >= 0.20).sum()
        )
    )


if __name__ == "__main__":
    main()
