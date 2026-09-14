from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "data" / "validation"
REPORT_PATH = REPORT_DIR / "phase5_report.json"
BACKUP = ROOT / "data" / "backups" / f"phase5_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
BASE = "http://127.0.0.1:8000"

BACKEND_PROCESS: subprocess.Popen[str] | None = None


def run(cmd: list[str], *, check: bool = True, capture: bool = False):
    print("\n$", " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=check,
        text=True,
        capture_output=capture,
    )


def fail(message: str):
    print(f"\n[FAIL] {message}")
    if BACKEND_PROCESS is not None:
        BACKEND_PROCESS.terminate()
        try:
            BACKEND_PROCESS.wait(timeout=5)
        except subprocess.TimeoutExpired:
            BACKEND_PROCESS.kill()
    print(f"[REPORT] {REPORT_PATH}")
    raise SystemExit(1)


def api(
    method: str,
    path: str,
    payload: dict | None = None,
    timeout: float = 10,
):
    url = BASE + path

    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = raw

            return response.status, body

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")

        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw

        return exc.code, body


def expect_status(
    method: str,
    path: str,
    expected: int,
    payload: dict | None = None,
):
    status, body = api(method, path, payload)

    if status != expected:
        fail(
            f"{method} {path}: expected {expected}, "
            f"got {status}: {body}"
        )

    print(f"[PASS] {method} {path} -> {status}")
    return body


def assert_true(condition: bool, message: str):
    if not condition:
        fail(message)
    print(f"[PASS] {message}")


def start_backend():
    global BACKEND_PROCESS

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)

    BACKEND_PROCESS = subprocess.Popen(
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

    print("[INFO] Starting temporary backend...")

    deadline = time.time() + 30

    while time.time() < deadline:
        if BACKEND_PROCESS.poll() is not None:
            fail("Backend terminated during startup")

        try:
            status, _ = api("GET", "/api/v1/health", timeout=2)
            if status == 200:
                print("[PASS] Backend became healthy")
                return
        except Exception:
            pass

        time.sleep(0.5)

    fail("Backend did not become healthy within 30 seconds")


def stop_backend():
    global BACKEND_PROCESS

    if BACKEND_PROCESS is None:
        return

    BACKEND_PROCESS.terminate()

    try:
        BACKEND_PROCESS.wait(timeout=5)
    except subprocess.TimeoutExpired:
        BACKEND_PROCESS.kill()
        BACKEND_PROCESS.wait(timeout=5)

    print("[INFO] Temporary backend stopped")


def compile_backend():
    targets = [
        ROOT / "backend",
        ROOT / "ml",
        ROOT / "optimization",
    ]

    for target in targets:
        if target.exists():
            files = [str(p) for p in target.rglob("*.py")]
            if files:
                run([sys.executable, "-m", "py_compile", *files])

    print("[PASS] Python syntax compilation")


def run_tests():
    result = run(
        [sys.executable, "-m", "pytest", "-q", "tests"],
        check=False,
        capture=True,
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        fail("Backend/integration test suite failed")

    print(result.stdout)
    print("[PASS] Full pytest suite")


def build_frontend():
    result = run(
        ["npm", "--prefix", "frontend", "run", "build"],
        check=False,
        capture=True,
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        fail("Frontend production build failed")

    print(result.stdout)
    print("[PASS] Frontend production build")


def check_artifacts():
    artifacts = {
        "phase3_plan": ROOT / "optimization/results/maintenance_plan_v2.parquet",
        "v3_model": ROOT / "ml/models/failure_30d_v3_logistic.joblib",
        "calibrator": ROOT / "ml/models/failure_30d_v3_probability_calibrator.joblib",
        "phase4_report": ROOT / "data/validation/phase4_report.json",
    }

    for name, path in artifacts.items():
        assert_true(
            path.exists() and path.stat().st_size > 0,
            f"{name}: {path.relative_to(ROOT)}",
        )


def check_stale_v1_references():
    # V1 remains as a historical optimization baseline.
    # Only active runtime references are considered stale.
    runtime_roots = [
        ROOT / "backend",
        ROOT / "ml",
        ROOT / "frontend" / "src",
        ROOT / "railway",
        ROOT / "optimization" / "solvers",
        ROOT / "scripts",
    ]

    allowed_historical = {
        "optimization/evaluation/compare_v1.py",
        "optimization/config/maintenance_v1.yaml",
    }

    matches = []

    for base in runtime_roots:
        if not base.exists():
            continue

        for path in base.rglob("*"):
            if not path.is_file():
                continue

            # The Phase 5 audit script necessarily contains the literal
            # maintenance_plan_v1 string that it searches for.
            if path.resolve() == (ROOT / "scripts/run_phase5.py").resolve():
                continue

            rel = path.relative_to(ROOT)
            rel_str = str(rel)

            if rel_str in allowed_historical:
                continue

            if path.suffix not in {
                ".py",
                ".yaml",
                ".yml",
                ".json",
                ".md",
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                ".txt",
            }:
                continue

            try:
                text = path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
            except Exception:
                continue

            for line_no, line in enumerate(text.splitlines(), 1):
                if "maintenance_plan_v1" not in line:
                    continue

                lowered = rel_str.lower()

                if any(token in lowered for token in [
                    "compare_v1",
                    "maintenance_v1",
                    "historical",
                    "comparison",
                    "backtest",
                    "report",
                    "readme",
                    "docs",
                ]):
                    continue

                matches.append(
                    f"{rel_str}:{line_no}: {line.strip()}"
                )

    assert_true(
        not matches,
        "No stale maintenance_plan_v1 runtime references remain",
    )

    if matches:
        print("[INFO] Active V1 references found:")
        for item in matches:
            print("  ", item)


def check_api():
    health = expect_status("GET", "/api/v1/health", 200)

    assert_true(
        health.get("status") == "ok",
        "Health status is ok",
    )

    system = expect_status("GET", "/api/v1/system/status", 200)

    assert_true(
        system.get("model_version") == "failure_30d_v3_logistic",
        "System reports V3 model",
    )

    assert_true(
        system.get("calibration") in {
            "logistic_probability_calibration",
            "calibrated",
            "calibrated_probability",
            None,
        },
        "System calibration field is valid",
    )

    summary = expect_status(
        "GET",
        "/api/v1/planning/summary",
        200,
    )

    assert_true(
        summary.get("planner_version") == "maintenance_plan_v2",
        "Planning summary reports V2 planner",
    )

    metrics = expect_status(
        "GET",
        "/api/v1/planning/metrics",
        200,
    )

    assert_true(
        metrics.get("planner_version") == "maintenance_plan_v2",
        "Planning metrics report V2 planner",
    )

    plan = expect_status(
        "GET",
        "/api/v1/planning/plan?limit=5",
        200,
    )

    items = plan.get("items")

    assert_true(
        isinstance(items, list),
        "Planning endpoint returns items list",
    )

    assert_true(
        len(items) > 0,
        "Planning endpoint returns selected tasks",
    )

    task = items[0]

    required_task_keys = {
        "task_id",
        "asset_id",
        "calibrated_risk",
        "condition_score",
        "degradation_rate",
        "priority",
        "criticality",
        "estimated_duration_minutes",
        "block_required",
        "explanation",
    }

    assert_true(
        required_task_keys.issubset(task.keys()),
        "Planning task contract contains required fields",
    )

    explanation = task["explanation"]

    assert_true(
        isinstance(explanation, dict),
        "Task explanation is structured",
    )

    assert_true(
        bool(explanation.get("reasons")),
        "Task explanation contains reasons",
    )

    task_id = str(task["task_id"])
    asset_id = str(task["asset_id"])

    detail = expect_status(
        "GET",
        f"/api/v1/planning/tasks/{task_id}",
        200,
    )

    assert_true(
        str(detail.get("task_id")) == task_id,
        "Planning task detail resolves the selected task",
    )

    risk = expect_status(
        "GET",
        f"/api/v1/assets/{asset_id}/risk",
        200,
    )

    assert_true(
        risk.get("asset_id") == asset_id,
        "Risk endpoint resolves planner asset",
    )

    # Negative route check.
    expect_status(
        "GET",
        "/api/v1/planning/tasks/__phase5_missing_task__",
        404,
    )

    # Audit must be readable before the new decision.
    before = expect_status(
        "GET",
        "/api/v1/audit/events?limit=20",
        200,
    )

    assert_true(
        isinstance(before.get("items"), list),
        "Audit endpoint returns an items list",
    )

    # Real human-decision workflow.
    decision = expect_status(
        "POST",
        f"/api/v1/planning/tasks/{task_id}/decision",
        200,
        {
            "decision": "approve",
            "actor": "phase5_integration_test",
            "note": "Phase 5 end-to-end integration verification",
        },
    )

    assert_true(
        decision.get("decision") == "approve",
        "Planner approve decision recorded",
    )

    assert_true(
        decision.get("human_approval_required") is True,
        "Human approval remains mandatory",
    )

    assert_true(
        decision.get("decision_mode") == "decision_support",
        "Decision mode remains decision_support",
    )

    after = expect_status(
        "GET",
        "/api/v1/audit/events?limit=50&event_type=PLANNING_APPROVED",
        200,
    )

    approval_events = after.get("items", [])

    assert_true(
        any(
            e.get("recommendation_id") == task_id
            for e in approval_events
        ),
        "Approval is persisted in audit history",
    )

    # Invalid decision must be rejected by Pydantic validation.
    status, body = api(
        "POST",
        f"/api/v1/planning/tasks/{task_id}/decision",
        {
            "decision": "autonomous_execute",
            "actor": "phase5_integration_test",
            "note": "must be rejected",
        },
    )

    assert_true(
        status in {400, 422},
        "Invalid planner decision is rejected",
    )


def main():
    print("=" * 80)
    print("RAIL-YOJNA PHASE 5 — RUNTIME + INTEGRATION VERIFICATION")
    print("=" * 80)

    BACKUP.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Phase 5 backup directory: {BACKUP}")

    result = {
        "phase": "5",
        "status": "PASS",
        "checks": {},
        "planner_version": "maintenance_plan_v2",
        "model_version": "failure_30d_v3_logistic",
        "human_review_required": True,
        "decision_mode": "decision_support",
        "autonomous_railway_control": False,
        "backup": str(BACKUP.relative_to(ROOT)),
    }

    try:
        check_artifacts()
        result["checks"]["artifacts"] = "PASS"

        compile_backend()
        result["checks"]["python_compile"] = "PASS"

        run_tests()
        result["checks"]["pytest"] = "PASS"

        build_frontend()
        result["checks"]["frontend_build"] = "PASS"

        check_stale_v1_references()
        result["checks"]["stale_v1_scan"] = "PASS"

        start_backend()

        check_api()
        result["checks"]["runtime_api"] = "PASS"
        result["checks"]["human_decision_audit"] = "PASS"

    except SystemExit:
        result["status"] = "FAIL"
        raise
    except Exception as exc:
        result["status"] = "FAIL"
        print(f"\n[FAIL] Unexpected exception: {type(exc).__name__}: {exc}")
        raise
    finally:
        stop_backend()

    REPORT_PATH.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 80)
    print("PHASE 5 COMPLETE")
    print("=" * 80)
    print(json.dumps(result, indent=2))
    print("=" * 80)


if __name__ == "__main__":
    main()
