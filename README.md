# Rail-Yojna 🚆

> **AI-assisted railway maintenance and block-planning decision support for explainable, constraint-aware planning.**

Rail-Yojna is an end-to-end research and engineering prototype for **railway asset risk assessment, maintenance planning, block planning, operational assessment, and human-reviewed decision support**.

```text
Asset condition → Risk prediction → Maintenance task
                         ↓
                 Block candidate
                         ↓
          Train / safety / resource assessment
                         ↓
              Explainable recommendation
                         ↓
                   Human planner
                  /      |      \
             APPROVE   MODIFY   REJECT
                         ↓
                     Audit trail
```

> **Safety boundary:** Rail-Yojna is a decision-support prototype. It does not autonomously control signalling, interlocking, train movement, route setting, dispatch, or block authority.

## What is implemented

| Area | Current capability |
|---|---|
| Railway data | Relational synthetic research dataset |
| ML | 30-day asset failure-risk inference |
| Calibration | Calibrated probability output |
| Maintenance planning | Versioned maintenance-plan artifact |
| Block planning | Same-track candidate block generation |
| Operations | Train occupancy and maintenance-window assessment |
| Safety | Deterministic safety-rule evaluation |
| Resources | Resource, crew, machine, and material assessment where source data permits |
| Recommendations | Explainable block recommendation service |
| Decisions | Human approve / modify / reject workflow |
| Audit | Prediction/decision event logging |
| Backend | FastAPI |
| Frontend | React planner-oriented Control Room |
| Validation | Unit, integration, and end-to-end tests |

## Why this project

Railway maintenance planning is not only a machine-learning problem. A useful planning workflow must combine asset condition, inspection and defect history, maintenance urgency, train occupancy, maintenance windows, task duration, resource availability, materials, deterministic safety constraints, operational conflicts, and planner decisions.

Rail-Yojna therefore treats **ML as one layer in a larger engineering system**, rather than allowing a model probability to become an operational decision.

## System architecture

```text
                    Railway Data
                         ↓
              Validation / preprocessing
                         ↓
           ┌─────────────┴─────────────┐
           ↓                           ↓
      ML / Risk                  Planning Data
           ↓                           ↓
      Calibrated Risk          Maintenance Plan
           └─────────────┬─────────────┘
                         ↓
                Block Candidate Gen.
                         ↓
            ┌────────────┼────────────┐
            ↓            ↓            ↓
         Trains        Safety      Resources
            └────────────┼────────────┘
                         ↓
                 Unified Assessment
                         ↓
                  Recommendation
                         ↓
                    Human Planner
                         ↓
                      Audit
```

See [`docs/architecture/operational_core.md`](docs/architecture/operational_core.md) and the expanded documentation under [`docs/`](docs/).

## ML component

The current production inference flow uses a versioned **30-day failure-risk** pipeline.

- **Rows:** 600,000
- **Positive events:** 3,358
- **Positive rate:** ~0.56%
- **Coverage:** 2022-01-01 → 2025-12-31
- **Engineered features:** 23
- **Model:** versioned logistic-regression pipeline
- **Calibration:** versioned probability calibrator

### Evaluation artifacts

| Metric | Result |
|---|---:|
| Raw PR-AUC | 0.1401 |
| Raw ROC-AUC | 0.9621 |
| Brier before calibration | 0.0997 |
| Brier after calibration | 0.0094 |

These are **synthetic research-data results**, not evidence of real-world railway model performance.

### Model limitation

The current synthetic positive class is strongly associated with newly detected defects. The model should therefore be interpreted as a synthetic leading-indicator model conditional on the available defect/condition signal, not as evidence of general real-world failure forecasting.

## Planning and block candidates

The current planning artifact contains:

- **51,316** candidate task rows
- **1,421** eligible candidates
- **1,314** selected tasks
- **107** eligible tasks deferred by optimization

Candidate blocks group compatible tasks using date, section, track, duration, risk, priority, criticality, and maintenance-window information.

Candidate-generation feasibility is deliberately distinct from operational clearance.

## Operational assessment

Candidate blocks can be assessed against:

### Train occupancy
- section and track movement coverage
- occupied intervals
- maintenance duration
- candidate windows

### Safety
- minimum block duration
- minimum clearance
- required isolation/protection
- required personnel

### Resources
- task-resource mappings
- crew/personnel
- machine availability
- material availability
- availability windows

### Independent component states

```text
Maintenance   PASS / INFEASIBLE
Safety        PASS / DATA_GAP / REVIEW
Train         PASS / CONFLICT / DATA_GAP
Resources     PASS / CONFLICT / DATA_GAP
Materials     PASS / CONFLICT / DATA_GAP
```

A data gap is not silently converted to a pass.

## Historical validation

The project independently validates historical maintenance/train relationships. A reproduced case is:

```text
Task:       TASK00000010
Date:       2023-01-21
Section:    SEC00000254
Track:      TRK00000449
Duration:   213 minutes
Train:      TRAIN00001602
Movement:   MOVE00095202
Observed:   train overlap reproduced
```

A full-duration train-free alternative window was also identified from the historical records.

This demonstrates prototype validation against source records rather than relying solely on UI demonstrations.

## Data model

```text
Network
  ↓
Stations / Sections / Tracks
  ↓
Assets
  ↓
Condition / Inspections / Defects
  ↓
Maintenance Tasks
  ↓
Blocks
  ↓
Train Movements / Delays
  ↓
Resources / Machines / Materials
  ↓
Safety Constraints
  ↓
Planning Decisions / Audit
```

The research dataset is synthetic and emphasizes relational consistency, temporal consistency, causal structure, leakage prevention, reproducibility, and controlled missingness.

## Repository structure

```text
Rail-Yojna/
├── backend/                 # FastAPI application
├── frontend/                # React planner dashboard
├── ml/                      # ML inference/model artifacts
├── optimization/            # Planning and optimization artifacts
├── railway/                 # Railway-domain modules
├── data/                    # Research data
├── simulation/              # Simulation/scenario layer
├── docs/                    # Architecture and research documentation
├── scripts/                 # Reproducible engineering scripts
├── tests/                   # Unit/integration/E2E tests
├── requirements.txt
├── LICENSE
└── README.md
```

## Local development

### Backend

```bash
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
```

FastAPI docs: `http://127.0.0.1:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Validation

```bash
python3 -m compileall -q backend
npm --prefix frontend run build
python3 -m pytest -q
```

## Dependency profiles

The Python environment is split by purpose rather than storing a full operating-system package snapshot.

| File | Purpose |
|---|---|
| `requirements.txt` | Runtime API, data, inference, and optimization |
| `requirements-dev.txt` | Testing and code-quality tools |
| `requirements-ml.txt` | Training, calibration, and ML research |
| `requirements-geo.txt` | Network/geospatial research |
| `requirements-full.txt` | Complete development/research environment |

For a normal local run:

```bash
python3 -m pip install -r requirements.txt
```

For full reproduction work:

```bash
python3 -m pip install -r requirements-full.txt
```

## Planner workflow

```text
Control Room
    ↓
Risk watchlist
    ↓
Block Planning
    ↓
Date / section / track filters
    ↓
Candidate blocks
    ↓
Train + safety + resource + material assessment
    ↓
Alternative windows
    ↓
Planner decision
    ├── APPROVE
    ├── MODIFY
    └── REJECT
    ↓
Audit event
```

## API areas

| Area | Purpose |
|---|---|
| Health/System | Service and data-mode information |
| Risk | Asset risk prediction and monitoring |
| Planning | Maintenance plan, tasks, metrics |
| Blocks | Candidate generation and assessment |
| Recommendations | Ranked decision support |
| Decisions | Human review actions |
| Audit | Decision/prediction traceability |
| Reports | Problem-report inputs |

The live OpenAPI schema at `/docs` is the authoritative API reference during development.

## Technology stack

- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy, Uvicorn
- **Data:** Pandas, Polars, NumPy, PyArrow, GeoPandas, NetworkX
- **ML:** Scikit-learn, XGBoost, LightGBM, CatBoost, Optuna, MLflow, Evidently
- **Optimization:** OR-Tools
- **Frontend:** React 19, Vite, Leaflet, React Leaflet, Axios
- **Engineering:** Pytest, Ruff, Black, MyPy, Pre-commit

## Documentation map

- [`Operational Core`](docs/architecture/operational_core.md)
- [`System Architecture`](docs/architecture/system_architecture.md)
- [`Data Flow`](docs/architecture/data_flow.md)
- [`Decision Engine`](docs/architecture/decision_engine.md)
- [`Failure Risk Model Card`](docs/ml/model_card.md)
- [`Feature Dictionary`](docs/ml/feature_dictionary.md)
- [`Block Planning`](docs/planning/block_planning.md)
- [`Constraint Model`](docs/planning/constraint_model.md)
- [`Validation Report`](docs/validation/validation_report.md)
- [`API Reference`](docs/api/api_reference.md)
- [`Development Setup`](docs/development/setup.md)
- [`Testing Guide`](docs/development/testing.md)
- [`Evaluation Protocol`](docs/research/evaluation_protocol.md)

## Project status

### Implemented

- [x] Synthetic relational railway data
- [x] Temporal feature engineering
- [x] 30-day failure-risk target
- [x] Calibrated ML inference
- [x] Versioned maintenance-plan artifact
- [x] Block candidate generation
- [x] Train occupancy assessment
- [x] Safety-rule assessment
- [x] Resource/material assessment
- [x] Unified block assessment
- [x] Recommendation engine
- [x] Human approve/modify/reject audit flow
- [x] FastAPI backend
- [x] React Control Room
- [x] Historical validation
- [x] Automated tests

### In active development

- [ ] Resource-aware alternative-window optimization
- [ ] Expanded historical validation suite
- [ ] Scenario simulation / digital-twin layer
- [ ] Planner-grade network/GIS visualization
- [ ] Expanded model cards and evaluation reports
- [ ] CI/CD and reproducible deployment

### Future research

- authoritative timetable/possession integration
- network-level conflict propagation
- delay-impact simulation
- multi-resource optimization
- uncertainty-aware planning
- scenario comparison and robustness analysis

## Research and deployment limitations

Rail-Yojna is a **research and decision-support prototype**.

It is not an operational railway authority system, signalling/interlocking controller, train-dispatch system, or replacement for railway safety procedures.

Real deployment would require authoritative infrastructure and operating data, formal safety/security processes, verification and validation, railway-domain review, and approval by the relevant organization.

## Academic / placement positioning

Rail-Yojna demonstrates a complete engineering chain:

**Machine Learning** — risk prediction and probability calibration  
**Data Engineering** — relational, temporal synthetic railway data and validation  
**Operations Research** — maintenance grouping, block planning, and constraint-aware assessment  
**Backend Engineering** — FastAPI services, modular domain logic, APIs, and audit events  
**Frontend Engineering** — planner-oriented React Control Room  
**Decision Science** — explainable alternatives with explicit human approval  
**Validation** — unit/integration/E2E testing plus historical conflict reproduction

## License

See [`LICENSE`](LICENSE).

## Project

**Rail-Yojna**  
*AI-Assisted Railway Maintenance & Block-Planning Decision Support System*  
Repository: `AnshXGrind/Rail-Yojna`