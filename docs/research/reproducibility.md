# Reproducibility Guide

## Repository version

Use the `release/final-project` branch for the reviewed submission state. The active development branch is `ansh`.

## Environment profiles

```bash
python3 -m pip install -r requirements.txt
```

For full research reproduction:

```bash
python3 -m pip install -r requirements-full.txt
```

## Validation commands

```bash
python3 -m compileall -q backend
npm --prefix frontend run build
python3 -m pytest -q
```

## ML reproduction

Training, calibration, ranking, and dataset-audit scripts are under `scripts/`. Versioned model artifacts are under `ml/models/`.

## Planning reproduction

Optimization configuration is under `optimization/config/`, solver implementations are under `optimization/solvers/`, and comparison/evaluation code is under `optimization/evaluation/`.

## Data

The large railway research dataset is synthetic and is not treated as an authoritative production input. The repository records dataset inventory metadata under `data/metadata/`.

## Reporting rule

Every reported experiment should identify:

- dataset version or generation state
- model version
- planner version
- configuration
- evaluation period
- exact command
- environment profile
- known limitations