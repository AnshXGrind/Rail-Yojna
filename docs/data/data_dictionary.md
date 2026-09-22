# Rail-Yojna Data Dictionary

## Data mode

The repository uses a **synthetic research dataset**. It is intended for development, testing, ML experiments, optimization experiments, and demonstrations. It is not official railway operational data.

The generated inventory is recorded in [`data/metadata/dataset_inventory.json`](../../data/metadata/dataset_inventory.json).

## Core entities

| Table | Role | Key fields |
|---|---|---|
| `assets` | Physical railway assets | `asset_id`, `asset_type`, `track_id`, `section_id`, `station_id`, `installation_date`, `design_life_years`, `criticality_score` |
| `asset_condition_history` | Time-series asset measurements | `measurement_id`, `asset_id`, `timestamp`, `condition_score`, `degradation_rate`, `measurement_value`, inspection-quality fields |
| `defects` | Detected asset defects | `defect_id`, `asset_id`, `section_id`, `detected_timestamp`, `defect_type`, `severity`, `priority` |
| `inspections` | Inspection history | `asset_id`, inspection dates/method/quality fields |
| `maintenance_tasks` | Planned maintenance work | `task_id`, `asset_id`, `section_id`, `track_id`, `task_type`, `priority`, `criticality`, time-window fields, duration, block requirements |
| `maintenance_execution` | Execution history | task identity, execution timestamps, status and actual-duration fields |
| `block_requests` | Maintenance block requests | `request_id`, `task_id`, `section_id`, `track_id`, requested window, priority, decision, approved window |
| `blocks` | Historical block records | `block_id`, `request_id`, `section_id`, `track_id`, planned/actual windows, duration, protection/isolation flags, status |
| `train_movements` | Train movement intervals | `movement_id`, `train_id`, date, section, track, scheduled/actual entry and exit |
| `trains` | Train master data | `train_id`, train number/type/service, priority, origin/destination, timetable and capacity fields |
| `train_delays` | Delay observations | train/movement identity, delay metrics and timestamps |
| `resources` | Resource master data | resource identity, type and operational attributes |
| `resource_availability` | Resource availability windows | resource identity, date, available start/end and status |
| `machines` | Maintenance machine inventory | machine identity and operational attributes |
| `materials` | Maintenance material inventory | material identity, quantities and properties |
| `task_resources` | Task/resource mapping | task and resource identifiers plus assignment attributes |
| `task_materials` | Task/material mapping | task and material identifiers plus quantities |
| `safety_constraints` | Deterministic safety rules | jurisdiction, ruleset, category/code, minimum duration, clearance, isolation/protection and personnel requirements |
| `data_provenance` | Record-level provenance | table, record, source type/name, generation method, quality and synthetic/derived flags |

## Important temporal relationships

Rail-Yojna uses event timing as a first-class modelling concern. Examples include:

```text
asset installation
      ↓
condition measurements
      ↓
defect / inspection
      ↓
maintenance task
      ↓
block request
      ↓
planned / actual block
      ↓
train interaction / delay
```

Prediction features are constructed using information available before the prediction timestamp.

## ML feature contract

The current failure-risk model uses 23 features. The authoritative feature order is stored with the model artifact and documented in [`docs/ml/feature_dictionary.md`](../ml/feature_dictionary.md).

## Synthetic-data rule

Where a field represents a generated railway quantity, its value must not be interpreted as an official railway rule, timetable, engineering limit, or safety authorization.