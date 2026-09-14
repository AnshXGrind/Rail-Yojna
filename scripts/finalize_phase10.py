#!/usr/bin/env python3
"""
Rail-Yojna Phase 10 — Full-System Audit
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[1]
API = os.environ.get("RAIL_YOJNA_API", "http://127.0.0.1:8000/api/v1")
REPORT_PATH = REPO / "data/validation/phase10_full_system_audit.json"

MODEL_PATH = REPO / "ml/models/failure_30d_v3_logistic.joblib"
CALIBRATOR_PATH = REPO / "ml/models/failure_30d_v3_probability_calibrator.joblib"
PLAN_PATH = REPO / "optimization/results/maintenance_plan_v2.parquet"
AUDIT_PATH = REPO / "data/audit/decision_events.jsonl"

DATASET_CANDIDATES = [
    REPO / "data/processed/failure_30d_dataset_v3.parquet",
    REPO / "data/processed/failure_30d_target_v3.parquet",
]

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

TIMEOUT = 15


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def http(
    method: str,
    path: str,
    **kwargs: Any,
) -> tuple[int | None, Any, str | None]:
    try:
        response = requests.request(
            method,
            API + path,
            timeout=TIMEOUT,
            **kwargs,
        )
    except Exception as exc:
        return None, None, repr(exc)

    try:
        data = response.json()
    except Exception:
        data = response.text

    return response.status_code, data, None


def check(
    name: str,
    passed: bool,
    detail: str,
    severity: str | None = None,
) -> dict[str, Any]:
    if severity is None:
        severity = "PASS" if passed else "FAIL"

    print(f"[{severity}] {name}: {detail}")

    return {
        "name": name,
        "status": severity,
        "detail": detail,
    }


def scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def safe_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): safe_json(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [safe_json(v) for v in obj]

    if isinstance(obj, np.ndarray):
        return [safe_json(v) for v in obj.tolist()]

    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()

    if isinstance(obj, (np.integer, np.floating)):
        return scalar(obj)

    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None

    return obj


def numeric_series(df: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in df.columns:
        return None
    return pd.to_numeric(df[column], errors="coerce")


def start_backend_if_needed() -> tuple[subprocess.Popen | None, bool]:
    code, _, _ = http("GET", "/health")

    if code == 200:
        return None, False

    print("[INFO] Backend unavailable; starting temporary Uvicorn.")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for _ in range(30):
        time.sleep(0.5)

        code, _, _ = http("GET", "/health")

        if code == 200:
            return proc, True

    proc.terminate()
    return None, False


def discover_dataset() -> Path | None:
    for path in DATASET_CANDIDATES:
        if path.exists():
            return path
    return None


def load_plan() -> pd.DataFrame | None:
    if not PLAN_PATH.exists():
        return None

    try:
        return pd.read_parquet(PLAN_PATH)
    except Exception as exc:
        print(f"[WARN] Could not load planner parquet: {exc}")
        return None


def main() -> int:
    print("=" * 80)
    print("RAIL-YOJNA PHASE 10 — FULL-SYSTEM AUDIT")
    print("=" * 80)

    results: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {}

    temporary_backend = None

    # ------------------------------------------------------------------
    # 1. Required artifacts
    # ------------------------------------------------------------------

    artifacts = {
        "model": MODEL_PATH.exists(),
        "calibrator": CALIBRATOR_PATH.exists(),
        "planner": PLAN_PATH.exists(),
        "audit_log": AUDIT_PATH.exists(),
    }

    results.append(
        check(
            "Required artifacts",
            all(artifacts.values()),
            ", ".join(
                f"{key}={'yes' if value else 'no'}"
                for key, value in artifacts.items()
            ),
        )
    )

    # ------------------------------------------------------------------
    # 2. Artifact loading
    # ------------------------------------------------------------------

    model = None
    calibrator = None

    try:
        if MODEL_PATH.exists():
            model_bundle = joblib.load(MODEL_PATH)
            if not isinstance(model_bundle, dict) or "model" not in model_bundle:
                raise TypeError(
                    "V3 model artifact is not the expected bundle with key 'model'"
                )
            model = model_bundle["model"]

        if CALIBRATOR_PATH.exists():
            calibrator = joblib.load(CALIBRATOR_PATH)

        loaded = model is not None and calibrator is not None

        results.append(
            check(
                "Artifact loading",
                loaded,
                f"model={type(model).__name__ if model else None}, "
                f"calibrator={type(calibrator).__name__ if calibrator else None}",
            )
        )

    except Exception as exc:
        results.append(
            check(
                "Artifact loading",
                False,
                repr(exc),
                "FAIL",
            )
        )

    # ------------------------------------------------------------------
    # 3. Backend
    # ------------------------------------------------------------------

    temporary_backend, _ = start_backend_if_needed()

    code, _, error = http("GET", "/health")

    results.append(
        check(
            "Health API",
            code == 200,
            f"HTTP {code}" + (f"; {error}" if error else ""),
        )
    )

    code, system, error = http("GET", "/system/status")

    system_model = (
        system.get("model", {})
        if isinstance(system, dict)
        else {}
    )

    results.append(
        check(
            "System status",
            code == 200 and isinstance(system, dict),
            f"HTTP {code}, model={system_model.get('version')}",
        )
    )

    evidence["system_status"] = safe_json(system)

    # ------------------------------------------------------------------
    # 4. Planning artifact integrity
    # ------------------------------------------------------------------

    plan = load_plan()

    if plan is None:
        results.append(
            check(
                "Planning artifact integrity",
                False,
                "maintenance_plan_v2.parquet unavailable",
                "FAIL",
            )
        )
    else:
        issues = []

        for column in ("task_id", "asset_id"):
            if column not in plan.columns:
                issues.append(f"missing:{column}")

        if "duration_minutes" in plan.columns:
            durations = numeric_series(plan, "duration_minutes")

            if durations is not None:
                if durations.isna().any():
                    issues.append("NaN duration_minutes")

                if (durations < 0).any():
                    issues.append("negative duration_minutes")

        if "risk_score" in plan.columns:
            risk = numeric_series(plan, "risk_score")

            if risk is not None:
                if risk.isna().any():
                    issues.append("NaN risk_score")

                if ((risk < 0) | (risk > 1)).any():
                    issues.append("risk_score outside [0,1]")

        duplicate_tasks = (
            int(plan["task_id"].duplicated().sum())
            if "task_id" in plan.columns
            else -1
        )

        evidence["planning"] = {
            "rows": len(plan),
            "columns": list(plan.columns),
            "duplicate_task_ids": duplicate_tasks,
        }

        valid = not issues and duplicate_tasks == 0

        results.append(
            check(
                "Planning artifact integrity",
                valid,
                f"rows={len(plan)}, "
                f"duplicate_task_ids={duplicate_tasks}, "
                f"issues={issues or 'none'}",
            )
        )

    # ------------------------------------------------------------------
    # 5. API ↔ planner consistency
    # ------------------------------------------------------------------

    code_summary, summary, _ = http(
        "GET",
        "/planning/summary",
    )

    code_metrics, metrics, _ = http(
        "GET",
        "/planning/metrics",
    )

    summary_count = (
        int(summary.get("selected_tasks", -1))
        if isinstance(summary, dict)
        else -1
    )

    metrics_count = (
        int(metrics.get("selected_tasks", -1))
        if isinstance(metrics, dict)
        else -1
    )

    selected_count = (
        int(plan["selected"].sum())
        if plan is not None and "selected" in plan.columns
        else -1
    )

    valid = (
        code_summary == 200
        and code_metrics == 200
        and summary_count == metrics_count == selected_count
    )

    results.append(
        check(
            "Planning API ↔ artifact consistency",
            valid,
            f"summary={summary_count}, "
            f"metrics={metrics_count}, "
            f"selected_rows={selected_count}, "
            f"candidate_rows={len(plan) if plan is not None else -1}",
        )
    )

    # ------------------------------------------------------------------
    # 6. Risk → planning coverage
    # ------------------------------------------------------------------

    code, top_payload, _ = http(
        "GET",
        "/assets/risk/top?limit=100",
    )

    if isinstance(top_payload, dict):
        top_assets = top_payload.get("items", [])
    elif isinstance(top_payload, list):
        top_assets = top_payload
    else:
        top_assets = []

    selected_asset_ids: set[str] = set()
    deferred_asset_ids: set[str] = set()
    eligible_asset_ids: set[str] = set()

    if plan is not None and "asset_id" in plan.columns:
        if "selected" in plan.columns:
            selected_asset_ids = set(
                plan.loc[plan["selected"].astype(bool), "asset_id"]
                .dropna()
                .astype(str)
            )

        if "candidate_status" in plan.columns:
            eligible_asset_ids = set(
                plan.loc[
                    plan["candidate_status"].astype(str).eq("eligible"),
                    "asset_id",
                ]
                .dropna()
                .astype(str)
            )

        if "decision" in plan.columns:
            deferred_asset_ids = set(
                plan.loc[
                    plan["decision"].astype(str)
                    .eq("deferred_by_optimization"),
                    "asset_id",
                ]
                .dropna()
                .astype(str)
            )

    coverage = {}

    for k in (10, 25, 50, 100):
        subset = top_assets[:k]

        ids = {
            str(row.get("asset_id"))
            for row in subset
            if isinstance(row, dict)
            and row.get("asset_id") is not None
        }

        represented = len(ids & selected_asset_ids)
        eligible = len(ids & eligible_asset_ids)
        deferred = len(ids & deferred_asset_ids)

        coverage[str(k)] = {
            "risk_assets": len(ids),
            "selected": represented,
            "eligible": eligible,
            "deferred_by_optimization": deferred,
            "coverage": represented / len(ids)
            if ids
            else None,
        }

    first_asset = (
        str(top_assets[0].get("asset_id"))
        if top_assets
        else None
    )

    first_selected = (
        first_asset in selected_asset_ids
        if first_asset is not None
        else False
    )

    evidence["risk_plan_coverage"] = coverage
    evidence["highest_risk_asset"] = first_asset

    results.append(
        check(
            "Risk → planning coverage",
            code == 200 and bool(top_assets),
            ", ".join(
                f"top{k}=selected:{v['selected']}/{v['risk_assets']},"
                f"eligible:{v['eligible']},"
                f"deferred:{v['deferred_by_optimization']}"
                for k, v in coverage.items()
            ),
        )
    )

    results.append(
        check(
            "Highest-risk asset representation",
            first_asset is None or first_selected,
            f"asset={first_asset}, "
            f"selected_in_plan={first_selected}",
            "PASS" if first_asset is None or first_selected else "WARN",
        )
    )

    # ------------------------------------------------------------------
    # 7. Dataset / 23-feature integrity
    # ------------------------------------------------------------------

    dataset_path = discover_dataset()
    dataset = None

    if dataset_path is None:
        results.append(
            check(
                "Feature dataset availability",
                False,
                "V3 processed dataset not found",
                "FAIL",
            )
        )
    else:
        try:
            dataset = pd.read_parquet(dataset_path)

            missing = [
                feature
                for feature in FEATURES
                if feature not in dataset.columns
            ]

            nonfinite = []

            for feature in FEATURES:
                series = numeric_series(dataset, feature)

                if series is None:
                    continue

                values = series.dropna().to_numpy()

                if values.size and not np.isfinite(values).all():
                    nonfinite.append(feature)

            valid = not missing and not nonfinite

            results.append(
                check(
                    "23-feature integrity",
                    valid,
                    f"dataset={rel(dataset_path)}, "
                    f"rows={len(dataset)}, "
                    f"missing={missing}, "
                    f"nonfinite={nonfinite}",
                )
            )

            evidence["dataset"] = {
                "path": rel(dataset_path),
                "rows": len(dataset),
                "missing_features": missing,
                "columns": list(dataset.columns),
            }

        except Exception as exc:
            results.append(
                check(
                    "Feature dataset integrity",
                    False,
                    repr(exc),
                    "FAIL",
                )
            )

    # ------------------------------------------------------------------
    # 8. Local model probability integrity
    # ------------------------------------------------------------------

    if (
        model is not None
        and calibrator is not None
        and dataset is not None
        and all(f in dataset.columns for f in FEATURES)
    ):
        try:
            sample = dataset[FEATURES].head(32)

            raw = model.predict_proba(sample)[:, 1]

            calibrated = (
                calibrator.predict_proba(
                    np.asarray(raw).reshape(-1, 1)
                )[:, 1]
                if calibrator is not None
                else raw
            )

            valid = (
                np.isfinite(raw).all()
                and np.isfinite(calibrated).all()
                and ((raw >= 0) & (raw <= 1)).all()
                and ((calibrated >= 0) & (calibrated <= 1)).all()
            )

            evidence["prediction_probe"] = {
                "rows": len(sample),
                "raw_min": float(raw.min()),
                "raw_max": float(raw.max()),
                "calibrated_min": float(calibrated.min()),
                "calibrated_max": float(calibrated.max()),
            }

            results.append(
                check(
                    "Model probability integrity",
                    bool(valid),
                    json.dumps(
                        evidence["prediction_probe"]
                    ),
                )
            )

        except Exception as exc:
            results.append(
                check(
                    "Model probability integrity",
                    False,
                    repr(exc),
                    "FAIL",
                )
            )

    # ------------------------------------------------------------------
    # 9. Live inference contract
    #
    # The public API intentionally accepts the compact inference request:
    # asset_id + timestamp + seven current measurements.
    # FeatureBuilder constructs the full V3 model vector internally.
    # ------------------------------------------------------------------

    inference_payload = None

    if dataset is not None:
        row = dataset.iloc[0]

        if "asset_id" not in dataset.columns:
            results.append(
                check(
                    "Live inference contract",
                    False,
                    "Dataset has no asset_id column",
                    "FAIL",
                )
            )
        else:
            timestamp_value = None

            if "timestamp" in dataset.columns:
                timestamp_value = row["timestamp"]
            elif "observation_timestamp" in dataset.columns:
                timestamp_value = row["observation_timestamp"]

            if timestamp_value is None:
                results.append(
                    check(
                        "Live inference contract",
                        False,
                        "Dataset has no timestamp/observation_timestamp column",
                        "FAIL",
                    )
                )
            else:
                inference_payload = {
                    "asset_id": str(row["asset_id"]),
                    "timestamp": str(timestamp_value),
                    "condition_score": scalar(row["condition_score"]),
                    "degradation_rate": scalar(row["degradation_rate"]),
                    "measurement_value": scalar(row["measurement_value"]),
                    "inspection_quality": scalar(row["inspection_quality"]),
                    "measurement_confidence": scalar(row["measurement_confidence"]),
                }

                code, prediction, error = http(
                    "POST",
                    "/risk/predict",
                    json=inference_payload,
                )

                probability = (
                    prediction.get("risk_probability")
                    if isinstance(prediction, dict)
                    else None
                )

                valid = (
                    code == 200
                    and isinstance(probability, (int, float))
                    and math.isfinite(float(probability))
                    and 0 <= float(probability) <= 1
                )

                results.append(
                    check(
                        "Live inference contract",
                        valid,
                        f"HTTP {code}, "
                        f"risk_probability={probability}"
                        + (f", error={error}" if error else ""),
                    )
                )

    # ------------------------------------------------------------------
    # 10. Invalid inference handling
    # ------------------------------------------------------------------

    invalid_payloads = {}

    if inference_payload is not None:
        invalid_payloads = {
            "missing_required_measurement": {
                k: v
                for k, v in inference_payload.items()
                if k != "condition_score"
            },
            "extra_feature": {
                **inference_payload,
                "__phase10_unknown_feature__": 1,
            },
            "wrong_type": {
                **inference_payload,
                "condition_score": "invalid-number",
            },
            "empty_payload": {},
        }

    invalid_results = {}

    for name, invalid_payload in invalid_payloads.items():
        code, response_data, error = http(
            "POST",
            "/risk/predict",
            json=invalid_payload,
        )

        invalid_results[name] = {
            "status": code,
            "error": error,
            "response": response_data,
        }

    evidence["invalid_inference_cases"] = safe_json(
        invalid_results
    )

    missing_ok = (
        isinstance(invalid_results.get("missing_required_measurement", {}).get("status"), int)
        and 400 <= invalid_results["missing_required_measurement"]["status"] < 500
    )

    wrong_type_ok = (
        isinstance(invalid_results.get("wrong_type", {}).get("status"), int)
        and 400 <= invalid_results["wrong_type"]["status"] < 500
    )

    empty_ok = (
        isinstance(invalid_results.get("empty_payload", {}).get("status"), int)
        and 400 <= invalid_results["empty_payload"]["status"] < 500
    )

    extra = invalid_results.get("extra_feature", {})
    extra_status = extra.get("status")

    # Pydantic may legitimately ignore unknown fields. Treat this as safe
    # when the request still succeeds with a valid probability.
    extra_ok = False

    if extra_status == 200 and isinstance(extra.get("response"), dict):
        extra_probability = extra["response"].get("risk_probability")

        extra_ok = (
            isinstance(extra_probability, (int, float))
            and math.isfinite(float(extra_probability))
            and 0 <= float(extra_probability) <= 1
        )
    elif isinstance(extra_status, int) and 400 <= extra_status < 500:
        extra_ok = True

    invalid_safe = (
        missing_ok
        and wrong_type_ok
        and empty_ok
        and extra_ok
    )

    results.append(
        check(
            "Inference invalid-input handling",
            invalid_safe,
            ", ".join(
                f"{name}=HTTP {item['status']}"
                for name, item in invalid_results.items()
            )
            + (
                "; extra field accepted and returned valid prediction"
                if extra_status == 200 and extra_ok
                else ""
            ),
            "PASS" if invalid_safe else "FAIL",
        )
    )

    # ------------------------------------------------------------------
    # 11. Planner task trace
    # ------------------------------------------------------------------

    task_id = None

    if (
        plan is not None
        and "task_id" in plan.columns
        and len(plan) > 0
    ):
        task_id = str(plan.iloc[0]["task_id"])

    if task_id:
        code, task, _ = http(
            "GET",
            f"/planning/tasks/{task_id}",
        )

        valid = code == 200 and isinstance(task, dict)

        results.append(
            check(
                "Planner task traceability",
                valid,
                f"task={task_id}, HTTP {code}",
            )
        )

    # ------------------------------------------------------------------
    # 12. Audit trail
    # ------------------------------------------------------------------

    code, audit_payload, _ = http(
        "GET",
        "/audit/events",
    )

    if isinstance(audit_payload, list):
        events = audit_payload
    elif isinstance(audit_payload, dict):
        events = audit_payload.get("events", [])
    else:
        events = []

    malformed = []

    for index, event in enumerate(events):
        if not isinstance(event, dict):
            malformed.append(f"{index}:not_object")
            continue

        for field in ("id", "type", "timestamp"):
            if field not in event:
                malformed.append(
                    f"{index}:missing_{field}"
                )

    evidence["audit"] = {
        "event_count": len(events),
        "malformed_count": len(malformed),
        "malformed_examples": malformed[:20],
    }

    results.append(
        check(
            "Audit trail integrity",
            code == 200 and not malformed,
            f"events={len(events)}, "
            f"malformed={len(malformed)}",
        )
    )

    # ------------------------------------------------------------------
    # 13. Artifact hashes
    # ------------------------------------------------------------------

    dataset_for_hash = (
        dataset_path
        if dataset_path is not None
        else None
    )

    hashes = {
        "model": sha256_file(MODEL_PATH),
        "calibrator": sha256_file(CALIBRATOR_PATH),
        "planner": sha256_file(PLAN_PATH),
        "dataset": (
            sha256_file(dataset_for_hash)
            if dataset_for_hash
            else None
        ),
    }

    evidence["artifact_sha256"] = hashes

    results.append(
        check(
            "Artifact reproducibility hashes",
            all(value for value in hashes.values()),
            ", ".join(
                f"{key}={value[:12]}…"
                if value
                else f"{key}=missing"
                for key, value in hashes.items()
            ),
        )
    )

    # ------------------------------------------------------------------
    # 14. Safety boundary
    # ------------------------------------------------------------------

    safety = (
        system.get("safety_policy", {})
        if isinstance(system, dict)
        else {}
    )

    safety_ok = (
        safety.get("human_approval_required") is True
        and safety.get("autonomous_signalling") is False
        and safety.get("autonomous_train_control") is False
        and safety.get("autonomous_block_authority") is False
    )

    results.append(
        check(
            "Safety boundary",
            safety_ok,
            json.dumps(safety),
        )
    )

    # ------------------------------------------------------------------
    # 15. Unknown resource handling
    # ------------------------------------------------------------------

    unknown_task_code, _, _ = http(
        "GET",
        "/planning/tasks/__phase10_missing_task__",
    )

    unknown_asset_code, _, _ = http(
        "GET",
        "/assets/__phase10_missing_asset__/risk",
    )

    failure_safe = (
        isinstance(unknown_task_code, int)
        and 400 <= unknown_task_code < 500
        and isinstance(unknown_asset_code, int)
        and 400 <= unknown_asset_code < 500
    )

    results.append(
        check(
            "Unknown-resource failure handling",
            failure_safe,
            f"task=HTTP {unknown_task_code}, "
            f"asset=HTTP {unknown_asset_code}",
        )
    )

    # ------------------------------------------------------------------
    # Final report
    # ------------------------------------------------------------------

    statuses = [result["status"] for result in results]

    failures = statuses.count("FAIL")
    warnings = statuses.count("WARN")
    passed = statuses.count("PASS")
    info = statuses.count("INFO")

    overall = (
        "FAIL"
        if failures
        else "PASS_WITH_WARNINGS"
        if warnings
        else "PASS"
    )

    report = {
        "phase": "10",
        "status": overall,
        "generated_at": now_iso(),
        "api": API,
        "checks": results,
        "summary": {
            "total_checks": len(results),
            "passed": passed,
            "warnings": warnings,
            "failures": failures,
            "info": info,
        },
        "versions": {
            "model": "failure_30d_v3_logistic",
            "planner": "maintenance_plan_v2",
        },
        "artifacts": {
            "model": rel(MODEL_PATH),
            "calibrator": rel(CALIBRATOR_PATH),
            "planner": rel(PLAN_PATH),
            "dataset": (
                rel(dataset_path)
                if dataset_path
                else None
            ),
            "audit_log": rel(AUDIT_PATH),
        },
        "evidence": safe_json(evidence),
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    print()
    print("=" * 80)
    print(
        "PHASE 10 "
        + ("COMPLETE" if overall != "FAIL" else "FAILED")
    )
    print("=" * 80)

    print(
        json.dumps(
            {
                "phase": "10",
                "status": overall,
                "summary": report["summary"],
                "report": str(REPORT_PATH),
            },
            indent=2,
        )
    )

    if temporary_backend is not None:
        temporary_backend.terminate()

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
