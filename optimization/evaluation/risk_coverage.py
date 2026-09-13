from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = (
    ROOT /
    "optimization/results/maintenance_plan_v1.parquet"
)

CAPACITY = {
    "50%": 5000,
    "75%": 7500,
    "100%": 10000,
    "125%": 12500,
}

POLICIES = [
    "chronological",
    "risk_only",
    "rail_yojna_v1",
]

TOP_FRACTIONS = [0.01, 0.05, 0.10, 0.20]


def greedy_select(df, sort_columns, ascending, capacity):
    selected = []
    used_by_day = {}

    for row in df.sort_values(
        sort_columns,
        ascending=ascending,
    ).itertuples():

        day = row.planned_date.normalize()
        duration = int(row.estimated_duration_minutes)

        used = used_by_day.get(day, 0)

        if used + duration <= capacity:
            selected.append(row.task_id)
            used_by_day[day] = used + duration

    return set(selected)


def rail_yojna_select(df, capacity):
    # Re-solve indirectly using the objective already stored in V1.
    from ortools.linear_solver import pywraplp

    solver = pywraplp.Solver.CreateSolver("SCIP")

    variables = {
        row.task_id: solver.BoolVar(f"x_{row.task_id}")
        for row in df.itertuples()
    }

    for _, group in df.groupby(
        df["planned_date"].dt.normalize()
    ):
        solver.Add(
            solver.Sum(
                variables[row.task_id]
                * int(row.estimated_duration_minutes)
                for row in group.itertuples()
            )
            <= capacity
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
        raise RuntimeError("Optimization failed.")

    return {
        task_id
        for task_id, var in variables.items()
        if var.solution_value() > 0.5
    }


def main():
    df = pd.read_parquet(PLAN_PATH)

    results = []

    # Global risk ranking of all candidate tasks.
    ranked = df.sort_values(
        "calibrated_risk",
        ascending=False,
    ).reset_index(drop=True)

    total_tasks = len(ranked)

    top_sets = {}

    for fraction in TOP_FRACTIONS:
        n = max(1, int(total_tasks * fraction))
        top_sets[fraction] = set(
            ranked.head(n)["task_id"]
        )

    for scenario, capacity in CAPACITY.items():

        policy_selections = {
            "chronological": greedy_select(
                df,
                ["planned_date", "task_id"],
                [True, True],
                capacity,
            ),
            "risk_only": greedy_select(
                df,
                ["calibrated_risk", "task_id"],
                [False, True],
                capacity,
            ),
            "rail_yojna_v1": rail_yojna_select(
                df,
                capacity,
            ),
        }

        for policy, selected_ids in policy_selections.items():

            for fraction, top_ids in top_sets.items():

                covered = len(
                    selected_ids & top_ids
                )

                results.append(
                    {
                        "scenario": scenario,
                        "capacity_minutes": capacity,
                        "policy": policy,
                        "top_fraction": fraction,
                        "top_tasks": len(top_ids),
                        "covered": covered,
                        "coverage_percent": (
                            100 * covered / len(top_ids)
                        ),
                    }
                )

    results = pd.DataFrame(results)

    print("=" * 80)
    print("RAIL-YOJNA — TOP-RISK COVERAGE")
    print("=" * 80)

    print(
        results.to_string(index=False)
    )

    print("\nCoverage pivot:")

    pivot = results.pivot_table(
        index=[
            "scenario",
            "top_fraction",
        ],
        columns="policy",
        values="coverage_percent",
    )

    print(pivot.to_string())

    output = (
        ROOT /
        "optimization/results/risk_coverage.csv"
    )

    results.to_csv(
        output,
        index=False,
    )

    print("\nSaved:")
    print(output)


if __name__ == "__main__":
    main()
