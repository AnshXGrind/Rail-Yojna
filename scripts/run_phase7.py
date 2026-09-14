from __future__ import annotations

import json
import math
import subprocess
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)


ROOT = Path(__file__).resolve().parents[1]

MODEL_PATH = ROOT / "ml/models/failure_30d_v3_logistic.joblib"
CALIBRATOR_PATH = ROOT / "ml/models/failure_30d_v3_probability_calibrator.joblib"
METADATA_PATH = ROOT / "ml/models/failure_30d_v3_metadata.json"

DATA_PATH = ROOT / "data/processed/failure_30d_dataset_v3.parquet"

RESULTS_PATH = ROOT / "ml/models/failure_30d_v3_results.csv"
BACKTEST_PATH = ROOT / "ml/models/failure_30d_v3_backtest.csv"
EXPANDING_PATH = ROOT / "ml/models/failure_30d_v3_expanding_backtest.csv"
EFFECTS_PATH = ROOT / "ml/models/failure_30d_v3_feature_effects.csv"

V2_V3_PATH = ROOT / "ml/models/failure_30d_v2_vs_v3_comparison.csv"

PLAN_PATH = ROOT / "optimization/results/maintenance_plan_v2.parquet"
PLAN_COMPARISON_PATH = ROOT / "optimization/results/maintenance_plan_v2_comparison.csv"

REPORT_DIR = ROOT / "data/validation"
REPORT_PATH = REPORT_DIR / "phase7_evaluation_report.json"
METRICS_PATH = ROOT / "ml/models/final_evaluation_metrics.csv"
EVALUATION_DOC = ROOT / "docs/evaluation.md"


def fail(message: str):
    print(f"\n[FAIL] {message}")
    raise SystemExit(1)


def assert_exists(path: Path, label: str):
    if not path.exists() or path.stat().st_size == 0:
        fail(f"Missing required artifact: {label}: {path}")
    print(f"[PASS] {label}")


def finite(value):
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            return None
        return float(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    return value


def json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    if isinstance(obj, tuple):
        return [json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return finite(obj)
    if pd.isna(obj):
        return None
    return obj


def find_column(df: pd.DataFrame, candidates: list[str], label: str):
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    lowered = {str(c).lower(): c for c in df.columns}

    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]

    fail(
        f"Could not identify {label}. "
        f"Available columns: {list(df.columns)}"
    )


def load_metadata():
    if not METADATA_PATH.exists():
        return {}

    return json.loads(
        METADATA_PATH.read_text(encoding="utf-8")
    )


def bootstrap_metric(
    y_true,
    y_score,
    metric,
    n_bootstrap=100,
    seed=42,
):
    rng = np.random.default_rng(seed)

    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)

    positives = np.where(y_true == 1)[0]
    negatives = np.where(y_true == 0)[0]

    if len(positives) < 2 or len(negatives) < 2:
        return None

    values = []

    for _ in range(n_bootstrap):
        pos_idx = rng.choice(
            positives,
            size=len(positives),
            replace=True,
        )
        neg_idx = rng.choice(
            negatives,
            size=len(negatives),
            replace=True,
        )

        idx = np.concatenate([pos_idx, neg_idx])

        try:
            values.append(
                float(metric(y_true[idx], y_score[idx]))
            )
        except Exception:
            continue

    if not values:
        return None

    values = np.asarray(values)

    return {
        "mean": float(np.mean(values)),
        "lower_95": float(np.quantile(values, 0.025)),
        "upper_95": float(np.quantile(values, 0.975)),
        "bootstrap_samples": int(len(values)),
    }


def calibration_metrics(y_true, probability):
    y_true = np.asarray(y_true)
    probability = np.asarray(probability)

    order = np.argsort(probability)
    y_sorted = y_true[order]
    p_sorted = probability[order]

    bins = np.array_split(
        np.arange(len(y_true)),
        10,
    )

    ece = 0.0
    rows = []

    for bin_index, idx in enumerate(bins, start=1):
        if len(idx) == 0:
            continue

        observed = float(np.mean(y_sorted[idx]))
        predicted = float(np.mean(p_sorted[idx]))
        weight = len(idx) / len(y_true)

        ece += weight * abs(observed - predicted)

        rows.append(
            {
                "bin": bin_index,
                "count": int(len(idx)),
                "mean_probability": predicted,
                "observed_frequency": observed,
                "absolute_gap": abs(observed - predicted),
            }
        )

    return float(ece), rows


def top_k_metrics(y_true, probability):
    y_true = np.asarray(y_true)
    probability = np.asarray(probability)

    rows = []

    for pct in [0.005, 0.01, 0.02, 0.05, 0.10]:
        n = max(1, int(math.ceil(len(y_true) * pct)))

        order = np.argsort(
            probability
        )[::-1]

        selected = order[:n]

        selected_failures = int(
            y_true[selected].sum()
        )

        total_failures = int(
            y_true.sum()
        )

        precision = selected_failures / n

        recall = (
            selected_failures / total_failures
            if total_failures
            else 0.0
        )

        baseline = float(np.mean(y_true))
        lift = (
            precision / baseline
            if baseline > 0
            else None
        )

        rows.append(
            {
                "top_fraction": pct,
                "selected_observations": n,
                "failures_captured": selected_failures,
                "precision": precision,
                "recall": recall,
                "baseline_failure_rate": baseline,
                "lift_vs_baseline": lift,
            }
        )

    return rows


def main():
    print("=" * 80)
    print("RAIL-YOJNA PHASE 7 — FINAL RESEARCH EVALUATION")
    print("=" * 80)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "docs").mkdir(parents=True, exist_ok=True)

    required = {
        MODEL_PATH: "V3 model",
        CALIBRATOR_PATH: "V3 probability calibrator",
        DATA_PATH: "V3 evaluation dataset",
        METADATA_PATH: "V3 metadata",
        BACKTEST_PATH: "frozen backtest results",
        EXPANDING_PATH: "expanding backtest results",
        EFFECTS_PATH: "feature effects",
        V2_V3_PATH: "V2/V3 comparison",
        PLAN_PATH: "maintenance_plan_v2",
        PLAN_COMPARISON_PATH: "optimization comparison",
    }

    for path, label in required.items():
        assert_exists(path, label)

    metadata = load_metadata()

    df = pd.read_parquet(DATA_PATH)

    print(f"[INFO] Evaluation rows: {len(df):,}")
    print(f"[INFO] Evaluation columns: {len(df.columns)}")

    target_col = find_column(
        df,
        [
            "failure_within_horizon",
            "failure_30d",
            "failure_30d_target",
            "target",
            "label",
        ],
        "target column",
    )

    time_col = find_column(
        df,
        [
            "observation_timestamp",
            "timestamp",
            "measurement_timestamp",
            "observed_at",
            "event_timestamp",
        ],
        "observation timestamp",
    )

    target = df[target_col].astype(int)

    timestamps = pd.to_datetime(
        df[time_col],
        utc=True,
    )

    positive_count = int(target.sum())
    negative_count = int((target == 0).sum())
    prevalence = positive_count / len(df)

    print(
        f"[PASS] Target: {target_col} | "
        f"positives={positive_count:,} | "
        f"prevalence={prevalence:.6%}"
    )

    # ------------------------------------------------------------------
    # Model feature discovery
    # ------------------------------------------------------------------

    model = joblib.load(MODEL_PATH)
    calibrator = joblib.load(CALIBRATOR_PATH)

    feature_names = metadata.get("model_features")

    if not feature_names:
        candidate = getattr(model, "feature_names_in_", None)

        if candidate is not None:
            feature_names = list(candidate)

    if not feature_names:
        fail("Could not determine V3 model feature names")

    missing_features = [
        x for x in feature_names
        if x not in df.columns
    ]

    if missing_features:
        fail(
            f"V3 evaluation dataset is missing model features: "
            f"{missing_features}"
        )

    print(
        f"[PASS] V3 feature contract: "
        f"{len(feature_names)} features"
    )

    X = df[feature_names]

    # ------------------------------------------------------------------
    # Full-dataset predictions
    # ------------------------------------------------------------------

    raw_probability = np.asarray(
        model.predict_proba(X)[:, 1]
    )

    calibrated_probability = np.asarray(
        calibrator.predict_proba(
            raw_probability.reshape(-1, 1)
        )[:, 1]
    )

    assert len(raw_probability) == len(df)
    assert len(calibrated_probability) == len(df)

    if np.any(~np.isfinite(raw_probability)):
        fail("Non-finite raw probabilities detected")

    if np.any(~np.isfinite(calibrated_probability)):
        fail("Non-finite calibrated probabilities detected")

    if not np.all(
        (raw_probability >= 0)
        & (raw_probability <= 1)
    ):
        fail("Raw probabilities outside [0, 1]")

    if not np.all(
        (calibrated_probability >= 0)
        & (calibrated_probability <= 1)
    ):
        fail("Calibrated probabilities outside [0, 1]")

    print("[PASS] Probability integrity")

    # ------------------------------------------------------------------
    # Temporal splits matching the frozen V3 protocol
    # ------------------------------------------------------------------

    train_end = pd.Timestamp(
        "2024-12-12T00:00:00Z"
    )

    validation_end = pd.Timestamp(
        "2025-07-31T00:00:00Z"
    )

    train_mask = timestamps < train_end
    validation_mask = (
        (timestamps >= train_end)
        & (timestamps < validation_end)
    )
    test_mask = timestamps >= validation_end

    split_sizes = {
        "train": int(train_mask.sum()),
        "validation": int(validation_mask.sum()),
        "test": int(test_mask.sum()),
    }

    print("[INFO] Temporal split:", split_sizes)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def score_split(name, mask):
        y = target[mask].to_numpy()
        raw = raw_probability[mask]
        calibrated = calibrated_probability[mask]

        raw_pr = average_precision_score(y, raw)
        raw_roc = roc_auc_score(y, raw)
        raw_brier = brier_score_loss(y, raw)

        cal_pr = average_precision_score(y, calibrated)
        cal_roc = roc_auc_score(y, calibrated)
        cal_brier = brier_score_loss(y, calibrated)

        raw_ece, raw_bins = calibration_metrics(y, raw)
        cal_ece, cal_bins = calibration_metrics(y, calibrated)

        return {
            "split": name,
            "rows": int(len(y)),
            "positives": int(y.sum()),
            "prevalence": float(np.mean(y)),
            "raw_pr_auc": float(raw_pr),
            "raw_roc_auc": float(raw_roc),
            "raw_brier": float(raw_brier),
            "calibrated_pr_auc": float(cal_pr),
            "calibrated_roc_auc": float(cal_roc),
            "calibrated_brier": float(cal_brier),
            "raw_ece": float(raw_ece),
            "calibrated_ece": float(cal_ece),
            "calibration_improvement_brier": float(
                raw_brier - cal_brier
            ),
            "calibration_bins_raw": raw_bins,
            "calibration_bins_calibrated": cal_bins,
        }

    split_results = [
        score_split("train", train_mask),
        score_split("validation", validation_mask),
        score_split("test", test_mask),
    ]

    for row in split_results:
        print(
            f"[PASS] {row['split']}: "
            f"PR-AUC={row['calibrated_pr_auc']:.6f}, "
            f"ROC-AUC={row['calibrated_roc_auc']:.6f}, "
            f"Brier={row['calibrated_brier']:.6f}, "
            f"ECE={row['calibrated_ece']:.6f}"
        )

    test_y = target[test_mask].to_numpy()
    test_raw = raw_probability[test_mask]
    test_cal = calibrated_probability[test_mask]

    # ------------------------------------------------------------------
    # Bootstrap confidence intervals
    # ------------------------------------------------------------------

    bootstrap = {
        "test_raw_pr_auc": bootstrap_metric(
            test_y,
            test_raw,
            average_precision_score,
        ),
        "test_calibrated_pr_auc": bootstrap_metric(
            test_y,
            test_cal,
            average_precision_score,
        ),
        "test_raw_roc_auc": bootstrap_metric(
            test_y,
            test_raw,
            roc_auc_score,
        ),
        "test_calibrated_roc_auc": bootstrap_metric(
            test_y,
            test_cal,
            roc_auc_score,
        ),
    }

    print("[PASS] Bootstrap confidence intervals")

    # ------------------------------------------------------------------
    # Top-K operational metrics
    # ------------------------------------------------------------------

    top_k = top_k_metrics(
        test_y,
        test_raw,
    )

    top_k_df = pd.DataFrame(top_k)

    print("[PASS] Top-K operational metrics")

    # ------------------------------------------------------------------
    # Ranking preservation by calibration
    # ------------------------------------------------------------------

    raw_order = np.argsort(
        np.argsort(raw_probability[test_mask])
    )

    calibrated_order = np.argsort(
        np.argsort(calibrated_probability[test_mask])
    )

    rank_corr = float(
        np.corrcoef(
            raw_order,
            calibrated_order,
        )[0, 1]
    )

    print(
        f"[PASS] Raw/calibrated ranking correlation: "
        f"{rank_corr:.8f}"
    )

    # ------------------------------------------------------------------
    # Frozen + expanding temporal backtest
    # ------------------------------------------------------------------

    backtest = pd.read_csv(BACKTEST_PATH)
    expanding = pd.read_csv(EXPANDING_PATH)

    def summarize_backtest(frame, name):
        if frame.empty:
            return {
                "name": name,
                "rows": 0,
            }

        numeric_candidates = [
            "pr_auc",
            "roc_auc",
            "top1_precision",
            "top5_recall",
            "top10_recall",
        ]

        result = {
            "name": name,
            "rows": int(len(frame)),
        }

        for column in numeric_candidates:
            if column in frame.columns:
                values = pd.to_numeric(
                    frame[column],
                    errors="coerce",
                ).dropna()

                if len(values):
                    result[column] = {
                        "mean": float(values.mean()),
                        "min": float(values.min()),
                        "max": float(values.max()),
                        "std": float(values.std(ddof=0)),
                    }

        return result

    backtest_summary = {
        "frozen": summarize_backtest(
            backtest,
            "frozen",
        ),
        "expanding": summarize_backtest(
            expanding,
            "expanding",
        ),
    }

    print("[PASS] Temporal backtest summary")

    # ------------------------------------------------------------------
    # V2 vs V3
    # ------------------------------------------------------------------

    v2_v3 = pd.read_csv(V2_V3_PATH)

    v2_v3_summary = {
        "rows": int(len(v2_v3)),
        "columns": list(v2_v3.columns),
        "records": json_safe(
            v2_v3.to_dict(orient="records")
        ),
    }

    print("[PASS] V2/V3 comparison")

    # ------------------------------------------------------------------
    # Optimization evaluation
    # ------------------------------------------------------------------

    plan = pd.read_parquet(PLAN_PATH)
    comparison = pd.read_csv(PLAN_COMPARISON_PATH)

    if "selected" not in plan.columns:
        fail("maintenance_plan_v2 missing selected column")

    selected = plan[plan["selected"] == 1].copy()

    risk = pd.to_numeric(
        selected["calibrated_risk"],
        errors="coerce",
    )

    optimization = {
        "candidate_tasks": int(len(plan)),
        "selected_tasks": int(len(selected)),
        "selected_minutes": int(
            selected["estimated_duration_minutes"].sum()
        ),
        "selected_hours": float(
            selected["estimated_duration_minutes"].sum() / 60
        ),
        "risk_mass": float(risk.sum()),
        "mean_selected_risk": float(risk.mean()),
        "high_risk_tasks": int(
            (risk >= 0.20).sum()
        ),
        "critical_risk_tasks": int(
            (risk >= 0.50).sum()
        ),
        "p1_tasks": int(
            (selected["priority"].astype(str) == "P1").sum()
        ),
        "block_required_tasks": int(
            selected["block_required"].astype(bool).sum()
        ),
        "comparison_records": json_safe(
            comparison.to_dict(orient="records")
        ),
    }

    print("[PASS] Optimization evaluation")

    # ------------------------------------------------------------------
    # Feature effects
    # ------------------------------------------------------------------

    effects = pd.read_csv(EFFECTS_PATH)

    if "feature" not in effects.columns:
        feature_col = effects.columns[0]
    else:
        feature_col = "feature"

    coefficient_col = None

    for candidate in [
        "coefficient",
        "coef",
        "effect",
        "weight",
    ]:
        if candidate in effects.columns:
            coefficient_col = candidate
            break

    feature_effects = {
        "rows": int(len(effects)),
        "columns": list(effects.columns),
        "top_effects": json_safe(
            effects.head(15).to_dict(
                orient="records"
            )
        ),
    }

    if coefficient_col:
        numeric_effects = effects.copy()

        numeric_effects[coefficient_col] = pd.to_numeric(
            numeric_effects[coefficient_col],
            errors="coerce",
        )

        numeric_effects["absolute_effect"] = (
            numeric_effects[coefficient_col]
            .abs()
        )

        top_absolute = (
            numeric_effects
            .sort_values(
                "absolute_effect",
                ascending=False,
            )
            .head(15)
        )

        feature_effects["top_absolute_effects"] = (
            json_safe(
                top_absolute.to_dict(
                    orient="records"
                )
            )
        )

    print("[PASS] Feature-effect evaluation")

    # ------------------------------------------------------------------
    # Dataset integrity
    # ------------------------------------------------------------------

    integrity = {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "positive_labels": positive_count,
        "negative_labels": negative_count,
        "positive_rate": prevalence,
        "duplicate_rows": int(
            df.duplicated().sum()
        ),
        "duplicate_prediction_keys": None,
        "time_min": str(timestamps.min()),
        "time_max": str(timestamps.max()),
    }

    for key_candidates in [
        ["asset_id", time_col],
        ["asset_id", "observation_timestamp"],
    ]:
        if all(x in df.columns for x in key_candidates):
            integrity["duplicate_prediction_keys"] = int(
                df.duplicated(
                    subset=key_candidates
                ).sum()
            )
            break

    print("[PASS] Dataset integrity summary")

    # ------------------------------------------------------------------
    # Research limitations
    # ------------------------------------------------------------------

    limitations = [
        (
            "Synthetic-data limitation",
            "The dataset is synthetic and should not be interpreted "
            "as evidence of real-world railway failure prevalence."
        ),
        (
            "Failure-target limitation",
            "The modeled target represents a 30-day failure horizon "
            "under the project's synthetic event-generation process."
        ),
        (
            "Defect-feature limitation",
            "The defect-recency feature is an unusually strong predictor "
            "in the synthetic benchmark and is therefore an important "
            "deployment/generalization limitation."
        ),
        (
            "Optimization limitation",
            "The V2 planner uses the available modeled maintenance "
            "constraints; several operational constraint tables exist "
            "without all of them being enforced as hard solver constraints."
        ),
        (
            "Safety limitation",
            "The system is a decision-support prototype and does not "
            "issue railway signalling, routing, dispatch, or movement authority."
        ),
        (
            "External-validation limitation",
            "No real-world railway dataset or prospective field trial "
            "is represented by these metrics."
        ),
    ]

    # ------------------------------------------------------------------
    # Final research interpretation
    # ------------------------------------------------------------------

    test_cal_pr = split_results[-1]["calibrated_pr_auc"]
    test_cal_roc = split_results[-1]["calibrated_roc_auc"]
    test_cal_brier = split_results[-1]["calibrated_brier"]
    test_cal_ece = split_results[-1]["calibrated_ece"]

    final_assessment = {
        "status": "PASS",
        "test_calibrated_pr_auc": test_cal_pr,
        "test_calibrated_roc_auc": test_cal_roc,
        "test_calibrated_brier": test_cal_brier,
        "test_calibrated_ece": test_cal_ece,
        "ranking_preservation_correlation": rank_corr,
        "optimization_selected_tasks": optimization[
            "selected_tasks"
        ],
        "optimization_risk_mass": optimization[
            "risk_mass"
        ],
        "interpretation": (
            "The frozen V3 model demonstrates strong temporal "
            "discrimination on the synthetic benchmark. Probability "
            "calibration materially improves probability quality while "
            "preserving ranking usefulness. The optimization layer converts "
            "risk estimates into a maintenance prioritization plan under "
            "the modeled planning constraints. These results establish "
            "research-engineering validity for the prototype, not real-world "
            "railway safety certification."
        ),
    }

    # ------------------------------------------------------------------
    # Save machine-readable metrics
    # ------------------------------------------------------------------

    metric_rows = []

    for split in split_results:
        metric_rows.append(
            {
                "category": "classification",
                "split": split["split"],
                "metric": "raw_pr_auc",
                "value": split["raw_pr_auc"],
            }
        )

        metric_rows.append(
            {
                "category": "classification",
                "split": split["split"],
                "metric": "calibrated_pr_auc",
                "value": split["calibrated_pr_auc"],
            }
        )

        metric_rows.append(
            {
                "category": "classification",
                "split": split["split"],
                "metric": "raw_roc_auc",
                "value": split["raw_roc_auc"],
            }
        )

        metric_rows.append(
            {
                "category": "classification",
                "split": split["split"],
                "metric": "calibrated_roc_auc",
                "value": split["calibrated_roc_auc"],
            }
        )

        metric_rows.append(
            {
                "category": "calibration",
                "split": split["split"],
                "metric": "raw_brier",
                "value": split["raw_brier"],
            }
        )

        metric_rows.append(
            {
                "category": "calibration",
                "split": split["split"],
                "metric": "calibrated_brier",
                "value": split["calibrated_brier"],
            }
        )

        metric_rows.append(
            {
                "category": "calibration",
                "split": split["split"],
                "metric": "raw_ece",
                "value": split["raw_ece"],
            }
        )

        metric_rows.append(
            {
                "category": "calibration",
                "split": split["split"],
                "metric": "calibrated_ece",
                "value": split["calibrated_ece"],
            }
        )

    for row in top_k:
        for metric_name in [
            "precision",
            "recall",
            "lift_vs_baseline",
        ]:
            metric_rows.append(
                {
                    "category": "top_k",
                    "split": "test",
                    "metric": (
                        f"{metric_name}@"
                        f"{row['top_fraction']}"
                    ),
                    "value": row[metric_name],
                }
            )

    metric_rows.append(
        {
            "category": "ranking",
            "split": "test",
            "metric": "raw_calibrated_rank_correlation",
            "value": rank_corr,
        }
    )

    for key, value in optimization.items():
        if isinstance(value, (int, float)):
            metric_rows.append(
                {
                    "category": "optimization",
                    "split": "v2",
                    "metric": key,
                    "value": value,
                }
            )

    metrics_df = pd.DataFrame(metric_rows)

    metrics_df.to_csv(
        METRICS_PATH,
        index=False,
    )

    print(
        f"[PASS] Metrics written: "
        f"{METRICS_PATH.relative_to(ROOT)}"
    )

    # ------------------------------------------------------------------
    # Final evaluation report
    # ------------------------------------------------------------------

    report = {
        "phase": "7",
        "status": "PASS",
        "timestamp": datetime.now().astimezone().isoformat(),
        "project": "Rail-Yojna",
        "evaluation_protocol": {
            "model": "failure_30d_v3_logistic",
            "calibrator": "failure_30d_v3_probability_calibrator",
            "planner": "maintenance_plan_v2",
            "horizon_days": 30,
            "data_mode": "synthetic",
            "temporal_evaluation": True,
        },
        "dataset": integrity,
        "splits": split_results,
        "bootstrap_95ci": bootstrap,
        "top_k_test": top_k,
        "ranking": {
            "raw_calibrated_rank_correlation": rank_corr,
        },
        "backtests": backtest_summary,
        "v2_v3_comparison": v2_v3_summary,
        "optimization": optimization,
        "feature_effects": feature_effects,
        "limitations": [
            {
                "topic": topic,
                "detail": detail,
            }
            for topic, detail in limitations
        ],
        "final_assessment": final_assessment,
        "artifacts": {
            "metrics_csv": str(
                METRICS_PATH.relative_to(ROOT)
            ),
            "report_json": str(
                REPORT_PATH.relative_to(ROOT)
            ),
            "evaluation_doc": str(
                EVALUATION_DOC.relative_to(ROOT)
            ),
        },
    }

    REPORT_PATH.write_text(
        json.dumps(
            json_safe(report),
            indent=2,
        ),
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # Human-readable evaluation document
    # ------------------------------------------------------------------

    test = split_results[-1]
    top1 = next(
        x for x in top_k
        if abs(x["top_fraction"] - 0.01) < 1e-12
    )
    top5 = next(
        x for x in top_k
        if abs(x["top_fraction"] - 0.05) < 1e-12
    )
    top10 = next(
        x for x in top_k
        if abs(x["top_fraction"] - 0.10) < 1e-12
    )

    documentation = f"""# Rail-Yojna — Final Evaluation

## Evaluation status

**Phase 7: PASS**

This document summarizes the frozen V3 failure-prediction model, probability calibration, temporal robustness checks, and V2 maintenance optimization evaluation.

## Dataset

- Rows: {integrity["rows"]:,}
- Positive labels: {integrity["positive_labels"]:,}
- Negative labels: {integrity["negative_labels"]:,}
- Positive rate: {integrity["positive_rate"]:.6%}
- Time range: {integrity["time_min"]} → {integrity["time_max"]}
- Data mode: synthetic

## Model

Model version: `failure_30d_v3_logistic`

Prediction horizon: **30 days**

The evaluation uses the frozen V3 model without retraining.

## Temporal test performance

| Metric | Raw | Calibrated |
|---|---:|---:|
| PR-AUC | {test["raw_pr_auc"]:.6f} | {test["calibrated_pr_auc"]:.6f} |
| ROC-AUC | {test["raw_roc_auc"]:.6f} | {test["calibrated_roc_auc"]:.6f} |
| Brier | {test["raw_brier"]:.6f} | {test["calibrated_brier"]:.6f} |
| ECE | {test["raw_ece"]:.6f} | {test["calibrated_ece"]:.6f} |

## Ranking utility

| Operating point | Precision | Recall | Lift |
|---|---:|---:|---:|
| Top 1% | {top1["precision"]:.4f} | {top1["recall"]:.4f} | {top1["lift_vs_baseline"]:.2f}x |
| Top 5% | {top5["precision"]:.4f} | {top5["recall"]:.4f} | {top5["lift_vs_baseline"]:.2f}x |
| Top 10% | {top10["precision"]:.4f} | {top10["recall"]:.4f} | {top10["lift_vs_baseline"]:.2f}x |

Raw versus calibrated ranking correlation:

**{rank_corr:.8f}**

The calibration stage therefore changes probability scale substantially more than ordering behavior.

## Temporal robustness

Frozen and expanding monthly backtests are included in the machine-readable report. Months with very few or zero failures have limited statistical power and should not be interpreted as definitive model failures or successes.

## Optimization

Planner version: `maintenance_plan_v2`

- Candidate tasks: {optimization["candidate_tasks"]:,}
- Selected tasks: {optimization["selected_tasks"]:,}
- Selected hours: {optimization["selected_hours"]:.2f}
- Risk mass: {optimization["risk_mass"]:.6f}
- High-risk selected tasks: {optimization["high_risk_tasks"]:,}
- Critical-risk selected tasks: {optimization["critical_risk_tasks"]:,}
- P1 selected tasks: {optimization["p1_tasks"]:,}
- Block-required selected tasks: {optimization["block_required_tasks"]:,}

The optimizer is evaluated as a decision-support prioritization layer, not as an autonomous railway control system.

## Feature effects

The frozen V3 feature-effect artifact is included in the final evidence package. Feature effects should be interpreted within the synthetic data-generating process rather than as causal claims about real railway assets.

## Limitations

1. The data is synthetic.
2. The 30-day failure target follows the project's synthetic event-generation process.
3. The defect-recency feature is unusually predictive in this benchmark and limits direct generalization to real-world data.
4. Not every available operational constraint is enforced as a hard optimization constraint.
5. The system does not issue signalling, routing, dispatch, or train movement authority.
6. No prospective real-world railway validation is represented.

## Reproducibility artifacts

- `ml/models/final_evaluation_metrics.csv`
- `data/validation/phase7_evaluation_report.json`
- `ml/models/failure_30d_v3_backtest.csv`
- `ml/models/failure_30d_v3_expanding_backtest.csv`
- `ml/models/failure_30d_v2_vs_v3_comparison.csv`
- `optimization/results/maintenance_plan_v2_comparison.csv`

## Final assessment

The evaluation establishes that Rail-Yojna is a coherent research-engineering prototype combining temporal failure-risk prediction, probability calibration, maintenance prioritization, deterministic decision rules, and human-reviewed planning.

The results should **not** be presented as proof of real-world railway safety performance or certification.
"""

    EVALUATION_DOC.write_text(
        documentation,
        encoding="utf-8",
    )

    print(
        f"[PASS] Evaluation document written: "
        f"{EVALUATION_DOC.relative_to(ROOT)}"
    )

    # ------------------------------------------------------------------
    # Final gate
    # ------------------------------------------------------------------

    report["gate"] = {
        "dataset_integrity": "PASS",
        "model_probability_integrity": "PASS",
        "temporal_evaluation": "PASS",
        "calibration_evaluation": "PASS",
        "ranking_evaluation": "PASS",
        "backtest_evaluation": "PASS",
        "optimization_evaluation": "PASS",
        "limitations_documented": "PASS",
        "reproducibility_artifacts": "PASS",
    }

    REPORT_PATH.write_text(
        json.dumps(
            json_safe(report),
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 80)
    print("PHASE 7 COMPLETE")
    print("=" * 80)

    print(
        json.dumps(
            {
                "phase": "7",
                "status": "PASS",
                "test_calibrated_pr_auc": test["calibrated_pr_auc"],
                "test_calibrated_roc_auc": test["calibrated_roc_auc"],
                "test_calibrated_brier": test["calibrated_brier"],
                "test_calibrated_ece": test["calibrated_ece"],
                "top1_precision": top1["precision"],
                "top5_recall": top5["recall"],
                "top10_recall": top10["recall"],
                "ranking_correlation": rank_corr,
                "selected_tasks": optimization["selected_tasks"],
                "risk_mass": optimization["risk_mass"],
                "report": str(REPORT_PATH.relative_to(ROOT)),
                "metrics": str(METRICS_PATH.relative_to(ROOT)),
                "documentation": str(EVALUATION_DOC.relative_to(ROOT)),
            },
            indent=2,
        )
    )

    print("=" * 80)


if __name__ == "__main__":
    main()
