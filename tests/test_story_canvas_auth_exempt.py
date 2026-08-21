"""Pin auth exemption for Story Canvas API routes.

Story Canvas save/load/research must work without a session cookie.
Routes in routes/story_canvas_routes.py already treat owner as optional;
AuthMiddleware was rejecting every /api/story-canvas/* call with 401
before handlers ran.
"""

import os


def _read_app_source() -> str:
    app_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app.py",
    )
    with open(app_path, encoding="utf-8") as fh:
        return fh.read()


def test_story_canvas_prefix_is_auth_exempt():
    src = _read_app_source()
    assert '"/api/story-canvas"' in src, (
        "/api/story-canvas must appear in AUTH_EXEMPT_PREFIXES"
    )
    start = src.find("AUTH_EXEMPT_PREFIXES")
    assert start != -1
    end = src.find("]", start)
    block = src[start:end]
    assert "/api/story-canvas" in block
