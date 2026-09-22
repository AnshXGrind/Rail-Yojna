# Optimization Evaluation

## Current maintenance-plan artifact

The versioned planning result contains:

- 51,316 total candidate task rows
- 1,421 eligible candidates
- 1,314 selected tasks
- 107 eligible tasks deferred by optimization

## Baseline comparison

The repository includes three planning views for comparison:

1. chronological selection baseline
2. risk-only selection baseline
3. Rail-Yojna optimization

The comparison is intended to distinguish the effect of simply selecting high-risk tasks from the effect of the planning objective and constraints.

## Current reference results

| Plan | Tasks | Risk-mass / purpose |
|---|---:|---|
| Chronological baseline | 1,244 | reference selection order |
| Risk-only baseline | 1,242 | 123.490945 risk mass |
| Rail-Yojna V2 | 1,314 | 124.002413 risk mass |

Historical reference risk mass for the chronological comparison is 114.518506.

## Critical planning note

These results do not mean every selected task has passed complete operational validation. Candidate generation, operational assessment, safety evaluation, and resource/material assessment are separate stages.

## Current date limitation

The selected optimized maintenance-plan tasks are concentrated in the available 2026 planning horizon. Historical validation is therefore performed independently using historical maintenance tasks and train movements.

## Future evaluation

Future experiments should report:

- task count
- critical-task coverage
- risk mass
- deferred tasks
- resource utilization
- block utilization
- train conflicts
- safety data gaps
- material/resource conflicts
- runtime
- sensitivity to capacity and objective weights