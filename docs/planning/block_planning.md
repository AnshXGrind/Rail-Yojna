# Block Planning

## Purpose

Convert maintenance tasks into planner-reviewable block candidates.

## Candidate dimensions

- planned date
- section
- track
- task compatibility
- duration
- maintenance window
- risk
- priority
- criticality

## Important distinction

A candidate-generator `FEASIBLE` status means the candidate is internally usable by that stage. It does **not** mean the block has passed train, safety, resource, or official operational validation.

## Flow

```text
Maintenance tasks → Candidate grouping → Block candidate
→ Operational assessment → Safety assessment
→ Resource/material assessment → Planner review
```
