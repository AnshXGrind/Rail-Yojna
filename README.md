# Rail-Yojna

**AI-Assisted Railway Maintenance and Block-Planning Decision Support System**

Rail-Yojna is a research and engineering project focused on improving railway maintenance planning by combining railway infrastructure data, machine learning, optimization, simulation, and deterministic safety constraints.

The system is designed to help railway planners answer questions such as:

* Which assets or sections require maintenance attention?
* Which maintenance activities should receive higher priority?
* When is a suitable maintenance window available?
* How will a proposed maintenance block affect train operations?
* Which combination of maintenance tasks, resources, and time windows produces a better plan?
* Does a proposed plan satisfy all defined safety and operational constraints?

Rail-Yojna is designed as a **decision-support system**. It does not autonomously control railway signalling, train movement authority, or other safety-critical railway systems.

---

## Project Status

**Current stage:** Infrastructure and dataset development

The project is currently being developed in stages:

1. Project and software infrastructure
2. Railway dataset generation and validation
3. Data ingestion and quality analysis
4. Feature engineering
5. Machine-learning models
6. Maintenance and risk prediction
7. Block-planning optimization
8. Simulation and scenario testing
9. Safety validation
10. Backend API
11. Planner dashboard
12. End-to-end integration and evaluation

The large synthetic research dataset is being generated separately and will be integrated after its schema, relationships, temporal consistency, and data quality have been validated.

---

## Core Idea

Rail-Yojna combines several components instead of treating railway maintenance as only an ML problem.

```text
                    RAIL-YOJNA
                         |
        +----------------+----------------+
        |                                 |
  Railway Data                      Railway Rules
        |                                 |
        +----------------+----------------+
                         |
                  Data Foundation
                         |
                 Risk / Prediction
                         |
                 Planning Engine
                         |
              Simulation / Validation
                         |
                Safety Validation
                         |
                 Recommendation
                         |
                 Human Planner
```

The system follows the principle:

> **AI proposes, deterministic constraints validate, and an authorized human makes the final planning decision.**

---

# Objectives

The main objectives of Rail-Yojna are:

### 1. Maintenance Prioritization

Use historical asset condition, inspections, defects, failures, maintenance history, and related operational information to estimate maintenance priorities and risks.

### 2. Maintenance Prediction

Where sufficient historical data exists, develop models for problems such as:

* asset failure risk
* maintenance requirement
* expected maintenance duration
* block overrun probability
* operational delay impact

The exact prediction targets will be determined from the validated dataset rather than assumed in advance.

### 3. Block Planning

Determine suitable maintenance windows while considering:

* railway topology
* train movements
* timetable constraints
* maintenance duration
* available resources
* track occupancy
* operational conflicts
* safety constraints

### 4. Scenario Simulation

Allow planners to evaluate alternative scenarios before selecting a plan.

For example:

```text
Scenario A
Maintenance: 08:00-10:00
Affected trains: 4

Scenario B
Maintenance: 11:00-13:00
Affected trains: 1

Scenario C
Maintenance: 14:00-15:30
Affected trains: 0
```

The system can compare the resulting operational consequences and constraints.

### 5. Explainable Decision Support

A recommendation should provide reasons and relevant information rather than only returning a numerical score.

---

# Safety Philosophy

Railway systems are safety-critical.

Rail-Yojna therefore separates **prediction and optimization** from **safety validation**.

```text
                 ML Model
                    |
                    v
              Optimization
                    |
                    v
            Candidate Plan
                    |
                    v
            Safety Validator
               /        \
              /          \
          VALID          INVALID
            |               |
            v               v
      Recommendation       Reject
            |
            v
      Human Planner
```

Safety constraints are treated as **hard constraints**, not simply as weighted objectives.

Rail-Yojna is not intended to directly control:

* railway signalling
* interlocking systems
* train movement authority
* automatic route setting
* safety-critical field equipment

The project is intended for research and decision-support purposes.

---

# Architecture

```text
                         RAIL-YOJNA
                              |
        +---------------------+---------------------+
        |                     |                     |
        v                     v                     v
   Data Layer              ML Layer          Optimization Layer
        |                     |                     |
        |              Risk / Prediction       Scheduling
        |              Feature Engineering    Resource Allocation
        |              Model Evaluation        Block Planning
        |                     |                     |
        +---------------------+---------------------+
                              |
                              v
                      Simulation Layer
                              |
                              v
                     Safety Validator
                              |
                              v
                       Decision Engine
                              |
                              v
                         FastAPI
                              |
                              v
                         Dashboard
```

---

# Railway Domain Model

The project is being designed around connected railway entities rather than a single flat dataset.

Core entities include:

```text
Network
   |
Stations
   |
Track Sections
   |
Tracks
   |
Assets
   |
Condition History
   |
Defects
   |
Maintenance Tasks
   |
Block Requests
   |
Blocks
   |
Train Movements
   |
Delays
   |
Resources
   |
Weather
   |
Incidents
```

The temporal relationship between these entities is particularly important.

For example:

```text
Asset condition decreases
        |
        v
Defect detected
        |
        v
Maintenance requested
        |
        v
Block planning
        |
        +----------+
        |          |
        v          v
    Block      Block denied
    granted         |
        |           v
        |       Condition worsens
        |           |
        +-----------+
                    |
                    v
              Failure / Incident
                    |
                    v
              Emergency block
                    |
                    v
               Train delay
```

This temporal structure is important for both machine learning and planning.

---

# Dataset

Rail-Yojna uses a large relational research dataset rather than a single flat CSV file.

The dataset is intended to contain interconnected information covering areas such as:

* railway infrastructure
* stations and track sections
* assets
* inspections
* asset condition
* defects
* maintenance activities
* maintenance execution
* block requests
* granted and actual blocks
* train schedules and movements
* delays
* resources and availability
* machines
* weather
* incidents
* emergency maintenance
* costs
* materials
* railway constraints
* signalling
* planning decisions
* timetable versions
* block-plan versions
* traffic demand
* data provenance

The dataset is being generated as **synthetic research data** and will be explicitly identified as such.

Synthetic data will not be treated as proof of real-world railway performance.

---

# Data Principles

The dataset and subsequent processing follow several principles:

### Relational consistency

Records should reference valid entities through foreign keys.

### Temporal consistency

Events should occur in realistic chronological order.

For example:

```text
defect_detected <= maintenance_start <= maintenance_end
```

where applicable.

### Causal relationships

Important events should not be generated as completely independent random rows.

For example:

```text
asset degradation
        ↓
defect probability
        ↓
maintenance requirement
        ↓
block request
        ↓
planning outcome
        ↓
operational consequence
```

### No target leakage

Features used for prediction must not contain information that would only become available after the prediction point.

### Controlled imperfections

Real-world data is imperfect. The research dataset may therefore contain controlled missing values, measurement noise, and other data-quality challenges, while preserving known ground truth where necessary for validation.

---

# Machine Learning

Machine learning will be used where the available data supports a meaningful prediction problem.

Possible tasks include:

```text
Asset data
    ↓
Feature engineering
    ↓
ML model
    ↓
Risk / prediction
```

Potential models include:

* baseline statistical models
* linear models
* tree-based models
* gradient boosting
* XGBoost
* LightGBM
* CatBoost

More complex models will only be introduced when justified by the problem and dataset.

Model evaluation will use appropriate temporal validation rather than relying only on random train/test splitting when the problem requires time-aware evaluation.

---

# Optimization

The optimization layer addresses the planning question:

> **What maintenance should be performed, where, when, and with which available resources while satisfying the required constraints?**

A simplified objective may combine:

```text
Maintenance risk
+ train disruption
+ maintenance cost
+ resource inefficiency
```

subject to hard constraints such as:

```text
Safety
Track availability
Train conflicts
Resource availability
Maintenance duration
Operational rules
Isolation requirements
Precedence relationships
```

The optimization layer is expected to use constraint programming and operations-research techniques, with OR-Tools being a primary candidate for the prototype.

---

# Simulation

Simulation will be used to test candidate planning decisions under different scenarios.

Example:

```text
Current railway state
        |
        +---- Maintenance Plan A
        |
        +---- Maintenance Plan B
        |
        +---- Maintenance Plan C
```

Each scenario can be evaluated for:

* affected trains
* expected delays
* maintenance completion
* resource utilization
* block utilization
* conflicts
* constraint violations
* operational impact

The goal is to compare plans before they are considered for real-world execution.

---

# Technology Stack

### Backend

* Python
* FastAPI
* Pydantic
* SQLAlchemy
* PostgreSQL

### Data Engineering

* Pandas
* Polars
* NumPy
* PyArrow
* SciPy

### Machine Learning

* Scikit-learn
* XGBoost
* LightGBM
* CatBoost
* Optuna

### Optimization

* OR-Tools

### Simulation / Network Modelling

* NetworkX
* GeoPandas
* Shapely

### Visualization

* Matplotlib
* Seaborn
* Plotly

### Experiment Tracking / Evaluation

* MLflow
* Evidently

### Testing and Code Quality

* Pytest
* Ruff
* Black
* MyPy
* Pre-commit

---

# Repository Structure

```text
Rail-Yojna/
│
├── backend/
│   └── app/
│       ├── api/
│       ├── core/
│       ├── models/
│       ├── schemas/
│       ├── services/
│       └── main.py
│
├── ml/
│   ├── data/
│   ├── features/
│   ├── models/
│   ├── training/
│   └── inference/
│
├── optimization/
│   ├── models/
│   ├── constraints/
│   ├── solvers/
│   └── scenarios/
│
├── data/
│   ├── raw/
│   ├── processed/
│   ├── metadata/
│   └── validation/
│
├── notebooks/
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── docs/
│
├── scripts/
│
├── .env.example
├── requirements.txt
└── README.md
```

---

# Development Roadmap

## Phase 1 — Infrastructure

* [x] Repository initialized
* [x] Development branches created
* [x] Python dependency stack established
* [ ] Backend skeleton
* [ ] Configuration system
* [ ] Logging
* [ ] Testing framework
* [ ] Database layer

## Phase 2 — Dataset

* [ ] Generate large synthetic dataset
* [ ] Validate schema
* [ ] Validate foreign-key relationships
* [ ] Validate timestamps
* [ ] Check missingness
* [ ] Check duplicates
* [ ] Detect impossible values
* [ ] Generate data dictionary
* [ ] Generate relationship documentation
* [ ] Produce data-quality report

## Phase 3 — Data Pipeline

* [ ] Data ingestion
* [ ] Cleaning
* [ ] Validation
* [ ] Feature engineering
* [ ] Temporal dataset construction
* [ ] Train/validation/test splits

## Phase 4 — Machine Learning

* [ ] Define prediction targets
* [ ] Establish baselines
* [ ] Train candidate models
* [ ] Evaluate models
* [ ] Compare models
* [ ] Model versioning
* [ ] Inference pipeline

## Phase 5 — Optimization

* [ ] Railway topology model
* [ ] Maintenance task model
* [ ] Resource model
* [ ] Train conflict model
* [ ] Hard safety constraints
* [ ] Block-planning solver
* [ ] Objective function
* [ ] Scenario comparison

## Phase 6 — Simulation

* [ ] Scenario generation
* [ ] Schedule simulation
* [ ] Delay propagation
* [ ] Resource simulation
* [ ] Maintenance execution simulation
* [ ] Plan comparison

## Phase 7 — Safety and Decision Support

* [ ] Safety validation layer
* [ ] Constraint violation reporting
* [ ] Recommendation explanations
* [ ] Audit logging
* [ ] Human approval workflow

## Phase 8 — Application

* [ ] FastAPI endpoints
* [ ] Planner dashboard
* [ ] Railway network visualization
* [ ] Asset view
* [ ] Maintenance planning view
* [ ] Block planning view
* [ ] Scenario comparison

## Phase 9 — Evaluation

* [ ] End-to-end testing
* [ ] Model evaluation
* [ ] Optimization evaluation
* [ ] Simulation validation
* [ ] Performance testing
* [ ] Reproducibility testing
* [ ] Documentation

---

# Research Direction

The project is intended to investigate how machine learning and operations research can work together in railway maintenance planning.

The central pipeline is:

```text
Historical Railway Data
          ↓
     ML / Statistics
          ↓
   Risk & Predictions
          ↓
     Optimization
          ↓
    Candidate Plan
          ↓
   Safety Validation
          ↓
 Human Decision Support
```

The objective is not to replace railway planners.

The objective is to provide planners with better information about:

* maintenance urgency
* operational conflicts
* available maintenance windows
* resource requirements
* expected disruption
* alternative plans
* constraint violations

---

# Reproducibility

Experiments should use:

* deterministic random seeds where appropriate
* versioned datasets
* versioned models
* documented configuration
* reproducible preprocessing
* recorded experiment parameters
* testable pipelines

Synthetic datasets should retain their generation configuration and seed so that experiments can be reproduced.

---

# Dataset and Research Disclaimer

The initial development dataset is synthetic and intended for research, software development, testing, and experimentation.

It should not be interpreted as official railway operational data or as an accurate representation of any railway operator's confidential systems, infrastructure, timetable, or safety procedures.

Any real-world deployment would require validation against authoritative railway standards, operational procedures, infrastructure data, safety systems, and regulatory requirements.

---

# Contributors

Rail-Yojna is being developed collaboratively.

Current development branches:

```text
main
 ├── ansh
 ├── hardik
 ├── sujal
 └── arjun
```

`ansh` is currently the primary development branch.

The `main` branch is intended to remain the clean/stable base branch.

---

# License

License information will be added as the project reaches its initial public-release stage.

