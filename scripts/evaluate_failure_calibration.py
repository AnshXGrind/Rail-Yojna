from __future__ import annotations

from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import pandas as pd

from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss


ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data" / "processed" / "failure_30d_features_v2.parquet"
MODEL = ROOT / "ml" / "models" / "failure_30d_v2_logistic.joblib"
OUTPUT = ROOT / "ml" / "models"

df = pd.read_parquet(DATA)

bundle = joblib.load(MODEL)

model = bundle["model"]
features = bundle["features"]

test = df[df["split"] == "test"].copy()

X_test = test[features]
y_test = test["failure_within_30_days"]

probabilities = model.predict_proba(X_test)[:, 1]

brier = brier_score_loss(
    y_test,
    probabilities,
)

print("=" * 70)
print("CALIBRATION")
print("=" * 70)

print(f"Brier score: {brier:.6f}")

fraction_positive, mean_predicted = calibration_curve(
    y_test,
    probabilities,
    n_bins=10,
    strategy="quantile",
)

calibration = pd.DataFrame({
    "mean_predicted_probability": mean_predicted,
    "observed_failure_rate": fraction_positive,
})

print("\nCalibration table:")
print(calibration.to_string(index=False))

calibration.to_csv(
    OUTPUT / "failure_calibration.csv",
    index=False,
)

plt.figure(figsize=(7, 7))

plt.plot(
    [0, 1],
    [0, 1],
    linestyle="--",
    label="Perfect calibration",
)

plt.plot(
    mean_predicted,
    fraction_positive,
    marker="o",
    label="V2 Logistic",
)

plt.xlabel("Mean predicted probability")
plt.ylabel("Observed failure rate")
plt.title("Failure Risk Calibration")

plt.legend()
plt.tight_layout()

plot_path = OUTPUT / "failure_calibration.png"

plt.savefig(
    plot_path,
    dpi=150,
)

plt.close()

print("\nSaved:")
print(OUTPUT / "failure_calibration.csv")
print(plot_path)
