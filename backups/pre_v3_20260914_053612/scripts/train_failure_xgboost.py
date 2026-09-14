from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
import xgboost as xgb

from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    precision_recall_curve,
)

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


def evaluate(model, X, y):
    probability = model.predict_proba(X)[:, 1]

    return {
        "pr_auc": average_precision_score(
            y,
            probability,
        ),
        "roc_auc": roc_auc_score(
            y,
            probability,
        ),
    }


def main():
    df = pd.read_parquet(DATA)

    train = df[df["split"] == "train"]
    validation = df[df["split"] == "validation"]
    test = df[df["split"] == "test"]

    X_train = train[FEATURES]
    y_train = train[TARGET]

    X_validation = validation[FEATURES]
    y_validation = validation[TARGET]

    X_test = test[FEATURES]
    y_test = test[TARGET]

    imputer = SimpleImputer(strategy="median")

    X_train = imputer.fit_transform(X_train)
    X_validation = imputer.transform(X_validation)
    X_test = imputer.transform(X_test)

    positive = y_train.sum()
    negative = len(y_train) - positive

    scale_pos_weight = negative / positive

    model = xgb.XGBClassifier(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="aucpr",
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        n_jobs=-1,
    )

    print("Training XGBoost...")

    model.fit(
        X_train,
        y_train,
        eval_set=[
            (X_validation, y_validation),
        ],
        verbose=False,
    )

    validation_metrics = evaluate(
        model,
        X_validation,
        y_validation,
    )

    test_metrics = evaluate(
        model,
        X_test,
        y_test,
    )

    print()
    print("=" * 70)
    print("XGBOOST RESULTS")
    print("=" * 70)

    print(
        f"Validation PR-AUC : "
        f"{validation_metrics['pr_auc']:.6f}"
    )

    print(
        f"Validation ROC-AUC: "
        f"{validation_metrics['roc_auc']:.6f}"
    )

    print(
        f"Test PR-AUC       : "
        f"{test_metrics['pr_auc']:.6f}"
    )

    print(
        f"Test ROC-AUC      : "
        f"{test_metrics['roc_auc']:.6f}"
    )

    model_path = (
        MODEL_DIR
        / "failure_30d_xgboost.joblib"
    )

    joblib.dump(
        {
            "model": model,
            "imputer": imputer,
            "features": FEATURES,
        },
        model_path,
    )

    print()
    print("Saved:")
    print(model_path)

    importance = pd.DataFrame({
        "feature": FEATURES,
        "importance": model.feature_importances_,
    }).sort_values(
        "importance",
        ascending=False,
    )

    print()
    print("FEATURE IMPORTANCE")
    print(importance.to_string(index=False))

    importance.to_csv(
        MODEL_DIR / "xgboost_feature_importance.csv",
        index=False,
    )


if __name__ == "__main__":
    main()
