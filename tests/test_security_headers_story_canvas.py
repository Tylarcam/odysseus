from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.middleware import SecurityHeadersMiddleware


def _client():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/plain")
    async def plain():
        return {"ok": True}

    @app.get("/static/story-canvas/index.html")
    async def story_canvas_index():
        return "<!DOCTYPE html><html><body><div id='root'></div></body></html>"

    return TestClient(app)


def test_default_routes_remain_unframeable():
    response = _client().get("/plain")

    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_story_canvas_static_can_be_framed_by_same_origin():
    response = _client().get("/static/story-canvas/index.html")

    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    csp = response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'self'" in csp
    assert "frame-ancestors 'none'" not in csp
    assert "script-src 'self'" in csp
