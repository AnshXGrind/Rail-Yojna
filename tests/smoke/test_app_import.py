def test_backend_imports_and_routes():
    from backend.app.main import app

    paths = {
        getattr(route, "path", "")
        for route in app.routes
    }

    assert "/" in paths
    assert "/api/v1/health" in paths
    assert "/api/v1/planning/blocks/{block_id}/optimized-windows" in paths
