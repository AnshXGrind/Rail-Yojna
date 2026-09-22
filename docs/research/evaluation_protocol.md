# Evaluation Protocol

## ML

Use time-aware validation where prediction timing requires it. Report PR-AUC, ROC-AUC, calibration, Brier score, class balance, and leakage checks.

## Planning

Compare documented baselines such as chronological and risk-only selection against constraint-aware planning. Report task count, risk mass, deferred tasks, utilization, conflicts, data gaps, and runtime.

## Historical validation

Use source maintenance and train-movement records to reproduce known conflicts and available windows.

## Reproducibility

Record dataset version, model version, planner version, configuration, seeds where applicable, exact command, and environment information.
