"""Tests for POST /reopen (Task D)."""

from __future__ import annotations

import json

import pytest

from tools.unified_memory_api import (
    DEFAULT_BU_CDP_URL,
    create_app,
    is_openable_url,
    lookup_article_metadata,
    open_url_via_browser_harness,
)


def _fixture_metadata():
    return {
        "0": {
            "article_id": 0,
            "url": "https://github.com/example/repo",
            "window_title": "GitHub",
            "timestamp": "2026-07-07T01:05:00",
        },
        "1": {
            "article_id": 1,
            "url": "",
            "window_title": "windows explorer",
            "timestamp": "2026-07-07T03:05:00",
        },
    }


@pytest.fixture
def metadata_path(tmp_path):
    path = tmp_path / "tiles_metadata.json"
    path.write_text(json.dumps(_fixture_metadata()), encoding="utf-8")
    return path


def test_lookup_article_metadata_found(metadata_path):
    meta = lookup_article_metadata(0, metadata_path=metadata_path)
    assert meta["url"] == "https://github.com/example/repo"
    assert meta["window_title"] == "GitHub"


def test_lookup_article_metadata_missing_raises(metadata_path):
    with pytest.raises(LookupError):
        lookup_article_metadata(99, metadata_path=metadata_path)


def test_is_openable_url_accepts_and_rejects():
    assert is_openable_url("https://github.com/example/repo") is True
    assert is_openable_url("http://localhost:8080/page") is True
    assert is_openable_url("") is False
    assert is_openable_url("windows explorer") is False
    assert is_openable_url("ftp://files.example.com") is False
    assert is_openable_url("  https://example.com  ") is True


def test_reopen_endpoint_200(metadata_path, monkeypatch):
    monkeypatch.setattr(
        "tools.unified_memory_api.resolve_path",
        lambda key, default="", env=None: metadata_path,
    )
    monkeypatch.setattr(
        "tools.unified_memory_api.open_url_via_browser_harness",
        lambda url: None,
    )

    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    resp = client.post("/reopen", json={"article_id": 0})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "opened"
    assert body["article_id"] == 0
    assert body["url"] == "https://github.com/example/repo"
    assert body["window_title"] == "GitHub"
    assert body["timestamp"] == "2026-07-07T01:05:00"
    assert body["method"] == "browser-harness"


def test_reopen_endpoint_422_empty_url(metadata_path, monkeypatch):
    monkeypatch.setattr(
        "tools.unified_memory_api.resolve_path",
        lambda key, default="", env=None: metadata_path,
    )

    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    resp = client.post("/reopen", json={"article_id": 1})

    assert resp.status_code == 422
    assert resp.json()["error"] == "no openable url"


def test_reopen_endpoint_404(metadata_path, monkeypatch):
    monkeypatch.setattr(
        "tools.unified_memory_api.resolve_path",
        lambda key, default="", env=None: metadata_path,
    )

    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    resp = client.post("/reopen", json={"article_id": 99})

    assert resp.status_code == 404
    assert resp.json()["error"] == "article not found"


def test_reopen_endpoint_503_harness_unavailable(metadata_path, monkeypatch):
    monkeypatch.setattr(
        "tools.unified_memory_api.resolve_path",
        lambda key, default="", env=None: metadata_path,
    )

    def _raise(url: str) -> None:
        raise RuntimeError("browser-harness not on PATH")

    monkeypatch.setattr(
        "tools.unified_memory_api.open_url_via_browser_harness",
        _raise,
    )

    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    resp = client.post("/reopen", json={"article_id": 0})

    assert resp.status_code == 503
    assert resp.json()["error"] == "browser-harness unavailable"


def test_open_url_pins_bu_cdp_url(monkeypatch):
    """Path A: subprocess always gets BU_CDP_URL (Comet :9333 default)."""
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["env"] = kwargs.get("env") or {}
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("tools.unified_memory_api.subprocess.run", fake_run)
    monkeypatch.setattr("tools.unified_memory_api.shutil.which", lambda _: "browser-harness")
    monkeypatch.delenv("BU_CDP_URL", raising=False)
    monkeypatch.setattr(
        "tools.unified_memory_api.load_memory_stack_env",
        lambda: {},
    )

    open_url_via_browser_harness("https://example.com")

    assert seen["env"].get("BU_CDP_URL") == DEFAULT_BU_CDP_URL


def test_open_url_respects_explicit_bu_cdp_url(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["env"] = kwargs.get("env") or {}
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("tools.unified_memory_api.subprocess.run", fake_run)
    monkeypatch.setattr("tools.unified_memory_api.shutil.which", lambda _: "browser-harness")
    monkeypatch.setenv("BU_CDP_URL", "http://127.0.0.1:9444")
    monkeypatch.setattr(
        "tools.unified_memory_api.load_memory_stack_env",
        lambda: {"BU_CDP_URL": "http://127.0.0.1:9333"},
    )

    open_url_via_browser_harness("https://example.com")

    assert seen["env"].get("BU_CDP_URL") == "http://127.0.0.1:9444"
