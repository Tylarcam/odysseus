"""TTS must never synthesize model thinking/reasoning — only the reply."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.tts_routes import setup_tts_routes


@pytest.fixture
def tts_client():
    mock = MagicMock()
    mock.available = True
    mock.synthesize.return_value = b"ID3fake-mp3"
    mock.synthesize_to_base64.return_value = "YmFzZTY0"
    app = FastAPI()
    app.include_router(setup_tts_routes(mock))
    return TestClient(app), mock


def test_synthesize_strips_think_tags(tts_client):
    client, mock = tts_client
    resp = client.post(
        "/api/tts/synthesize",
        json={"text": "<think time=\"1.2\">internal plan</think>\n\nHello there."},
    )
    assert resp.status_code == 200
    mock.synthesize.assert_called_once_with("Hello there.")


def test_synthesize_strips_thinking_process_prefix(tts_client):
    client, mock = tts_client
    resp = client.post(
        "/api/tts/synthesize",
        json={
            "text": "Thinking Process: Let me analyze this carefully.\n\n# Answer\n\nThe answer is 42."
        },
    )
    assert resp.status_code == 200
    spoken = mock.synthesize.call_args[0][0]
    assert "Thinking Process" not in spoken
    assert "The answer is 42." in spoken


def test_synthesize_rejects_thinking_only(tts_client):
    client, mock = tts_client
    resp = client.post(
        "/api/tts/synthesize",
        json={"text": "<think>still reasoning with no reply</think>"},
    )
    assert resp.status_code == 400
    mock.synthesize.assert_not_called()
