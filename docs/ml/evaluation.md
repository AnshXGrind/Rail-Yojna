# ML Evaluation — Failure Risk v3

## Dataset

- Rows: 600,000
- Positive events: 3,358
- Positive rate: 0.5597%
- Coverage: 2022-01-01 to 2025-12-31
- Features: 23

## Evaluation

| Metric | Result |
|---|---:|
| Raw PR-AUC | 0.140138 |
| Raw ROC-AUC | 0.962140 |
| Brier score before calibration | 0.099655 |
| Brier score after calibration | 0.009368 |

## Interpretation

PR-AUC is particularly relevant because the positive class is highly imbalanced. ROC-AUC describes ranking discrimination, while the Brier score reflects probabilistic accuracy/calibration.

Calibration reduced the reported Brier score substantially on the evaluation data.

## Important limitation

All positive examples in the current synthetic target are associated with a newly detected defect signal. The current model therefore behaves as a synthetic leading-indicator model and should not be described as a general real-world railway failure predictor.

## Risk thresholds

```text
< 0.05        LOW
0.05–< 0.20   MEDIUM
0.20–< 0.50   HIGH
≥ 0.50        CRITICAL
```

## Reproduction

The main evaluation/training scripts are under `scripts/` and the versioned artifacts are under `ml/models/`. The exact dataset/model versions should be recorded with each future experiment.