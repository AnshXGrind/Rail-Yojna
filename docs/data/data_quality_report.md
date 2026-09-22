# Data Quality Report

## Scope

This document records the current research-data validation posture. It describes software/data consistency checks, not railway certification.

## Dataset inventory highlights

| Table | Rows | Purpose |
|---|---:|---|
| `asset_condition_history` | 600,000 | Asset condition time series |
| `assets` | 30,000 | Asset master data |
| `defects` | 78,856 | Defect history |
| `block_requests` | 47,211 | Block request history |
| `blocks` | 13,268 | Historical block records |
| `data_provenance` | 2,751,984 | Record-level provenance |
| `train_movements` | 525,960 | Train movement history |

Additional tables are recorded in `data/metadata/dataset_inventory.json`.

## Validation principles

### Relational consistency

Foreign-key-style relationships are checked where the generator and validation scripts define them.

### Temporal consistency

Events are checked for valid ordering where domain semantics require it. Examples include measurement history, defect detection, maintenance windows, and train movement intervals.

### Leakage prevention

Prediction features are constructed from information available before the model timestamp. Historical counts and elapsed-time features are therefore calculated using prior observations.

### Controlled missingness

Missing values can be used as part of the research scenario, but a missing operational source is not silently treated as a feasible state in the planning layer.

### Provenance

`data_provenance` records whether a record is synthetic or derived and stores generation metadata for reproducibility.

## Known research limitation

The current failure target is strongly associated with newly detected defects in the synthetic generator. Model metrics must therefore be interpreted in the context of this synthetic leading-indicator structure.

## Operational-data limitation

The repository does not contain authoritative railway operational inputs. Train, safety, resource, timetable, and asset records in the research environment should not be represented as actual railway operating data.