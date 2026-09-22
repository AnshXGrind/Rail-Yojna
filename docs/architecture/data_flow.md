# Data Flow

## End-to-end

```text
Raw research data
      ↓
Validation / preprocessing
      ↓
Temporal feature construction
      ↓
ML inference
      ↓
Calibrated risk
      ↓
Maintenance planning
      ↓
Block candidate generation
      ↓
Train / safety / resource / material assessment
      ↓
Recommendation
      ↓
Human decision
      ↓
Audit event
```

## Data-gap rule

A missing table, missing movement coverage, unmapped safety rule, or unjoinable resource record is reported as `DATA_GAP`, not silently converted to `PASS`.
