# Decision Engine

## Core principle

```text
AI proposes → Deterministic validation → Human review → Approve / Modify / Reject → Audit
```

## Assessment layers

### Maintenance
Checks task/window consistency.

### Safety
Evaluates applicable deterministic railway safety constraints. Unmapped task types remain a data gap.

### Train occupancy
Evaluates movement intervals relevant to the candidate.

### Resources
Checks joinable resource and machine availability.

### Materials
Checks material requirements where reliable joins exist.

## Non-goals

The decision engine does not authorize possession, operate signals, dispatch trains, set routes, control interlocking, or replace railway procedures.
