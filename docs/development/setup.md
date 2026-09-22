# Development Setup

## Requirements

- Python 3
- Node.js / npm
- Git

## Backend

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
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
