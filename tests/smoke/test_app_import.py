from fastapi.testclient import TestClient


def test_backend_imports_and_routes():
    from backend.app.main import app

    client = TestClient(app)

    assert client.get("/").status_code == 200
    assert client.get("/api/v1/health").status_code == 200

    openapi_paths = app.openapi()["paths"]

    assert "/api/v1/health" in openapi_paths
    assert (
        "/api/v1/planning/blocks/{block_id}/optimized-windows"
        in openapi_paths
    )
