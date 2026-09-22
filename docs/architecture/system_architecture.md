# System Architecture

## Scope

Rail-Yojna connects railway data, machine learning, maintenance planning, operational assessment, safety constraints, resources, and human review.

## Component flow

```text
Railway Data → Validation → ML / Risk
                         ↘ Planning Data
                              ↓
                     Block Candidates
                              ↓
               Train + Safety + Resources
                              ↓
                    Unified Assessment
                              ↓
                     Recommendation
                              ↓
                      Human Planner
                              ↓
                           Audit
```

## Principles

1. ML output is advisory.
2. Safety constraints are deterministic.
3. Missing operational information remains visible as a data gap.
4. Component assessments remain independently inspectable.
5. Human review is required before a planning decision is recorded.
6. Synthetic research data is explicitly separated from authoritative railway data.

## Backend

FastAPI exposes domain services for risk, planning, blocks, operational assessment, resources, recommendations, decisions, reports, and audit.

## Frontend

The React Control Room presents risk, maintenance, block candidates, assessments, alternative windows, and human decision controls. It does not grant operational authority.

## Extension points

Future work includes richer network conflict propagation, scenario simulation, authoritative timetable integration, multi-resource optimization, and GIS visualization.
