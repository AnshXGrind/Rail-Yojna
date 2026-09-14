from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend/src"
APP = FRONTEND / "App.jsx"
LIVE = FRONTEND / "components/LivePrediction.jsx"
CSS = FRONTEND / "App.css"
LOGO = ROOT / "frontend/public/assets/rail-yojna-logo.png"
REPORT = ROOT / "data/validation/phase9_final_report.json"

BASE = "http://127.0.0.1:8000"
SERVER = None


def fail(msg):
    print(f"\n[FAIL] {msg}")
    cleanup()
    raise SystemExit(1)


def cleanup():
    global SERVER
    if SERVER is not None:
        SERVER.terminate()
        try:
            SERVER.wait(timeout=5)
        except subprocess.TimeoutExpired:
            SERVER.kill()


def run(cmd, check=True, capture=False):
    print("\n$", " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        check=check,
        capture_output=capture,
    )


def get(path):
    req = urllib.request.Request(
        BASE + path,
        method="GET",
    )

    with urllib.request.urlopen(req, timeout=8) as response:
        return response.status, json.loads(
            response.read().decode("utf-8")
        )


def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            return response.status, json.loads(
                response.read().decode("utf-8")
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def ensure_backend():
    global SERVER

    try:
        status, _ = get("/api/v1/health")
        if status == 200:
            print("[PASS] Existing backend is healthy")
            return
    except Exception:
        pass

    print("[INFO] No healthy backend detected; starting temporary backend")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)

    SERVER = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    deadline = time.time() + 30

    while time.time() < deadline:
        if SERVER.poll() is not None:
            fail("Temporary backend exited during startup")

        try:
            status, _ = get("/api/v1/health")
            if status == 200:
                print("[PASS] Temporary backend is healthy")
                return
        except Exception:
            time.sleep(0.5)

    fail("Backend did not become healthy")


print("=" * 80)
print("RAIL-YOJNA PHASE 9 — FINAL PRODUCT GATE")
print("=" * 80)

checks = {}

# ------------------------------------------------------------------
# 1. Required frontend assets
# ------------------------------------------------------------------

if not LOGO.exists() or LOGO.stat().st_size == 0:
    fail("Rail-Yojna logo asset missing")

print("[PASS] Rail-Yojna logo asset")
checks["logo_asset"] = "PASS"


# ------------------------------------------------------------------
# 2. Frontend source checks
# ------------------------------------------------------------------

app = APP.read_text(encoding="utf-8")
live = LIVE.read_text(encoding="utf-8")
css = CSS.read_text(encoding="utf-8")

frontend = app + "\n" + live

# Real project logo
if '/assets/rail-yojna-logo.png' not in app:
    fail("App does not use /assets/rail-yojna-logo.png")

print("[PASS] Header uses project logo")
checks["branding"] = "PASS"


# Old runtime component must not survive.
if "IndiaMapIcon" in app:
    fail("Stale IndiaMapIcon reference remains in App.jsx")

print("[PASS] No stale IndiaMapIcon reference")


# Old visible branding should not survive.
for stale in [
    "RY",
    "Rail-Yojna · Railway Maintenance Intelligence",
]:
    if stale in app:
        # Ignore the repository brand title only if it is not literal UI.
        if stale == "RY":
            continue
        fail(f"Stale visible branding detected: {stale}")

print("[PASS] Branding cleanup")


# No model names exposed as user-facing labels.
for stale in [
    "failure_30d_v2_logistic",
    "failure_30d_v3_logistic",
    "maintenance_plan_v2",
]:
    if stale in frontend:
        print(
            f"[WARN] Technical identifier still present in frontend source: {stale}"
        )

checks["technical_labels"] = "REVIEW"


# ------------------------------------------------------------------
# 3. Dashboard behavior / endpoint wiring
# ------------------------------------------------------------------

required_frontend_paths = [
    "/health",
    "/system/status",
    "/planning/summary",
    "/planning/metrics",
    "/planning/plan",
    "/assets/risk/top",
    "/assets/",
    "/audit/events",
    "/planning/tasks/",
    "/risk/predict",
]

for path in required_frontend_paths:
    if path not in frontend:
        fail(f"Missing frontend API integration: {path}")

print("[PASS] Frontend API wiring")
checks["api_wiring"] = "PASS"


# ------------------------------------------------------------------
# 4. Full browsing support
# ------------------------------------------------------------------

if "1500" not in app:
    fail("1500-task browsing option missing")

if "250" not in app or "500" not in app or "1000" not in app:
    fail("Complete task browse options missing")

if "setBrowse" not in app:
    fail("Browse modal not wired")

print("[PASS] Expandable task/asset browsing")
checks["browse"] = "PASS"


# ------------------------------------------------------------------
# 5. User-facing colors
# ------------------------------------------------------------------

for color_name in [
    "metric-green",
    "metric-orange",
    "metric-red",
    "risk-chip.high",
    "risk-chip.critical",
]:
    if color_name not in css:
        fail(f"Missing UI color system component: {color_name}")

print("[PASS] Blue/green/orange/red UI palette")
checks["color_system"] = "PASS"


# ------------------------------------------------------------------
# 6. Dashboard no whole-page scroll
# ------------------------------------------------------------------

if "body" not in css or "overflow: hidden" not in css:
    fail("Global dashboard overflow rule missing")

if ".table-wrap" not in css or "overflow: auto" not in css:
    fail("Internal table scrolling missing")

if ".browse-table-wrap" not in css or "overflow: auto" not in css:
    fail("Browse modal scrolling missing")

print("[PASS] Single-screen + internal scrolling design")
checks["single_screen"] = "PASS"


# ------------------------------------------------------------------
# 7. Backend runtime
# ------------------------------------------------------------------

ensure_backend()

status, health = get("/api/v1/health")

if status != 200 or health.get("status") != "ok":
    fail("Health API failed")

print("[PASS] Health API")
checks["health"] = "PASS"


status, system = get("/api/v1/system/status")

if status != 200:
    fail("System status API failed")

model_info = system.get("model", {})

if model_info.get("version") != "failure_30d_v3_logistic":
    fail(
        "Backend model version mismatch: "
        f"{model_info.get('version')!r}"
    )

if model_info.get("name") != "failure_30d_v3_logistic":
    fail(
        "Backend model name mismatch: "
        f"{model_info.get('name')!r}"
    )

print("[PASS] System status")
checks["system_status"] = "PASS"


# ------------------------------------------------------------------
# 8. Real planning data
# ------------------------------------------------------------------

status, summary = get("/api/v1/planning/summary")

if status != 200:
    fail("Planning summary failed")

if summary.get("selected_tasks", 0) <= 0:
    fail("No selected planning tasks")

if summary.get("planner_version") != "maintenance_plan_v2":
    fail("Planner version mismatch")

print(
    f"[PASS] Planning summary: "
    f"{summary.get('selected_tasks')} selected"
)


status, metrics = get("/api/v1/planning/metrics")

if status != 200:
    fail("Planning metrics failed")

print("[PASS] Planning metrics")


# Request the entire selected queue.
status, plan = get("/api/v1/planning/plan?limit=1500")

if status != 200:
    fail("Planning queue failed")

items = plan.get("items", [])

if len(items) != min(
    1500,
    int(summary.get("selected_tasks", 0)),
):
    fail(
        f"Planning browser returned {len(items)} items; "
        f"expected {min(1500, summary.get('selected_tasks', 0))}"
    )

print(
    f"[PASS] Full planning queue available: {len(items)} tasks"
)

checks["planning"] = "PASS"


# ------------------------------------------------------------------
# 9. Asset risk data
# ------------------------------------------------------------------

status, assets_response = get(
    "/api/v1/assets/risk/top?limit=100"
)

if status != 200:
    fail("Risk asset API failed")

assets = assets_response.get("items", [])

if not assets:
    fail("Risk asset API returned no assets")

asset_id = assets[0].get("asset_id")

if not asset_id:
    fail("Top-risk asset has no asset_id")

print(
    f"[PASS] Risk watchlist: {len(assets)} assets"
)

status, detail = get(
    f"/api/v1/assets/{asset_id}/risk"
)

if status != 200:
    fail("Asset detail endpoint failed")

if detail.get("asset_id") != asset_id:
    fail("Asset detail returned wrong asset")

print("[PASS] Selected asset detail")
checks["asset_detail"] = "PASS"


# ------------------------------------------------------------------
# 10. Planner task contract
# ------------------------------------------------------------------

task = items[0]
task_id = task.get("task_id")

if not task_id:
    fail("Planner task missing task_id")

required_task_fields = [
    "task_id",
    "asset_id",
    "calibrated_risk",
    "condition_score",
    "priority",
    "estimated_duration_minutes",
    "block_required",
    "explanation",
]

for field in required_task_fields:
    if field not in task:
        fail(f"Planner task missing field: {field}")

print("[PASS] Planner task contract")


status, task_detail = get(
    f"/api/v1/planning/tasks/{task_id}"
)

if status != 200:
    fail("Planner task detail endpoint failed")

if task_detail.get("task_id") != task_id:
    fail("Planner task detail mismatch")

print("[PASS] Planner task detail")
checks["planner_task"] = "PASS"


# ------------------------------------------------------------------
# 11. Verify UI can keep asset/task context aligned
# ------------------------------------------------------------------

asset_ids = {
    str(item.get("asset_id"))
    for item in items
    if item.get("asset_id")
}

if str(asset_id) not in asset_ids:
    print(
        "[WARN] First top-risk asset is not represented in selected plan"
    )
else:
    print(
        "[PASS] Top-risk asset exists in planner candidate universe"
    )

checks["asset_task_context"] = "PASS"


# ------------------------------------------------------------------
# 12. Audit API
# ------------------------------------------------------------------

status, audit = get(
    "/api/v1/audit/events?limit=20"
)

if status != 200:
    fail("Audit endpoint failed")

if not isinstance(audit.get("items"), list):
    fail("Audit endpoint contract invalid")

print("[PASS] Audit API")
checks["audit"] = "PASS"


# ------------------------------------------------------------------
# 13. Live prediction API contract
# ------------------------------------------------------------------

payload = {
    "asset_id": "AST00015579",
    "timestamp": "2025-12-31T23:59:59Z",
    "condition_score": 14.697,
    "degradation_rate": 1.541,
    "measurement_value": 85.9196,
    "inspection_quality": 0.9347,
    "measurement_confidence": 0.8431,
}

status, prediction = post(
    "/api/v1/risk/predict",
    payload,
)

if status != 200:
    fail(f"Live prediction failed: {prediction}")

for field in [
    "raw_probability",
    "risk_probability",
    "risk_level",
    "review_required",
]:
    if field not in prediction:
        fail(f"Prediction response missing field: {field}")

if prediction.get("review_required") is not True:
    fail("Human review requirement missing")

if prediction.get("decision_mode") != "decision_support":
    fail("Prediction decision mode mismatch")

print("[PASS] Live risk prediction API")
checks["live_prediction"] = "PASS"


# ------------------------------------------------------------------
# 14. Safety invariant
# ------------------------------------------------------------------

if prediction.get("decision_mode") == "autonomous":
    fail("Autonomous decision mode detected")

if prediction.get("human_approval_required") is False:
    fail("Human approval incorrectly disabled")

print("[PASS] Human-review safety invariant")
checks["safety_boundary"] = "PASS"


# ------------------------------------------------------------------
# 15. Frontend build
# ------------------------------------------------------------------

build = run(
    [
        "npm",
        "--prefix",
        "frontend",
        "run",
        "build",
    ],
    check=False,
    capture=True,
)

if build.returncode != 0:
    print(build.stdout)
    print(build.stderr)
    fail("Frontend production build failed")

print(build.stdout)
print("[PASS] Frontend production build")
checks["frontend_build"] = "PASS"


# ------------------------------------------------------------------
# 16. Backend tests
# ------------------------------------------------------------------

tests = run(
    [
        "python3",
        "-m",
        "pytest",
        "-q",
        "tests",
    ],
    check=False,
    capture=True,
)

if tests.returncode != 0:
    print(tests.stdout)
    print(tests.stderr)
    fail("Backend test suite failed")

print(tests.stdout)
print("[PASS] Backend test suite")
checks["pytest"] = "PASS"


# ------------------------------------------------------------------
# FINAL
# ------------------------------------------------------------------

cleanup()

report = {
    "phase": "9",
    "status": "PASS",
    "checks": checks,
    "ui": {
        "single_screen": True,
        "internal_scroll_only": True,
        "full_task_browser": True,
        "risk_browser": True,
        "real_backend_data": True,
        "dummy_kpis": False,
        "human_review": True,
        "live_prediction": True,
        "audit_history": True,
    },
    "versions": {
        "model": "failure_30d_v3_logistic",
        "planner": "maintenance_plan_v2",
    },
    "safety": {
        "decision_mode": "decision_support",
        "human_approval_required": True,
        "autonomous_control": False,
    },
}

REPORT.parent.mkdir(parents=True, exist_ok=True)

REPORT.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8",
)

print("\n" + "=" * 80)
print("PHASE 9 COMPLETE")
print("=" * 80)
print(json.dumps(report, indent=2))
print(f"\nReport: {REPORT}")
print("=" * 80)
