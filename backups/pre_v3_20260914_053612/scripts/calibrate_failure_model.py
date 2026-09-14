from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.calibration import calibration_curve


ROOT = Path(__file__).resolve().parents[1]

DATA = (
    ROOT
    / "data"
    / "processed"
    / "failure_30d_features_v2.parquet"
)

MODEL = (
    ROOT
    / "ml"
    / "models"
    / "failure_30d_v2_logistic.joblib"
)

OUTPUT = ROOT / "ml" / "models"


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-8, 1 - 1e-8)
    return np.log(p / (1 - p))


def main():

    df = pd.read_parquet(DATA)

    bundle = joblib.load(MODEL)

    model = bundle["model"]
    features = bundle["features"]

    train = df[df["split"] == "train"]
    validation = df[df["split"] == "validation"]
    test = df[df["split"] == "test"]

    # ---------------------------------------------------------
    # Generate raw model probabilities
    # ---------------------------------------------------------

    validation_raw = model.predict_proba(
        validation[features]
    )[:, 1]

    test_raw = model.predict_proba(
        test[features]
    )[:, 1]

    y_validation = validation[
        "failure_within_30_days"
    ].to_numpy()

    y_test = test[
        "failure_within_30_days"
    ].to_numpy()

    # ---------------------------------------------------------
    # Fit sigmoid calibrator on VALIDATION only
    # ---------------------------------------------------------

    calibrator = LogisticRegression(
        C=1.0,
        solver="lbfgs",
        max_iter=1000,
    )

    calibrator.fit(
        logit(validation_raw).reshape(-1, 1),
        y_validation,
    )

    # ---------------------------------------------------------
    # Apply calibrator
    # ---------------------------------------------------------

    validation_calibrated = calibrator.predict_proba(
        logit(validation_raw).reshape(-1, 1)
    )[:, 1]

    test_calibrated = calibrator.predict_proba(
        logit(test_raw).reshape(-1, 1)
    )[:, 1]

    # ---------------------------------------------------------
    # Metrics
    # ---------------------------------------------------------

    raw_pr_auc = average_precision_score(
        y_test,
        test_raw,
    )

    calibrated_pr_auc = average_precision_score(
        y_test,
        test_calibrated,
    )

    raw_roc_auc = roc_auc_score(
        y_test,
        test_raw,
    )

    calibrated_roc_auc = roc_auc_score(
        y_test,
        test_calibrated,
    )

    raw_brier = brier_score_loss(
        y_test,
        test_raw,
    )

    calibrated_brier = brier_score_loss(
        y_test,
        test_calibrated,
    )

    print("=" * 80)
    print("CALIBRATED FAILURE MODEL")
    print("=" * 80)

    print()
    print("TEST METRICS")
    print()

    print(
        f"Raw PR-AUC        : {raw_pr_auc:.6f}"
    )

    print(
        f"Calibrated PR-AUC : {calibrated_pr_auc:.6f}"
    )

    print(
        f"Raw ROC-AUC       : {raw_roc_auc:.6f}"
    )

    print(
        f"Calibrated ROC-AUC: {calibrated_roc_auc:.6f}"
    )

    print(
        f"Raw Brier         : {raw_brier:.6f}"
    )

    print(
        f"Calibrated Brier  : {calibrated_brier:.6f}"
    )

    # ---------------------------------------------------------
    # Calibration table
    # ---------------------------------------------------------

    fraction_positive, mean_predicted = calibration_curve(
        y_test,
        test_calibrated,
        n_bins=10,
        strategy="quantile",
    )

    calibration = pd.DataFrame({
        "mean_predicted_probability": mean_predicted,
        "observed_failure_rate": fraction_positive,
    })

    print()
    print("CALIBRATION TABLE")
    print()
    print(
        calibration.to_string(index=False)
    )

    # ---------------------------------------------------------
    # Save calibrator
    # ---------------------------------------------------------

    calibrator_path = (
        OUTPUT
        / "failure_30d_probability_calibrator.joblib"
    )

    joblib.dump(
        calibrator,
        calibrator_path,
    )

    calibration.to_csv(
        OUTPUT
        / "failure_30d_calibrated_test.csv",
        index=False,
    )

    print()
    print("Saved:")
    print(calibrator_path)


if __name__ == "__main__":
    main()
