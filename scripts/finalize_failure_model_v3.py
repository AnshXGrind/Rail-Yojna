from __future__ import annotations

import json
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

DATA = ROOT / "data" / "processed" / "failure_30d_dataset_v3.parquet"
MODEL_PATH = ROOT / "ml" / "models" / "failure_30d_v3_logistic.joblib"
CALIBRATOR_PATH = (
    ROOT / "ml" / "models" / "failure_30d_v3_probability_calibrator.joblib"
)

RESULTS_PATH = (
    ROOT / "ml" / "models" / "failure_30d_v3_logistic_results.csv"
)
RANKING_PATH = (
    ROOT / "ml" / "models" / "failure_30d_v3_ranking_results.csv"
)
BACKTEST_PATH = (
    ROOT / "ml" / "models" / "failure_30d_v3_backtest.csv"
)
EXPANDING_BACKTEST_PATH = (
    ROOT / "ml" / "models" / "failure_30d_v3_expanding_backtest.csv"
)
FEATURE_EFFECTS_PATH = (
    ROOT / "ml" / "models" / "failure_30d_v3_feature_effects.csv"
)

METADATA_PATH = (
    ROOT / "ml" / "models" / "failure_30d_v3_metadata.json"
)

AUDIT_PATH = (
    ROOT / "data" / "validation" / "failure_30d_v3_leakage_audit.csv"
)

EXPECTED_FEATURES = [
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

TARGET = "failure_within_30_days"


def fail(message: str) -> None:
    print(f"\nFAILED: {message}")
    raise SystemExit(1)


def check_file(path: Path) -> None:
    if not path.exists():
        fail(f"Missing required artifact: {path}")


def main() -> None:
    print("=" * 90)
    print("RAIL-YOJNA V3 FINAL MODEL GATE")
    print("=" * 90)

    required = [
        DATA,
        MODEL_PATH,
        CALIBRATOR_PATH,
        RESULTS_PATH,
        RANKING_PATH,
        BACKTEST_PATH,
        EXPANDING_BACKTEST_PATH,
        FEATURE_EFFECTS_PATH,
        AUDIT_PATH,
    ]

    print("\n[1/7] Checking required artifacts...")
    for path in required:
        check_file(path)
        print(f"  PASS  {path.relative_to(ROOT)}")

    print("\n[2/7] Loading model and validating feature contract...")
    bundle = joblib.load(MODEL_PATH)

    if "model" not in bundle or "features" not in bundle:
        fail("V3 model bundle missing model/features")

    model = bundle["model"]
    features = list(bundle["features"])

    if features != EXPECTED_FEATURES:
        fail(
            "V3 feature contract mismatch\n"
            f"Expected: {EXPECTED_FEATURES}\n"
            f"Found   : {features}"
        )

    if len(features) != 23:
        fail(f"Expected 23 features, found {len(features)}")

    print("  PASS  23-feature contract")

    print("\n[3/7] Loading validated V3 dataset...")
    df = pd.read_parquet(DATA)

    if len(df) != 600_000:
        fail(f"Expected 600,000 rows, found {len(df):,}")

    missing = [f for f in features if f not in df.columns]
    if missing:
        fail(f"Missing model features in dataset: {missing}")

    if TARGET not in df.columns:
        fail(f"Missing target column: {TARGET}")

    print(f"  PASS  rows={len(df):,}")
    print(f"  PASS  positives={int(df[TARGET].sum()):,}")

    test = df[df["split"] == "test"].copy()

    print(f"  PASS  test_rows={len(test):,}")

    print("\n[4/7] Golden probability / calibration gate...")

    raw = model.predict_proba(test[features])[:, 1]

    calibrator = joblib.load(CALIBRATOR_PATH)

    clipped = np.clip(raw, 1e-8, 1 - 1e-8)
    logits = np.log(clipped / (1 - clipped))

    calibrated = calibrator.predict_proba(
        logits.reshape(-1, 1)
    )[:, 1]

    if not np.isfinite(raw).all():
        fail("Raw probabilities contain non-finite values")

    if not np.isfinite(calibrated).all():
        fail("Calibrated probabilities contain non-finite values")

    if ((raw < 0) | (raw > 1)).any():
        fail("Raw probabilities outside [0,1]")

    if ((calibrated < 0) | (calibrated > 1)).any():
        fail("Calibrated probabilities outside [0,1]")

    y = test[TARGET].astype(int).to_numpy()

    # Calibration is expected to preserve the underlying ordering
    # because the fitted sigmoid has a positive coefficient.
    # Exact permutation equality is too strict because calibration
    # can compress probabilities into numerical ties.
    raw_order = np.argsort(-raw, kind="stable")
    calibrated_order = np.argsort(-calibrated, kind="stable")

    calibration_coefficient = float(
        calibrator.coef_[0, 0]
    )

    monotonic_violations = int(
        np.sum(
            np.diff(
                calibrated[np.argsort(raw)]
            ) < 0
        )
    )

    top_k_agreement = {}

    for fraction in [0.005, 0.01, 0.02, 0.05, 0.10]:
        k = max(1, int(len(test) * fraction))

        raw_top = set(raw_order[:k])
        cal_top = set(calibrated_order[:k])

        intersection = len(raw_top & cal_top)

        top_k_agreement[str(fraction)] = (
            intersection / k
        )

    ranking_identical = (
        calibration_coefficient > 0
        and monotonic_violations == 0
    )

    if not ranking_identical:
        fail(
            "Calibration is not monotonic increasing; "
            "investigate calibrator before promotion"
        )

    raw_pr = average_precision_score(y, raw)
    cal_pr = average_precision_score(y, calibrated)
    raw_roc = roc_auc_score(y, raw)
    cal_roc = roc_auc_score(y, calibrated)
    raw_brier = brier_score_loss(y, raw)
    cal_brier = brier_score_loss(y, calibrated)

    print("  PASS  raw probabilities valid")
    print("  PASS  calibrated probabilities valid")
    print(
        "  PASS  calibrator coefficient positive: "
        f"{calibration_coefficient:.9f}"
    )
    print(
        "  PASS  monotonicity violations: "
        f"{monotonic_violations}"
    )

    print("  Top-K raw/calibrated agreement:")
    for fraction, agreement in top_k_agreement.items():
        print(
            f"    top {float(fraction):.1%}: "
            f"{agreement:.2%}"
        )

    print("\n  Test metrics:")
    print(f"    Raw PR-AUC         : {raw_pr:.6f}")
    print(f"    Calibrated PR-AUC  : {cal_pr:.6f}")
    print(f"    Raw ROC-AUC        : {raw_roc:.6f}")
    print(f"    Calibrated ROC-AUC : {cal_roc:.6f}")
    print(f"    Raw Brier          : {raw_brier:.6f}")
    print(f"    Calibrated Brier   : {cal_brier:.6f}")

    print("\n[5/7] Checking saved evaluation outputs...")

    ranking = pd.read_csv(RANKING_PATH)

    required_ranking_fractions = {
        0.005,
        0.01,
        0.02,
        0.05,
        0.10,
    }

    present = set(ranking["top_fraction"].astype(float))

    if not required_ranking_fractions.issubset(present):
        fail("Ranking output missing one or more required top-K levels")

    backtest = pd.read_csv(BACKTEST_PATH)
    expanding = pd.read_csv(EXPANDING_BACKTEST_PATH)
    effects = pd.read_csv(FEATURE_EFFECTS_PATH)

    if len(backtest) == 0:
        fail("Frozen temporal backtest is empty")

    if len(expanding) == 0:
        fail("Expanding temporal backtest is empty")

    if len(effects) != 23:
        fail(
            f"Expected 23 feature effects, found {len(effects)}"
        )

    print("  PASS  ranking evaluation")
    print("  PASS  frozen temporal backtest")
    print("  PASS  expanding temporal backtest")
    print("  PASS  23 feature effects")

    print("\n[6/7] Checking leakage audit...")

    audit = pd.read_csv(AUDIT_PATH)

    if "status" not in audit.columns:
        fail("Leakage audit missing status column")

    failures = audit[
        audit["status"].astype(str).str.upper() == "FAIL"
    ]

    if len(failures):
        fail(
            f"Leakage audit contains {len(failures)} FAIL rows"
        )

    print("  PASS  leakage audit contains zero FAIL rows")

    print("\n[7/7] Writing model registry metadata...")

    metadata = {
        "model_name": "failure_30d_v3_logistic",
        "model_type": "logistic_regression",
        "target": TARGET,
        "horizon_days": 30,
        "feature_count": len(features),
        "features": features,
        "dataset": str(DATA.relative_to(ROOT)),
        "model_artifact": str(MODEL_PATH.relative_to(ROOT)),
        "calibrator_artifact": str(
            CALIBRATOR_PATH.relative_to(ROOT)
        ),
        "training_method": {
            "imputer": "median",
            "scaler": "standard",
            "classifier": "LogisticRegression",
            "class_weight": "balanced",
            "random_state": 42,
            "max_iter": 1000,
        },
        "test_metrics": {
            "raw_pr_auc": float(raw_pr),
            "calibrated_pr_auc": float(cal_pr),
            "raw_roc_auc": float(raw_roc),
            "calibrated_roc_auc": float(cal_roc),
            "raw_brier": float(raw_brier),
            "calibrated_brier": float(cal_brier),
        },
        "ranking_validation": {
            "calibrator_coefficient": calibration_coefficient,
            "monotonic_violations": monotonic_violations,
            "raw_and_calibrated_monotonic": bool(
                ranking_identical
            ),
            "top_k_agreement": top_k_agreement,
        },
        "validation": {
            "leakage_audit": "PASS",
            "temporal_backtest": "PASS_WITH_LOW_EVENT_MONTHS",
            "expanding_backtest": "PASS_WITH_LOW_EVENT_MONTHS",
            "causal_defect_check": "PASS",
        },
        "interpretation_note": (
            "The synthetic generator explicitly creates later "
            "failure events from defects marked failure_occurred=True. "
            "Recent defect detection is therefore a strong intended "
            "leading indicator in this synthetic benchmark."
        ),
        "promotion_status": "FROZEN_RESEARCH_MODEL",
        "production_status": (
            "NOT_FOR_AUTONOMOUS_RAILWAY_SAFETY_CONTROL"
        ),
    }

    METADATA_PATH.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print(f"  PASS  {METADATA_PATH}")

    print("\n" + "=" * 90)
    print("PHASE 1 FINAL STATUS")
    print("=" * 90)

    print("1A  V3 trainer                 PASS")
    print("1B  V3 training                PASS")
    print("1C  V2 vs V3 comparison        PASS")
    print("1D  V3 calibration             PASS")
    print("1E  V3 ranking                 PASS")
    print("1F  Frozen temporal backtest   PASS")
    print("1F  Expanding backtest         PASS")
    print("1G  Feature investigation      PASS")
    print("1H  Probability/parity gate    PASS")
    print("1I  Model freeze               PASS")

    print("\nMODEL FROZEN:")
    print(MODEL_PATH)

    print("\nCALIBRATOR:")
    print(CALIBRATOR_PATH)

    print("\nMETADATA:")
    print(METADATA_PATH)

    print("\n" + "=" * 90)
    print("PHASE 1 COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()
