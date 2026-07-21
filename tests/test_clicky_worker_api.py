"""Tests for the Clicky worker adapter API."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tools.clicky_worker_api import (
    anthropic_sse_from_text,
    build_memory_answer,
    create_app,
    extract_user_prompt,
    should_clicky_web_search,
)


def _anthropic_body(prompt: str) -> dict:
    """Mimic the request clicky-windows ClaudeApiClient builds."""
    return {
        "model": "claude-sonnet-4-6",
        "max_tokens": 1024,
        "stream": True,
        "system": "You are Clicky.",
        "messages": [
            {"role": "user", "content": "earlier question"},
            {"role": "assistant", "content": "earlier answer"},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": "aaaa"},
                    },
                    {"type": "text", "text": "Screen 1 (Primary)"},
                    {"type": "text", "text": prompt},
                ],
            },
        ],
    }


def test_extract_user_prompt_takes_last_text_block():
    body = _anthropic_body("what was I reading about PixelRAG?")
    assert extract_user_prompt(body) == "what was I reading about PixelRAG?"


def test_extract_user_prompt_handles_string_content():
    body = {"messages": [{"role": "user", "content": "plain question"}]}
    assert extract_user_prompt(body) == "plain question"


def test_extract_user_prompt_empty_when_missing():
    assert extract_user_prompt({}) == ""
    assert extract_user_prompt({"messages": [{"role": "assistant", "content": "hi"}]}) == ""


def test_anthropic_sse_stream_is_parseable_like_clicky():
    stream = anthropic_sse_from_text("line one\nline two")

    # Reproduce the ClaudeApiClient parse loop: data: lines, stop at [DONE].
    accumulated = []
    for line in stream.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        if payload == "[DONE]":
            break
        event = json.loads(payload)
        assert event["type"] == "content_block_delta"
        assert event["delta"]["type"] == "text_delta"
        accumulated.append(event["delta"]["text"])

    assert "".join(accumulated) == "line one\nline two\n"
    assert stream.rstrip().endswith("data: [DONE]")


def test_build_memory_answer_formats_results():
    fake_result = {
        "query": "PixelRAG",
        "visual_results": [{"id": "tile-a.png", "tile_metadata": {"window_title": "PixelRAG docs"}}],
        "agent_memory_results": [{"summary": "Explored PixelRAG pipelines."}],
        "notes_results": [{"title": "PixelRAG Pipeline Notes", "filename": "notes.md"}],
    }
    with patch("tools.clicky_worker_api.query_unified_memory", return_value=fake_result):
        answer = build_memory_answer("PixelRAG")

    assert answer.startswith("From your Odysseus memory.")
    assert "PixelRAG docs" in answer


def test_build_memory_answer_handles_empty_results():
    empty = {"query": "x", "visual_results": [], "agent_memory_results": [], "notes_results": []}
    with patch("tools.clicky_worker_api.query_unified_memory", return_value=empty):
        answer = build_memory_answer("x")

    assert "could not find anything" in answer


def test_build_search_context_truncates_long_results():
    with patch(
        "tools.clicky_worker_api.comprehensive_web_search",
        return_value=("x" * 5000, []),
        create=True,
    ):
        with patch.dict("os.environ", {}, clear=False):
            # Import inside patch scope because build_search_context lazy-imports search
            import tools.clicky_worker_api as api

            with patch("src.search.comprehensive_web_search", return_value=("x" * 5000, [])):
                text = api.build_search_context("rust news")

    assert len(text) <= 4015
    assert text.endswith("[...truncated]")


def test_should_clicky_web_search_respects_disable_flag():
    with patch.dict("os.environ", {"CLICKY_CHAT_SEARCH": "false"}, clear=False):
        assert should_clicky_web_search("search for cats") is False


def test_chat_route_returns_sse_answer():
    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    async def fake_stream(_body):
        yield 'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello from local model\\n"}}\n\n'
        yield "data: [DONE]\n\n"

    app = create_app()
    client = TestClient(app)

    with patch("clicky_integration.clicky_chat.stream_clicky_chat", fake_stream):
        response = client.post("/chat", json=_anthropic_body("what was I reading?"))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "content_block_delta" in response.text
    assert "Hello from local model" in response.text
    assert "data: [DONE]" in response.text


def test_chat_route_memory_mode():
    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    fake_result = {
        "query": "PixelRAG",
        "visual_results": [{"id": "tile-a.png", "tile_metadata": {"window_title": "PixelRAG docs"}}],
        "agent_memory_results": [],
        "notes_results": [],
    }

    app = create_app()
    client = TestClient(app)

    with patch.dict("os.environ", {"CLICKY_CHAT_MODE": "memory"}, clear=False):
        with patch("tools.clicky_worker_api.query_unified_memory", return_value=fake_result):
            response = client.post("/chat", json=_anthropic_body("what was I reading?"))

    assert response.status_code == 200
    assert "PixelRAG docs" in response.text


def test_chat_route_rejects_bodies_without_prompt():
    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    client = TestClient(create_app())
    assert client.post("/chat", json={"messages": []}).status_code == 400
    assert client.post("/chat", content=b"not json").status_code == 400


def test_transcribe_route_uses_local_stt_first():
    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    client = TestClient(create_app())
    with patch(
        "tools.clicky_worker_api.transcribe_clicky_audio",
        return_value=(200, b'{"transcript": "hello clicky"}', "application/json"),
    ) as transcribe:
        response = client.post(
            "/transcribe",
            content=b"RIFFfakewav",
            headers={"Content-Type": "audio/wav"},
        )

    assert response.status_code == 200
    assert response.json()["transcript"] == "hello clicky"
    transcribe.assert_called_once()


def test_transcribe_clicky_audio_falls_back_to_upstream():
    from tools import clicky_worker_api as api

    with patch("services.stt.get_stt_service", side_effect=ImportError("no stt")):
        with patch.object(
            api,
            "_proxy_upstream",
            return_value=(200, b'{"transcript": "from cloud"}', "application/json"),
        ) as proxy:
            status, payload, _ = api.transcribe_clicky_audio(b"RIFF", "audio/wav")

    assert status == 200
    assert b"from cloud" in payload
    proxy.assert_called_once_with("/transcribe", b"RIFF", "audio/wav")


def test_transcribe_route_proxies_upstream():
    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    client = TestClient(create_app())
    upstream_body = json.dumps({"transcript": "hello clicky"}).encode("utf-8")

    with patch(
        "tools.clicky_worker_api.transcribe_clicky_audio",
        return_value=(200, upstream_body, "application/json"),
    ):
        response = client.post(
            "/transcribe",
            content=b"RIFFfakewav",
            headers={"Content-Type": "audio/wav"},
        )

    assert response.status_code == 200
    assert response.json()["transcript"] == "hello clicky"


def test_health_and_warmup_routes():
    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    client = TestClient(create_app())
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert client.head("/").status_code == 200


def test_mic_lease_routes():
    pytest.importorskip("starlette")
    from starlette.testclient import TestClient

    client = TestClient(create_app())
    assert client.get("/mic/status").json()["available"] is True

    claim = client.post("/mic/claim", json={"holder": "clicky", "mode": "ptt"})
    assert claim.status_code == 200
    token = claim.json()["token"]

    blocked = client.post("/mic/claim", json={"holder": "odysseus", "mode": "recorder"})
    assert blocked.status_code == 409
    assert blocked.json()["holder"] == "clicky"

    release = client.post("/mic/release", json={"holder": "clicky", "token": token})
    assert release.status_code == 200
    assert release.json()["released"] is True
