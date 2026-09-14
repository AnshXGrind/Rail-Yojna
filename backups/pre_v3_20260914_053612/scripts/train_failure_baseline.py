from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd

from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data" / "processed" / "failure_30d_features.parquet"
MODEL_DIR = ROOT / "ml" / "models"

MODEL_DIR.mkdir(parents=True, exist_ok=True)


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
]

TARGET = "failure_within_30_days"


def evaluate(name, model, X, y):
    probabilities = model.predict_proba(X)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)

    pr_auc = average_precision_score(y, probabilities)
    roc_auc = roc_auc_score(y, probabilities)

    print("\n" + "=" * 70)
    print(name)
    print("=" * 70)

    print(f"PR-AUC : {pr_auc:.6f}")
    print(f"ROC-AUC: {roc_auc:.6f}")

    print("\nConfusion matrix:")
    print(confusion_matrix(y, predictions))

    print("\nClassification report:")
    print(
        classification_report(
            y,
            predictions,
            digits=4,
            zero_division=0,
        )
    )

    return {
        "model": name,
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
    }


def main():
    print("Loading feature dataset...")

    df = pd.read_parquet(DATA)

    print(f"Rows: {len(df):,}")

    train = df[df["split"] == "train"]
    validation = df[df["split"] == "validation"]
    test = df[df["split"] == "test"]

    X_train = train[FEATURES]
    y_train = train[TARGET]

    X_validation = validation[FEATURES]
    y_validation = validation[TARGET]

    X_test = test[FEATURES]
    y_test = test[TARGET]

    print("\nTarget distribution:")
    print(y_train.value_counts())

    results = []

    # ---------------------------------------------------------
    # Baseline 1: always predict the majority class
    # ---------------------------------------------------------

    dummy = DummyClassifier(
        strategy="most_frequent"
    )

    dummy.fit(X_train, y_train)

    results.append(
        evaluate(
            "Majority Baseline",
            dummy,
            X_test,
            y_test,
        )
    )

    # ---------------------------------------------------------
    # Baseline 2: Logistic Regression
    # ---------------------------------------------------------

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

    model.fit(X_train, y_train)

    results.append(
        evaluate(
            "Logistic Regression",
            model,
            X_test,
            y_test,
        )
    )

    # ---------------------------------------------------------
    # Save model
    # ---------------------------------------------------------

    model_path = MODEL_DIR / "failure_30d_logistic.joblib"

    joblib.dump(
        model,
        model_path,
    )

    print(f"\nModel saved to:")
    print(model_path)

    results_df = pd.DataFrame(results)

    print("\n" + "=" * 70)
    print("MODEL COMPARISON")
    print("=" * 70)

    print(results_df.to_string(index=False))

    results_df.to_csv(
        MODEL_DIR / "baseline_results.csv",
        index=False,
    )


if __name__ == "__main__":
    main()
