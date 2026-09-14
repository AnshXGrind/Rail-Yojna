from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd

from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data" / "processed" / "failure_30d_dataset_v3.parquet"
MODEL_DIR = ROOT / "ml" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

TARGET = "failure_within_30_days"

FEATURES = [
    # Current condition
    "condition_score",
    "degradation_rate",
    "measurement_value",
    "inspection_quality",
    "measurement_confidence",

    # Condition history
    "previous_condition_score",
    "condition_change",
    "days_since_previous_measurement",
    "historical_mean_condition",
    "historical_min_condition",
    "historical_mean_degradation",
    "historical_observation_count",

    # Asset
    "design_life_years",
    "criticality_score",
    "asset_age_days",

    # Defects
    "defect_days_since_last",
    "defect_count_before",

    # Inspections
    "inspection_days_since_last",
    "inspection_count_before",

    # Maintenance
    "maintenance_days_since_last",
    "maintenance_count_before",

    # Previous incidents
    "incident_days_since_last",
    "incident_count_before",
]


def evaluate(model, X, y, name):
    probabilities = model.predict_proba(X)[:, 1]

    return {
        "model": name,
        "pr_auc": average_precision_score(
            y,
            probabilities,
        ),
        "roc_auc": roc_auc_score(
            y,
            probabilities,
        ),
    }


def main():
    print("Loading V3 dataset...")

    df = pd.read_parquet(DATA)

    train = df[df["split"] == "train"]
    validation = df[df["split"] == "validation"]
    test = df[df["split"] == "test"]

    print(f"Train      : {len(train):,}")
    print(f"Validation : {len(validation):,}")
    print(f"Test       : {len(test):,}")

    X_train = train[FEATURES]
    y_train = train[TARGET]

    X_validation = validation[FEATURES]
    y_validation = validation[TARGET]

    X_test = test[FEATURES]
    y_test = test[TARGET]

    model = Pipeline(
        [
            (
                "imputer",
                SimpleImputer(strategy="median"),
            ),
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "classifier",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )

    print("\nTraining V3 Logistic Regression...")

    model.fit(
        X_train,
        y_train,
    )

    validation_result = evaluate(
        model,
        X_validation,
        y_validation,
        "V3 Logistic - validation",
    )

    test_result = evaluate(
        model,
        X_test,
        y_test,
        "V3 Logistic - test",
    )

    print("\n" + "=" * 70)
    print("V3 RESULTS")
    print("=" * 70)

    print(
        f"Validation PR-AUC : "
        f"{validation_result['pr_auc']:.6f}"
    )

    print(
        f"Validation ROC-AUC: "
        f"{validation_result['roc_auc']:.6f}"
    )

    print(
        f"Test PR-AUC       : "
        f"{test_result['pr_auc']:.6f}"
    )

    print(
        f"Test ROC-AUC      : "
        f"{test_result['roc_auc']:.6f}"
    )

    model_path = (
        MODEL_DIR / "failure_30d_v3_logistic.joblib"
    )

    joblib.dump(
        {
            "model": model,
            "features": FEATURES,
        },
        model_path,
    )

    print("\nSaved:")
    print(model_path)

    results = pd.DataFrame(
        [validation_result, test_result]
    )

    results.to_csv(
        MODEL_DIR / "failure_30d_v3_logistic_results.csv",
        index=False,
    )


if __name__ == "__main__":
    main()
