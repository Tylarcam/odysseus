"""Tests for Clicky chat routing to Odysseus endpoints."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from clicky_integration.clicky_chat import (
    anthropic_body_to_openai_messages,
    clicky_chat_config,
    stream_endpoint_chat,
)
from tools.clicky_worker_api import (
    memory_answer_is_empty,
    should_clicky_web_search,
)


def _anthropic_body() -> dict:
    return {
        "model": "ignored",
        "max_tokens": 512,
        "system": "You are Clicky.",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": "abcd",
                        },
                    },
                    {"type": "text", "text": "Screen 1"},
                    {"type": "text", "text": "what is on my screen?"},
                ],
            }
        ],
    }


def test_anthropic_body_to_openai_messages_converts_vision_blocks():
    messages, max_tokens = anthropic_body_to_openai_messages(_anthropic_body())

    assert max_tokens == 512
    assert messages[0]["role"] == "system"
    user = messages[1]
    assert user["role"] == "user"
    assert user["content"][0]["type"] == "image_url"
    assert user["content"][0]["image_url"]["url"] == "data:image/jpeg;base64,abcd"
    assert user["content"][-1]["text"] == "what is on my screen?"


def test_clicky_chat_config_defaults_to_endpoint_mode():
    with patch.dict("os.environ", {}, clear=True):
        mode, prefix, endpoint_id, model_override, inject_memory = clicky_chat_config()
    assert mode == "endpoint"
    assert prefix == "default"
    assert endpoint_id == ""
    assert model_override == ""
    assert inject_memory is False


async def _collect_stream(body):
    from clicky_integration.clicky_chat import stream_endpoint_chat

    chunks = []
    async for chunk in stream_endpoint_chat(body):
        chunks.append(chunk)
    return "".join(chunks)


def test_stream_endpoint_chat_emits_anthropic_sse():
    import asyncio

    async def fake_stream_llm(*_args, **_kwargs):
        yield 'data: {"delta": "Hi "}\n\n'
        yield 'data: {"delta": "there"}\n\n'
        yield "data: [DONE]\n\n"

    with patch(
        "clicky_integration.clicky_chat.resolve_clicky_endpoint",
        return_value=("http://127.0.0.1:8000/v1/chat/completions", "test-model", {}),
    ):
        with patch("clicky_integration.clicky_chat.stream_llm", fake_stream_llm):
            text = asyncio.run(_collect_stream(_anthropic_body()))

    assert "content_block_delta" in text
    assert "Hi " in text
    assert "there" in text
    assert "data: [DONE]" in text


def test_should_clicky_web_search_on_explicit_request():
    with patch.dict("os.environ", {"CLICKY_CHAT_SEARCH": "true"}, clear=False):
        assert should_clicky_web_search("please search for latest rust news") is True
        assert should_clicky_web_search("what was I reading?") is False


def test_should_clicky_web_search_when_memory_empty():
    with patch.dict("os.environ", {"CLICKY_CHAT_SEARCH": "true"}, clear=False):
        empty = "I could not find anything in your Odysseus memory about that."
        assert memory_answer_is_empty(empty) is True
        assert should_clicky_web_search("tell me about PixelRAG", empty) is True


async def test_stream_endpoint_chat_injects_memory_and_search():
    captured_messages = []

    async def fake_stream_llm(_url, _model, messages, **_kwargs):
        captured_messages.extend(messages)
        yield 'data: {"delta": "answer"}\n\n'
        yield "data: [DONE]\n\n"

    with patch.dict(
        "os.environ",
        {"CLICKY_CHAT_MEMORY": "true", "CLICKY_CHAT_SEARCH": "true"},
        clear=False,
    ):
        with patch(
            "clicky_integration.clicky_chat.resolve_clicky_endpoint",
            return_value=("http://127.0.0.1:11434/v1/chat/completions", "llava:7b", {}),
        ):
            with patch(
                "tools.clicky_worker_api.build_memory_answer",
                return_value="I could not find anything in your Odysseus memory about that.",
            ):
                with patch(
                    "tools.clicky_worker_api.build_search_context",
                    return_value="Result one about rust.",
                ):
                    with patch("clicky_integration.clicky_chat.stream_llm", fake_stream_llm):
                        await _collect_stream(_anthropic_body())

    system_contents = [m["content"] for m in captured_messages if m.get("role") == "system"]
    assert any("Odysseus memory" in c for c in system_contents)
    assert any("web search results" in c for c in system_contents)
