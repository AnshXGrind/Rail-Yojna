from pathlib import Path

import pandas as pd
import yaml
from ortools.linear_solver import pywraplp


ROOT = Path(__file__).resolve().parents[2]

TASK_PATH = ROOT / "data/raw/rail_yojna_data/maintenance_tasks.parquet"
RISK_PATH = ROOT / "ml/models/asset_risk_state_test.parquet"
CONFIG_PATH = ROOT / "optimization/config/maintenance_v1.yaml"


def load_config():
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def load_candidates(risk_timestamp: pd.Timestamp) -> pd.DataFrame:
    tasks = pd.read_parquet(
        TASK_PATH,
        columns=[
            "task_id",
            "asset_id",
            "section_id",
            "track_id",
            "task_type",
            "priority",
            "criticality",
            "planned_date",
            "earliest_start",
            "latest_finish",
            "estimated_duration_minutes",
            "block_required",
            "task_status",
        ],
    )

    risk = pd.read_parquet(
        RISK_PATH,
        columns=[
            "asset_id",
            "calibrated_risk",
            "condition_score",
            "degradation_rate",
        ],
    )

    for col in [
        "planned_date",
        "earliest_start",
        "latest_finish",
    ]:
        tasks[col] = pd.to_datetime(
            tasks[col],
            format="mixed",
            errors="coerce",
            utc=True,
        )

    candidates = tasks[
        tasks["task_status"].isin(["planned", "approved"])
        & (tasks["earliest_start"] > risk_timestamp)
    ].copy()

    candidates = candidates.merge(
        risk,
        on="asset_id",
        how="inner",
        validate="many_to_one",
    )

    return candidates


def normalize(series: pd.Series) -> pd.Series:
    minimum = series.min()
    maximum = series.max()

    if maximum == minimum:
        return pd.Series(1.0, index=series.index)

    return (series - minimum) / (maximum - minimum)


def build_scores(
    candidates: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    priority_scores = config["priority_scores"]

    candidates["risk_score"] = candidates["calibrated_risk"]
    candidates["criticality_score"] = candidates["criticality"]
    candidates["priority_score"] = candidates["priority"].map(
        priority_scores
    )

    candidates["value"] = (
        config["objective"]["risk_weight"]
        * candidates["risk_score"]
        + config["objective"]["criticality_weight"]
        * candidates["criticality_score"]
        + config["objective"]["priority_weight"]
        * candidates["priority_score"]
    )

    return candidates


def solve(candidates: pd.DataFrame, daily_capacity: int):
    solver = pywraplp.Solver.CreateSolver("SCIP")

    if solver is None:
        raise RuntimeError("SCIP solver is unavailable in OR-Tools.")

    x = {
        row.task_id: solver.BoolVar(f"select_{row.task_id}")
        for row in candidates.itertuples()
    }

    # Capacity is applied to each planned date.
    for planned_date, group in candidates.groupby(
        candidates["planned_date"].dt.date
    ):
        solver.Add(
            solver.Sum(
                x[row.task_id] * float(row.estimated_duration_minutes)
                for row in group.itertuples()
            )
            <= daily_capacity
        )

    objective = solver.Objective()

    for row in candidates.itertuples():
        objective.SetCoefficient(
            x[row.task_id],
            float(row.value),
        )

    objective.SetMaximization()

    status = solver.Solve()

    if status not in (
        pywraplp.Solver.OPTIMAL,
        pywraplp.Solver.FEASIBLE,
    ):
        raise RuntimeError(
            f"Optimization failed with status {status}"
        )

    result = candidates.copy()

    result["selected"] = [
        int(x[task_id].solution_value() > 0.5)
        for task_id in result["task_id"]
    ]

    result["objective_contribution"] = (
        result["value"] * result["selected"]
    )

    return result


def main():
    config = load_config()

    risk_timestamp = pd.Timestamp(
        config["planning"]["risk_timestamp"]
    )

    candidates = load_candidates(risk_timestamp)

    if candidates.empty:
        raise RuntimeError("No planning candidates found.")

    candidates = build_scores(candidates, config)

    # Ensure priority mapping succeeded.
    if candidates["priority_score"].isna().any():
        bad = candidates.loc[
            candidates["priority_score"].isna(),
            "priority",
        ].unique()

        raise ValueError(
            f"Unknown priority values: {bad}"
        )

    daily_capacity = int(config["capacity"]["daily_minutes"])

    result = solve(
        candidates,
        daily_capacity,
    )

    output_path = ROOT / config["output"]["path"]
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_parquet(
        output_path,
        index=False,
    )

    selected = result[result["selected"] == 1]

    print("=" * 80)
    print("RAIL-YOJNA MAINTENANCE V1")
    print("=" * 80)

    print(f"Candidates: {len(result):,}")
    print(f"Selected:   {len(selected):,}")
    print(
        f"Selection rate: "
        f"{100 * len(selected) / len(result):.2f}%"
    )

    print(
        "\nSelected maintenance time:",
        f"{selected['estimated_duration_minutes'].sum():,.0f}",
        "minutes",
    )

    print(
        "Selected predicted-risk mass:",
        f"{selected['calibrated_risk'].sum():.4f}",
    )

    print(
        "Selected tasks by priority:"
    )
    print(
        selected["priority"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print("\nTop selected tasks:")

    print(
        selected.sort_values(
            "value",
            ascending=False,
        )[
            [
                "task_id",
                "asset_id",
                "calibrated_risk",
                "criticality",
                "priority",
                "estimated_duration_minutes",
                "value",
                "planned_date",
            ]
        ]
        .head(20)
        .to_string(index=False)
    )

    print("\nSaved:")
    print(output_path)


if __name__ == "__main__":
    main()
