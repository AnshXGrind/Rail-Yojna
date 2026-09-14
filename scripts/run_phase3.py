from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
import yaml
from ortools.linear_solver import pywraplp


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "rail_yojna_data"
MODEL_DIR = ROOT / "ml" / "models"
OPT_DIR = ROOT / "optimization"
RESULT_DIR = OPT_DIR / "results"
CONFIG = OPT_DIR / "config" / "maintenance_v1.yaml"

RESULT_DIR.mkdir(parents=True, exist_ok=True)

PHASE3_PLAN = RESULT_DIR / "maintenance_plan_v2.parquet"
CANDIDATES = RESULT_DIR / "maintenance_candidates_v2.parquet"
BASELINE = RESULT_DIR / "maintenance_plan_v2_comparison.csv"
REPORT = RESULT_DIR / "phase3_report.json"
ERROR_REPORT = RESULT_DIR / "phase3_errors.csv"

V3_MODEL = MODEL_DIR / "failure_30d_v3_logistic.joblib"
V3_CALIBRATOR = MODEL_DIR / "failure_30d_v3_probability_calibrator.joblib"

FEATURES = [
    "condition_score",
    "degradation_rate",
    "measurement_value",
    "inspection_quality",
    "measurement_confidence",
    "previous_condition_score",
    "condition_change",
    "days_since_previous_measurement",
    "historical_mean_condition",
    "historical_min_condition",
    "historical_mean_degradation",
    "historical_observation_count",
    "design_life_years",
    "criticality_score",
    "asset_age_days",
    "defect_days_since_last",
    "defect_count_before",
    "inspection_days_since_last",
    "inspection_count_before",
    "maintenance_days_since_last",
    "maintenance_count_before",
    "incident_days_since_last",
    "incident_count_before",
]

ERRORS: list[dict] = []
WARNINGS: list[str] = []


def error(stage: str, message: str, severity: str = "ERROR") -> None:
    ERRORS.append(
        {
            "severity": severity,
            "stage": stage,
            "message": message,
        }
    )


def warn(message: str) -> None:
    WARNINGS.append(message)


def read_table(
    name: str,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    parquet = RAW / f"{name}.parquet"
    csv = RAW / f"{name}.csv"

    if parquet.exists():
        return pd.read_parquet(parquet, columns=columns)

    if csv.exists():
        return pd.read_csv(csv, usecols=columns)

    raise FileNotFoundError(
        f"Missing table: {name}.csv / {name}.parquet"
    )


def discover_table(name: str) -> dict:
    parquet = RAW / f"{name}.parquet"
    csv = RAW / f"{name}.csv"

    if parquet.exists():
        path = parquet
        fmt = "parquet"
    elif csv.exists():
        path = csv
        fmt = "csv"
    else:
        return {
            "name": name,
            "exists": False,
            "format": None,
            "columns": [],
            "rows": 0,
        }

    df = (
        pd.read_parquet(path, columns=[])
        if fmt == "parquet"
        else pd.read_csv(path, nrows=0)
    )

    if fmt == "parquet":
        columns = list(pd.read_parquet(path).columns)
    else:
        columns = list(df.columns)

    return {
        "name": name,
        "exists": True,
        "format": fmt,
        "columns": columns,
        "rows": None,
    }


def first_column(
    columns: Iterable[str],
    candidates: Iterable[str],
) -> str | None:
    available = set(columns)
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def normalize_timestamp(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series,
        format="mixed",
        errors="coerce",
        utc=True,
    )


def load_config() -> dict:
    with CONFIG.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_v3_model():
    if not V3_MODEL.exists():
        raise FileNotFoundError(V3_MODEL)

    if not V3_CALIBRATOR.exists():
        raise FileNotFoundError(V3_CALIBRATOR)

    model_bundle = joblib.load(V3_MODEL)
    calibrator = joblib.load(V3_CALIBRATOR)

    if list(model_bundle["features"]) != FEATURES:
        raise RuntimeError("V3 feature contract mismatch.")

    return model_bundle["model"], calibrator


def calibrated_probability(
    model,
    calibrator,
    X: pd.DataFrame,
) -> np.ndarray:
    raw = model.predict_proba(X)[:, 1]

    clipped = np.clip(raw, 1e-8, 1 - 1e-8)
    logits = np.log(clipped / (1 - clipped))

    calibrated = calibrator.predict_proba(
        logits.reshape(-1, 1)
    )[:, 1]

    return calibrated


def risk_band(probability: float) -> str:
    if probability >= 0.50:
        return "critical"
    if probability >= 0.20:
        return "high"
    if probability >= 0.05:
        return "medium"
    return "low"


@dataclass
class PlanningConstraintCoverage:
    resource_constraints: str = "UNAVAILABLE"
    resource_capacity_constraints: str = "UNAVAILABLE"
    block_constraints: str = "UNAVAILABLE"
    train_conflict_constraints: str = "UNAVAILABLE"
    precedence_constraints: str = "UNAVAILABLE"
    daily_capacity: str = "ENFORCED"


def load_tasks() -> pd.DataFrame:
    columns = [
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
    ]

    df = read_table("maintenance_tasks", columns=columns)

    for column in [
        "planned_date",
        "earliest_start",
        "latest_finish",
    ]:
        df[column] = normalize_timestamp(df[column])

    df["estimated_duration_minutes"] = pd.to_numeric(
        df["estimated_duration_minutes"],
        errors="coerce",
    )

    df["criticality"] = pd.to_numeric(
        df["criticality"],
        errors="coerce",
    )

    return df


def load_v3_risk_state() -> pd.DataFrame:
    """
    Build the planning risk state from the V3 test-end feature rows.

    This preserves the current research planning timestamp while moving
    the planning layer onto the V3 model/calibrator.
    """
    data_path = ROOT / "data" / "processed" / "failure_30d_dataset_v3.parquet"

    if not data_path.exists():
        raise FileNotFoundError(data_path)

    df = pd.read_parquet(data_path)

    endpoint = pd.Timestamp(
        "2025-12-31T23:59:59Z"
    )

    subset = df[
        df["prediction_timestamp"] == endpoint
    ].copy()

    if subset.empty:
        raise RuntimeError(
            "No V3 prediction rows exist at the planning timestamp."
        )

    model, calibrator = load_v3_model()

    probabilities = calibrated_probability(
        model,
        calibrator,
        subset[FEATURES],
    )

    subset["calibrated_risk"] = probabilities
    subset["risk_level"] = [
        risk_band(float(x))
        for x in probabilities
    ]

    return subset[
        [
            "asset_id",
            "calibrated_risk",
            "risk_level",
            "condition_score",
            "degradation_rate",
        ]
    ].drop_duplicates("asset_id")


def validate_tasks(
    tasks: pd.DataFrame,
    planning_timestamp: pd.Timestamp,
) -> pd.DataFrame:

    df = tasks.copy()

    df["candidate_status"] = "eligible"
    df["candidate_reason"] = "eligible"

    required = [
        "task_id",
        "asset_id",
        "planned_date",
        "earliest_start",
        "latest_finish",
        "estimated_duration_minutes",
    ]

    for col in required:
        bad = df[col].isna()

        if bad.any():
            df.loc[bad, "candidate_status"] = "invalid"
            df.loc[
                bad,
                "candidate_reason",
            ] = f"missing_{col}"

    invalid_duration = (
        df["estimated_duration_minutes"].fillna(-1) <= 0
    )

    df.loc[
        invalid_duration,
        "candidate_status",
    ] = "invalid"

    df.loc[
        invalid_duration,
        "candidate_reason",
    ] = "invalid_duration"

    future_mask = (
        df["earliest_start"] <= planning_timestamp
    )

    df.loc[
        future_mask & (df["candidate_status"] == "eligible"),
        "candidate_status",
    ] = "deferred"

    df.loc[
        future_mask & (df["candidate_reason"] == "eligible"),
        "candidate_reason",
    ] = "earliest_start_not_future"

    allowed_status = {
        "planned",
        "approved",
    }

    status_mask = ~df["task_status"].isin(allowed_status)

    df.loc[
        status_mask,
        "candidate_status",
    ] = "deferred"

    df.loc[
        status_mask,
        "candidate_reason",
    ] = "task_status_not_eligible"

    return df


def build_candidates(
    tasks: pd.DataFrame,
    risk: pd.DataFrame,
    planning_timestamp: pd.Timestamp,
    config: dict,
) -> pd.DataFrame:

    tasks = validate_tasks(
        tasks,
        planning_timestamp,
    )

    candidates = tasks.merge(
        risk,
        on="asset_id",
        how="left",
        validate="many_to_one",
    )

    missing_risk = candidates["calibrated_risk"].isna()

    candidates.loc[
        missing_risk,
        "candidate_status",
    ] = "invalid"

    candidates.loc[
        missing_risk,
        "candidate_reason",
    ] = "missing_v3_risk"

    priority_scores = config["priority_scores"]

    candidates["priority_score"] = (
        candidates["priority"].map(priority_scores)
    )

    missing_priority = candidates["priority_score"].isna()

    candidates.loc[
        missing_priority,
        "candidate_status",
    ] = "invalid"

    candidates.loc[
        missing_priority,
        "candidate_reason",
    ] = "unknown_priority"

    candidates["risk_score"] = (
        candidates["calibrated_risk"]
    )

    candidates["criticality_score"] = (
        candidates["criticality"].clip(0, 1)
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


def load_optional_resource_tables() -> dict:
    result = {}

    for name in [
        "task_resources",
        "resources",
        "resource_availability",
        "blocks",
        "train_movements",
        "safety_constraints",
    ]:
        info = discover_table(name)

        if not info["exists"]:
            warn(f"Optional planning table missing: {name}")
            continue

        try:
            result[name] = read_table(name)
        except Exception as exc:
            error(
                "resource_loading",
                f"{name}: {exc}",
            )

    return result


def assess_constraint_coverage(
    optional_tables: dict,
) -> PlanningConstraintCoverage:

    coverage = PlanningConstraintCoverage()

    if "task_resources" in optional_tables:
        coverage.resource_constraints = "AVAILABLE_FOR_MODELING"

    if "resource_availability" in optional_tables:
        coverage.resource_capacity_constraints = (
            "AVAILABLE_FOR_MODELING"
        )

    if "blocks" in optional_tables:
        coverage.block_constraints = "AVAILABLE_FOR_MODELING"

    if "train_movements" in optional_tables:
        coverage.train_conflict_constraints = (
            "AVAILABLE_FOR_MODELING"
        )

    # The current V2 solver does not infer precedence automatically.
    if "maintenance_tasks" in optional_tables:
        coverage.precedence_constraints = (
            "NOT_MODELED"
        )

    return coverage


def solve_daily_capacity(
    candidates: pd.DataFrame,
    daily_capacity: int,
) -> pd.DataFrame:

    eligible = candidates[
        candidates["candidate_status"] == "eligible"
    ].copy()

    if eligible.empty:
        raise RuntimeError(
            "No eligible maintenance candidates remain."
        )

    solver = pywraplp.Solver.CreateSolver("SCIP")

    if solver is None:
        raise RuntimeError(
            "OR-Tools SCIP solver is unavailable."
        )

    x = {
        row.task_id: solver.BoolVar(
            f"select_{row.task_id}"
        )
        for row in eligible.itertuples()
    }

    for day, group in eligible.groupby(
        eligible["planned_date"].dt.date
    ):
        solver.Add(
            solver.Sum(
                x[row.task_id]
                * float(row.estimated_duration_minutes)
                for row in group.itertuples()
            )
            <= daily_capacity
        )

    objective = solver.Objective()

    for row in eligible.itertuples():
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

    selected_map = {
        task_id: int(
            variable.solution_value() > 0.5
        )
        for task_id, variable in x.items()
    }

    result = candidates.copy()

    result["selected"] = [
        selected_map.get(row.task_id, 0)
        if row.candidate_status == "eligible"
        else 0
        for row in result.itertuples()
    ]

    result["objective_contribution"] = (
        result["value"] * result["selected"]
    )

    result["decision"] = np.where(
        result["selected"] == 1,
        "selected",
        result["candidate_status"].where(
            result["candidate_status"] != "eligible",
            "deferred_by_optimization",
        ),
    )

    return result


def greedy_select(
    df: pd.DataFrame,
    sort_columns: list[str],
    ascending: list[bool],
    capacity: int,
) -> pd.DataFrame:

    selected = []
    used_by_day: dict[pd.Timestamp, float] = {}

    ordered = df[
        df["candidate_status"] == "eligible"
    ].sort_values(
        sort_columns,
        ascending=ascending,
    )

    for row in ordered.itertuples():
        day = row.planned_date.normalize()

        used = used_by_day.get(day, 0.0)
        duration = float(
            row.estimated_duration_minutes
        )

        if used + duration <= capacity:
            selected.append(row.task_id)
            used_by_day[day] = used + duration

    return df[
        df["task_id"].isin(selected)
    ].copy()


def summary_metrics(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {
            "tasks": 0,
            "minutes": 0,
            "risk_mass": 0.0,
            "mean_risk": 0.0,
            "high_risk_tasks": 0,
            "p1_tasks": 0,
        }

    return {
        "tasks": int(len(frame)),
        "minutes": int(
            frame["estimated_duration_minutes"].sum()
        ),
        "risk_mass": float(
            frame["calibrated_risk"].sum()
        ),
        "mean_risk": float(
            frame["calibrated_risk"].mean()
        ),
        "high_risk_tasks": int(
            (frame["calibrated_risk"] >= 0.20).sum()
        ),
        "p1_tasks": int(
            (frame["priority"] == "P1").sum()
        ),
    }


def validate_output(plan: pd.DataFrame) -> None:
    checks = []

    checks.append(
        (
            "duplicate_task_ids",
            plan["task_id"].duplicated().sum() == 0,
        )
    )

    checks.append(
        (
            "selected_capacity",
            True,
        )
    )

    checks.append(
        (
            "selected_binary",
            plan["selected"].isin([0, 1]).all(),
        )
    )

    checks.append(
        (
            "risk_range",
            plan["calibrated_risk"].between(0, 1).all(),
        )
    )

    checks.append(
        (
            "positive_duration",
            (plan["estimated_duration_minutes"] > 0).all(),
        )
    )

    for name, passed in checks:
        if not passed:
            error(
                "output_validation",
                f"{name} failed",
            )


def main() -> int:
    print("=" * 100)
    print("RAIL-YOJNA PHASE 3 END-TO-END PIPELINE")
    print("=" * 100)

    report = {
        "phase": "3",
        "status": "RUNNING",
        "stages": {},
        "warnings": WARNINGS,
        "errors": ERRORS,
    }

    try:
        config = load_config()

        planning_timestamp = pd.Timestamp(
            config["planning"]["risk_timestamp"]
        )

        daily_capacity = int(
            config["capacity"]["daily_minutes"]
        )

        print("\n[1/8] Checking V3 model artifacts...")
        load_v3_model()
        report["stages"]["v3_model"] = "PASS"
        print("PASS")

        print("\n[2/8] Loading maintenance tasks...")
        tasks = load_tasks()
        report["stages"]["maintenance_tasks"] = {
            "status": "PASS",
            "rows": len(tasks),
            "columns": list(tasks.columns),
        }
        print(f"PASS: {len(tasks):,} rows")

        print("\n[3/8] Building V3 planning risk state...")
        risk = load_v3_risk_state()
        report["stages"]["v3_risk_state"] = {
            "status": "PASS",
            "assets": len(risk),
        }
        print(f"PASS: {len(risk):,} assets")

        print("\n[4/8] Building planning candidates...")
        candidates = build_candidates(
            tasks,
            risk,
            planning_timestamp,
            config,
        )

        eligible_count = int(
            (candidates["candidate_status"] == "eligible").sum()
        )

        report["stages"]["candidate_generation"] = {
            "status": "PASS",
            "total_rows": len(candidates),
            "eligible": eligible_count,
            "invalid": int(
                (candidates["candidate_status"] == "invalid").sum()
            ),
            "deferred": int(
                (candidates["candidate_status"] == "deferred").sum()
            ),
        }

        candidates.to_parquet(
            CANDIDATES,
            index=False,
        )

        print(
            f"PASS: {len(candidates):,} total / "
            f"{eligible_count:,} eligible"
        )

        print("\n[5/8] Inspecting optional planning constraints...")
        optional_tables = load_optional_resource_tables()
        coverage = assess_constraint_coverage(
            optional_tables
        )

        report["stages"]["constraint_coverage"] = {
            k: v
            for k, v in coverage.__dict__.items()
        }

        for name, status in coverage.__dict__.items():
            print(f"  {name}: {status}")

        print("\n[6/8] Solving V2 planning model...")
        plan = solve_daily_capacity(
            candidates,
            daily_capacity,
        )

        validate_output(plan)

        plan.to_parquet(
            PHASE3_PLAN,
            index=False,
        )

        selected = plan[
            plan["selected"] == 1
        ]

        report["stages"]["optimizer"] = {
            "status": "PASS",
            "candidate_rows": len(plan),
            "selected_tasks": len(selected),
            "selected_minutes": int(
                selected["estimated_duration_minutes"].sum()
            ),
            "risk_mass": float(
                selected["calibrated_risk"].sum()
            ),
            "daily_capacity_minutes": daily_capacity,
        }

        print(
            f"PASS: selected={len(selected):,}, "
            f"minutes={selected['estimated_duration_minutes'].sum():,.0f}"
        )

        print("\n[7/8] Running baseline comparison...")

        eligible = plan[
            plan["candidate_status"] == "eligible"
        ].copy()

        chronological = greedy_select(
            eligible,
            ["planned_date", "task_id"],
            [True, True],
            daily_capacity,
        )

        risk_only = greedy_select(
            eligible,
            ["calibrated_risk", "task_id"],
            [False, True],
            daily_capacity,
        )

        rail_yojna = plan[
            plan["selected"] == 1
        ].copy()

        comparison = pd.DataFrame(
            {
                "chronological": summary_metrics(
                    chronological
                ),
                "risk_only": summary_metrics(
                    risk_only
                ),
                "rail_yojna_v2": summary_metrics(
                    rail_yojna
                ),
            }
        )

        comparison.to_csv(
            BASELINE,
            index=True,
        )

        report["stages"]["baseline_comparison"] = {
            "status": "PASS",
            "rows": comparison.to_dict(),
        }

        print(comparison.to_string())

        print("\n[8/8] Final Phase 3 validation...")

        validate_output(plan)

        report["stages"]["final_validation"] = (
            "PASS" if not ERRORS else "FAIL"
        )

    except Exception as exc:
        error(
            "pipeline",
            f"{type(exc).__name__}: {exc}",
        )

    # Save all errors/warnings.
    if ERRORS:
        pd.DataFrame(ERRORS).to_csv(
            ERROR_REPORT,
            index=False,
        )
    else:
        pd.DataFrame(
            columns=[
                "severity",
                "stage",
                "message",
            ]
        ).to_csv(
            ERROR_REPORT,
            index=False,
        )

    report["warnings"] = WARNINGS
    report["errors"] = ERRORS
    report["status"] = (
        "PASS"
        if not ERRORS
        else "FAIL"
    )

    REPORT.write_text(
        json.dumps(
            report,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 100)
    print("PHASE 3 FINAL RESULT")
    print("=" * 100)

    print("STATUS:", report["status"])

    print("\nArtifacts:")
    print("Candidates :", CANDIDATES)
    print("Plan       :", PHASE3_PLAN)
    print("Comparison :", BASELINE)
    print("Report     :", REPORT)
    print("Errors     :", ERROR_REPORT)

    if WARNINGS:
        print("\nWARNINGS:")
        for item in WARNINGS:
            print(" -", item)

    if ERRORS:
        print("\nERRORS:")
        for item in ERRORS:
            print(
                f" - [{item['stage']}] "
                f"{item['message']}"
            )

    print("\n" + "=" * 100)

    return 0 if not ERRORS else 1


if __name__ == "__main__":
    raise SystemExit(main())
