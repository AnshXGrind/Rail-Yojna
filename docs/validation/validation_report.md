# Validation Report

## Automated validation

The repository contains unit, integration, and end-to-end tests covering block assessment, recommendations, safety mapping, and historical joins.

```bash
python3 -m compileall -q backend
npm --prefix frontend run build
python3 -m pytest -q
```

## Historical validation

Known reproduced case: `TASK00000010`, 2023-01-21, `SEC00000254`, `TRK00000449`, `TRAIN00001602`, `MOVE00095202`, 213-minute maintenance duration, with a reproduced train overlap and an identified full-duration alternative window.

## Interpretation

Because the dataset is synthetic, validation demonstrates software/data consistency and prototype behavior; it is not railway certification or evidence of operational safety.
