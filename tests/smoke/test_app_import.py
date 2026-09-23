def test_backend_imports_and_routes():
    from backend.app.api import routes as primary_routes
    from backend.app.main import app

    print("main module:", __import__("backend.app.main", fromlist=["__file__"]).__file__)
    print("routes module:", primary_routes.__file__)
    print("primary router routes:", [
        getattr(route, "path", "")
        for route in primary_routes.router.routes
    ])
    print("app routes:", [
        getattr(route, "path", "")
        for route in app.routes
    ])

    paths = {
        getattr(route, "path", "")
        for route in app.routes
    }

    assert primary_routes.router.routes
    assert "/" in paths
    assert "/api/v1/health" in paths
    assert "/api/v1/planning/blocks/{block_id}/optimized-windows" in paths
