"""Tests for Clicky overlay launcher service and routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_start_clicky_rejects_non_windows():
    with patch("services.clicky_launcher.IS_WINDOWS", False):
        from services.clicky_launcher import start_clicky

        result = start_clicky()
    assert result["ok"] is False
    assert "Windows" in result["error"]


def test_worker_ready_requires_mic_and_endpoint_chat():
    from services.clicky_launcher import worker_ready

    with patch("services.clicky_launcher._worker_has_mic_routes", return_value=True):
        with patch("services.clicky_launcher._worker_has_endpoint_chat", return_value=True):
            assert worker_ready(40002) is True
        with patch("services.clicky_launcher._worker_has_endpoint_chat", return_value=False):
            assert worker_ready(40002) is False


def test_ensure_worker_running_skips_when_ready():
    from services.clicky_launcher import ensure_worker_running

    with patch("services.clicky_launcher.worker_ready", return_value=True):
        result = ensure_worker_running({})
    assert result["ready"] is True
    assert result["started"] is False


def test_start_clicky_launches_worker_and_app():
    from services.clicky_launcher import start_clicky

    with patch("services.clicky_launcher.IS_WINDOWS", True):
        with patch("services.clicky_launcher.ensure_worker_running", return_value={"ready": True, "port": 40002}):
            with patch("services.clicky_launcher.memory_api_health", return_value=True):
                with patch("services.clicky_launcher.worker_health", return_value={"health": {"chat_model": "test-model"}}):
                    with patch("services.clicky_launcher.launch_clicky_app", return_value={"ok": True, "pid": 123}):
                        result = start_clicky(launch_app=True)
    assert result["ok"] is True
    assert "Clicky overlay launched" in result["message"]
    assert result["worker_health"]["chat_model"] == "test-model"


def test_clicky_start_route_success(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.clicky_routes import setup_clicky_routes

    monkeypatch.setattr("routes.clicky_routes.require_authenticated_request", lambda _req: "tester")
    monkeypatch.setattr(
        "routes.clicky_routes.start_clicky",
        lambda **kwargs: {
            "ok": True,
            "message": "Clicky overlay launched. Hold Ctrl+Alt to talk.",
            "worker": {"ready": True},
        },
    )
    app = FastAPI()
    app.include_router(setup_clicky_routes())
    client = TestClient(app)
    response = client.post("/api/clicky/start", json={"launch_app": True})
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_clicky_start_route_failure(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.clicky_routes import setup_clicky_routes

    monkeypatch.setattr("routes.clicky_routes.require_authenticated_request", lambda _req: "tester")
    monkeypatch.setattr(
        "routes.clicky_routes.start_clicky",
        lambda **kwargs: {"ok": False, "error": "worker unhealthy"},
    )
    app = FastAPI()
    app.include_router(setup_clicky_routes())
    client = TestClient(app)
    response = client.post("/api/clicky/start", json={"launch_app": True})
    assert response.status_code == 503
