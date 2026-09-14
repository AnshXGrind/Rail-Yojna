from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from joblib import load

from ml.inference.feature_builder import FeatureBuilder


ROOT = Path(__file__).resolve().parents[2]

MODEL_PATH = (
    ROOT /
    "ml/models/failure_30d_v3_logistic.joblib"
)

CALIBRATOR_PATH = (
    ROOT /
    "ml/models/failure_30d_v3_probability_calibrator.joblib"
)


@lru_cache(maxsize=1)
def load_artifacts():
    artifact = load(MODEL_PATH)
    calibrator = load(CALIBRATOR_PATH)
    feature_builder = FeatureBuilder()

    expected_features = artifact["features"]

    return (
        artifact["model"],
        expected_features,
        calibrator,
        feature_builder,
    )


def predict(
    *,
    asset_id: str,
    timestamp,
    condition_score: float,
    degradation_rate: float,
    measurement_value: float,
    inspection_quality: float,
    measurement_confidence: float,
) -> dict:

    (
        model,
        expected_features,
        calibrator,
        feature_builder,
    ) = load_artifacts()

    features = feature_builder.build(
        asset_id=asset_id,
        timestamp=timestamp,
        condition_score=condition_score,
        degradation_rate=degradation_rate,
        measurement_value=measurement_value,
        inspection_quality=inspection_quality,
        measurement_confidence=measurement_confidence,
    )

    if list(features.columns) != list(expected_features):
        raise RuntimeError(
            "Inference feature order does not match the "
            "trained V3 model."
        )

    raw_probability = float(
        model.predict_proba(features)[0, 1]
    )

    # The calibration model was trained on the logit-transformed
    # raw probability, not on the raw probability itself.
    clipped_probability = np.clip(
        raw_probability,
        1e-15,
        1 - 1e-15,
    )

    raw_logit = np.log(
        clipped_probability / (1.0 - clipped_probability)
    )

    calibrated_probability = float(
        calibrator.predict_proba(
            np.array([[raw_logit]])
        )[0, 1]
    )

    return {
        "asset_id": asset_id,
        "timestamp": str(timestamp),
        "raw_probability": raw_probability,
        "risk_probability": calibrated_probability,
        "prediction_horizon_days": 30,
        "model_version": "failure_30d_v3_logistic",
        "calibration": "platt_sigmoid",
        "data_mode": "synthetic",
    }
