# Rail-Yojna Operational Core

## Purpose

Rail-Yojna is an India-focused railway maintenance decision-support
system.

The system does not autonomously control:

- signalling
- train movements
- interlocking
- block authority
- other safety-vital railway functions

A human railway planner remains responsible for operational approval.

## Decision pipeline

Operational data
        |
        v
Asset state
        |
        +--> ML prediction
        |
        +--> Deterministic railway rules
        |
        v
Risk / recommendation
        |
        v
Constraint-aware planning
        |
        v
Human review
        |
        +--> APPROVE
        +--> MODIFY
        +--> REJECT
        |
        v
Audit trail

## Current limitation

The current repository contains synthetic railway data.

The optimization layer remains a research/simulation planner until
authoritative operational inputs are available:

1. future timetable
2. possession/block availability
3. resource/crew availability
4. approved engineering constraints
5. authoritative asset and maintenance records

Synthetic assumptions must never be presented as actual railway limits.

## ML boundary

ML produces an estimate.

ML does not authorize maintenance, possession, signalling,
or train operation.

## Audit

Prediction requests are stored in:

`data/audit/decision_events.jsonl`
