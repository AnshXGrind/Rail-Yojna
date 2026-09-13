from pathlib import Path

import pandas as pd
from ortools.linear_solver import pywraplp


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = ROOT / "optimization/results/maintenance_plan_v1.parquet"

BASE_CAPACITY = 10_000

SCENARIOS = {
    "50%": 0.50,
    "75%": 0.75,
    "100%": 1.00,
    "125%": 1.25,
}


def greedy_select(
    df: pd.DataFrame,
    sort_columns: list[str],
    ascending: list[bool],
    daily_capacity: int,
) -> pd.DataFrame:

    selected = []
    used_by_day = {}

    ordered = df.sort_values(
        sort_columns,
        ascending=ascending,
    )

    for row in ordered.itertuples():
        day = row.planned_date.normalize()
        duration = int(row.estimated_duration_minutes)

        used = used_by_day.get(day, 0)

        if used + duration <= daily_capacity:
            selected.append(row.task_id)
            used_by_day[day] = used + duration

    return df[df["task_id"].isin(selected)].copy()


def solve_rail_yojna(
    df: pd.DataFrame,
    daily_capacity: int,
) -> pd.DataFrame:

    solver = pywraplp.Solver.CreateSolver("SCIP")

    if solver is None:
        raise RuntimeError("SCIP solver is unavailable.")

    variables = {
        row.task_id: solver.BoolVar(f"x_{row.task_id}")
        for row in df.itertuples()
    }

    for day, group in df.groupby(
        df["planned_date"].dt.normalize()
    ):
        solver.Add(
            solver.Sum(
                variables[row.task_id]
                * int(row.estimated_duration_minutes)
                for row in group.itertuples()
            )
            <= daily_capacity
        )

    objective = solver.Objective()

    for row in df.itertuples():
        objective.SetCoefficient(
            variables[row.task_id],
            float(row.value),
        )

    objective.SetMaximization()

    status = solver.Solve()

    if status not in (
        pywraplp.Solver.OPTIMAL,
        pywraplp.Solver.FEASIBLE,
    ):
        raise RuntimeError(
            f"Rail-Yojna optimization failed: {status}"
        )

    selected_ids = {
        task_id
        for task_id, variable in variables.items()
        if variable.solution_value() > 0.5
    }

    return df[
        df["task_id"].isin(selected_ids)
    ].copy()


def metrics(frame: pd.DataFrame) -> dict:

    if frame.empty:
        return {
            "tasks": 0,
            "minutes": 0,
            "risk_mass": 0.0,
            "mean_risk": 0.0,
            "p1_tasks": 0,
            "high_risk_tasks": 0,
        }

    return {
        "tasks": len(frame),
        "minutes": int(
            frame["estimated_duration_minutes"].sum()
        ),
        "risk_mass": float(
            frame["calibrated_risk"].sum()
        ),
        "mean_risk": float(
            frame["calibrated_risk"].mean()
        ),
        "p1_tasks": int(
            (frame["priority"] == "P1").sum()
        ),
        "high_risk_tasks": int(
            (frame["calibrated_risk"] >= 0.20).sum()
        ),
    }


def main():

    df = pd.read_parquet(PLAN_PATH)

    results = []

    for scenario, multiplier in SCENARIOS.items():

        capacity = int(
            BASE_CAPACITY * multiplier
        )

        chronological = greedy_select(
            df,
            ["planned_date", "task_id"],
            [True, True],
            capacity,
        )

        risk_only = greedy_select(
            df,
            ["calibrated_risk", "task_id"],
            [False, True],
            capacity,
        )

        rail_yojna = solve_rail_yojna(
            df,
            capacity,
        )

        for policy, selected in [
            ("chronological", chronological),
            ("risk_only", risk_only),
            ("rail_yojna_v1", rail_yojna),
        ]:

            row = {
                "scenario": scenario,
                "daily_capacity_minutes": capacity,
                "policy": policy,
            }

            row.update(metrics(selected))

            results.append(row)

    results = pd.DataFrame(results)

    print("=" * 80)
    print("RAIL-YOJNA V1 — CAPACITY SENSITIVITY")
    print("=" * 80)

    print(
        results.to_string(index=False)
    )

    print("\nRisk mass by scenario:")

    print(
        results
        .pivot(
            index="scenario",
            columns="policy",
            values="risk_mass",
        )
        .to_string()
    )

    print("\nMean risk by scenario:")

    print(
        results
        .pivot(
            index="scenario",
            columns="policy",
            values="mean_risk",
        )
        .to_string()
    )

    print("\nP1 tasks by scenario:")

    print(
        results
        .pivot(
            index="scenario",
            columns="policy",
            values="p1_tasks",
        )
        .to_string()
    )

    print("\nHigh-risk tasks by scenario:")

    print(
        results
        .pivot(
            index="scenario",
            columns="policy",
            values="high_risk_tasks",
        )
        .to_string()
    )

    output = (
        ROOT /
        "optimization/results/capacity_sensitivity.csv"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    results.to_csv(
        output,
        index=False,
    )

    print("\nSaved:")
    print(output)


if __name__ == "__main__":
    main()
