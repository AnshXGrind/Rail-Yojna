# Rail-Yojna Release Demo

## Local runtime

Start the backend:

```bash
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```bash
npm --prefix frontend run dev
```

The dataset and model artifacts are expected to be present locally.

## Presentation flow

1. Open **Control Room**.
2. Show the asset risk watchlist and maintenance queue.
3. Open **Block Planning**.
4. Select a candidate block and show:
   - maintenance bundle
   - safety assessment
   - train conflict / operational assessment
   - resource and material assessment
   - alternative windows
   - human-review decision controls.
5. Record **Modify**, **Reject**, or **Approve** as the planner decision.
6. Open **Reports** and create or inspect a field report.
7. Open **Service** for the affected asset and show service history.

The approval action is a human planning decision. It does not issue railway block authority, signalling instructions, dispatch authority, or train movement control.

## API evidence

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/openapi.json
```

The primary planning endpoint used by the block-planning UI is:

```text
GET /api/v1/planning/blocks/{block_id}/optimized-windows
```

## Screenshot capture

The repository includes:

```text
scripts/capture_demo_screenshots.py
```

Install Playwright once:

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

Then run:

```bash
python3 scripts/capture_demo_screenshots.py
```

The script writes:

```text
docs/assets/demo/control-room.png
docs/assets/demo/block-planning.png
docs/assets/demo/reports.png
docs/assets/demo/service.png
```

These files are intentionally generated from the locally running application rather than committed as synthetic/fabricated screenshots.
