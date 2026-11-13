"""
The FastAPI app builds: every router imports and every route is valid
(a route FastAPI rejects only fails at startup otherwise). No DB needed.
"""
from app.main import app


def test_app_builds_with_every_router():
    paths = {route.path for route in app.routes}
    for prefix in ("/tracks", "/users", "/exercises", "/chat", "/studio", "/terms"):
        assert any(path.startswith(prefix) for path in paths), prefix
