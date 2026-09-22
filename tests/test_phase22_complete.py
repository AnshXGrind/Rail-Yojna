
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.window_optimizer import optimize_task_windows


client = TestClient(app)


def test_optimized_windows_route_is_registered():
    schema = app.openapi()
    paths = schema.get("paths", {})

    assert "/api/v1/planning/blocks/{block_id}/optimized-windows" in paths


def test_historical_task_has_train_evaluation():
    result = optimize_task_windows(
        "TASK00000010",
        include_resource_check=False,
        limit=10,
    )

    assert result["status"] != "MAINTENANCE_DATA_GAP"
    assert result["train_coverage"]["status"] == "EVALUATED"


def test_candidates_remain_decision_support():
    response = client.get(
        "/api/v1/planning/blocks/candidates",
        params={"limit": 3},
    )

    assert response.status_code == 200

    body = response.json()

    for item in body["items"]:
        assert (
            item["constraint_status"]["signalling_authority"]
            == "not_evaluated"
        )


def test_invalid_optimized_window_block_is_rejected():
    response = client.get(
        "/api/v1/planning/blocks/not-a-valid-block/optimized-windows"
    )

    assert response.status_code == 400


def test_real_candidate_optimized_window_endpoint():
    response = client.get(
        "/api/v1/planning/blocks/candidates",
        params={"limit": 1},
    )

    assert response.status_code == 200

    items = response.json()["items"]

    if not items:
        return

    block_id = items[0]["block_id"]

    response = client.get(
        f"/api/v1/planning/blocks/{block_id}/optimized-windows"
    )

    assert response.status_code == 200

    body = response.json()

    assert "alternative_windows" in body
    assert "trains" in body
    assert "resources" in body
    assert "materials" in body
