# Development Setup

## Requirements

- Python 3
- Node.js / npm
- Git

## Python dependency profiles

The repository no longer uses a full system-environment freeze as its project dependency file.

Use the profile that matches the task:

### Runtime / application

```bash
python3 -m pip install -r requirements.txt
```

Includes the FastAPI application, data processing, model inference, and optimization runtime dependencies.

### Development and testing

```bash
python3 -m pip install -r requirements-dev.txt
```

Includes the runtime profile plus pytest and code-quality tools.

### ML training and research

```bash
python3 -m pip install -r requirements-ml.txt
```

Adds the model-training, calibration, experiment, and evaluation stack.

### Geospatial/network research

```bash
python3 -m pip install -r requirements-geo.txt
```

Adds NetworkX and geospatial packages.

### Complete research environment

```bash
python3 -m pip install -r requirements-full.txt
```

This installs all project profiles.

## Backend

```bash
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

FastAPI documentation:

```text
http://127.0.0.1:8000/docs
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

## Validation

```bash
python3 -m compileall -q backend
npm --prefix frontend run build
python3 -m pytest -q
```

Use `.env.example` as a starting point. Do not commit secrets.
