"""Streaming STT WebSocket route (Phase 2) — /api/stt/stream.

Builds a minimal FastAPI app around just the stt_stream router (same pattern
as test_device_flow_routes.py) instead of importing the full app.py, so these
tests don't need the whole app's startup side effects. Auth is monkeypatched
at the `authenticate_websocket` call site inside routes.stt_stream_routes.
"""
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import stt_stream_routes


class _FakeSegment:
    def __init__(self, text):
        self.text = text


class _FakeInfo:
    language = "en"
    language_probability = 0.99


class _FakeWhisperModel:
    """Stubbed faster-whisper model — no real audio decode needed."""

    def __init__(self, text="hello world"):
        self.text = text
        self.transcribe_calls = 0

    def transcribe(self, _path, **_kwargs):
        self.transcribe_calls += 1
        return [_FakeSegment(self.text)], _FakeInfo()


def _make_stt_service(provider="local", model=None):
    stt_service = MagicMock()
    stt_service._load_settings.return_value = {
        "stt_enabled": True,
        "stt_provider": provider,
        "stt_model": "base",
        "stt_language": "",
    }
    stt_service._get_whisper.return_value = model
    return stt_service


def _client(monkeypatch, stt_service, auth_user="alice"):
    monkeypatch.setattr(stt_stream_routes, "authenticate_websocket", lambda ws: auth_user)
    app = FastAPI()
    app.include_router(stt_stream_routes.setup_stt_stream_routes(stt_service))
    return TestClient(app)


def test_unauthenticated_connection_is_rejected(monkeypatch):
    stt_service = _make_stt_service(model=_FakeWhisperModel())
    client = _client(monkeypatch, stt_service, auth_user=None)

    with pytest.raises(Exception):
        with client.websocket_connect("/api/stt/stream"):
            pass


def test_non_local_provider_gets_error_frame_then_closes(monkeypatch):
    stt_service = _make_stt_service(provider="browser")
    client = _client(monkeypatch, stt_service)

    with client.websocket_connect("/api/stt/stream") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "local" in msg["message"].lower()


def test_missing_model_gets_error_frame(monkeypatch):
    stt_service = _make_stt_service(provider="local", model=None)
    client = _client(monkeypatch, stt_service)

    with client.websocket_connect("/api/stt/stream") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "whisper" in msg["message"].lower()


def test_start_binary_stop_yields_final_frame(monkeypatch):
    model = _FakeWhisperModel(text="testing one two three")
    stt_service = _make_stt_service(provider="local", model=model)
    client = _client(monkeypatch, stt_service)

    with client.websocket_connect("/api/stt/stream") as ws:
        ws.send_json({"type": "start", "sampleRate": 16000})
        ws.send_bytes(b"\x00\x00" * 1600)  # 0.1s of silence @16kHz mono 16-bit
        ws.send_json({"type": "stop"})
        msg = ws.receive_json()
        assert msg["type"] == "final"
        assert msg["text"] == "testing one two three"
    assert model.transcribe_calls >= 1


def test_cancel_yields_no_final_frame(monkeypatch):
    model = _FakeWhisperModel(text="should not appear")
    stt_service = _make_stt_service(provider="local", model=model)
    client = _client(monkeypatch, stt_service)

    with client.websocket_connect("/api/stt/stream") as ws:
        ws.send_json({"type": "start", "sampleRate": 16000})
        ws.send_bytes(b"\x00\x00" * 1600)
        ws.send_json({"type": "cancel"})
        with pytest.raises(Exception):
            ws.receive_json()
