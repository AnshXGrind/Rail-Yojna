# Model Card — Failure Risk v3

## Artifacts

- `ml/models/failure_30d_v3_logistic.joblib`
- `ml/models/failure_30d_v3_probability_calibrator.joblib`

## Dataset

- 600,000 rows
- 3,358 positives
- ~0.56% positive rate
- 2022-01-01 through 2025-12-31
- 23 engineered features

## Evaluation

| Metric | Value |
|---|---:|
| Raw PR-AUC | 0.140138 |
| Raw ROC-AUC | 0.962140 |
| Brier before calibration | 0.099655 |
| Brier after calibration | 0.009368 |

These results describe the synthetic research dataset.

## Limitation

Positive cases are strongly associated with newly detected defects in the synthetic generator. The model is therefore currently a synthetic leading-indicator model, not evidence of general real-world failure prediction.

## Intended use

Research, engineering prototyping, maintenance prioritization experiments, and decision-support demonstrations.
