"""Local STT readiness — stats reason + 503 detail."""

from unittest.mock import MagicMock

import pytest

from routes.stt_routes import _stt_unavailable_message
from services.stt.stt_service import STTService


def test_get_stats_reports_missing_package(monkeypatch):
    service = STTService()

    monkeypatch.setattr(service, "_load_settings", lambda: {
        "stt_enabled": True,
        "stt_provider": "local",
        "stt_model": "tiny",
        "stt_language": "",
    })

    def fake_get_whisper():
        service._set_local_status(
            "missing_package",
            "missing_package",
            "faster-whisper is not installed on the server",
        )
        return None

    monkeypatch.setattr(service, "_get_whisper", fake_get_whisper)

    stats = service.get_stats()
    assert stats["available"] is False
    assert stats["model_loaded"] is False
    assert stats["local_status"] == "missing_package"
    assert stats["reason"] == "missing_package"
    assert "not installed" in stats["local_detail"]


def test_get_stats_reports_load_failed(monkeypatch):
    service = STTService()

    monkeypatch.setattr(service, "_load_settings", lambda: {
        "stt_enabled": True,
        "stt_provider": "local",
        "stt_model": "tiny",
        "stt_language": "",
    })

    def fake_get_whisper():
        service._set_local_status("load_failed", "load_failed", "CUDA OOM")
        return None

    monkeypatch.setattr(service, "_get_whisper", fake_get_whisper)

    stats = service.get_stats()
    assert stats["reason"] == "load_failed"
    assert stats["local_detail"] == "CUDA OOM"


def test_get_stats_reports_loaded(monkeypatch):
    service = STTService()
    model = MagicMock()

    monkeypatch.setattr(service, "_load_settings", lambda: {
        "stt_enabled": True,
        "stt_provider": "local",
        "stt_model": "tiny",
        "stt_language": "",
    })
    monkeypatch.setattr(service, "_get_whisper", lambda: model)

    stats = service.get_stats()
    assert stats["available"] is True
    assert stats["model_loaded"] is True


def test_stt_unavailable_message_missing_package():
    msg = _stt_unavailable_message({
        "provider": "local",
        "reason": "missing_package",
    })
    assert "not installed" in msg
    assert "INSTALL_STT=true" in msg
    assert "Browser" in msg
    assert "Settings > Audio & Voice" in msg


def test_stt_unavailable_message_load_failed():
    msg = _stt_unavailable_message({
        "provider": "local",
        "reason": "load_failed",
        "local_detail": "CUDA OOM",
    })
    assert "failed to load" in msg
    assert "CUDA OOM" in msg
    assert "Browser" in msg


def test_stt_unavailable_message_browser():
    msg = _stt_unavailable_message({"provider": "browser"})
    assert "browser" in msg.lower()
    assert "Settings > Audio & Voice" in msg
