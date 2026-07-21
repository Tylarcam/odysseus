"""Route Clicky /chat requests to Odysseus ModelEndpoint models."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from src.endpoint_resolver import resolve_endpoint, resolve_endpoint_by_id
from src.llm_core import stream_llm

logger = logging.getLogger("clicky_chat")


def clicky_chat_config() -> Tuple[str, str, str, str, bool]:
    """Return (mode, setting_prefix, endpoint_id, model_override, inject_memory)."""
    mode = (os.environ.get("CLICKY_CHAT_MODE") or "endpoint").strip().lower()
    prefix = (os.environ.get("CLICKY_CHAT_SETTING_PREFIX") or "default").strip() or "default"
    endpoint_id = (os.environ.get("CLICKY_CHAT_ENDPOINT_ID") or "").strip()
    model_override = (os.environ.get("CLICKY_CHAT_MODEL") or "").strip()
    inject_memory = (os.environ.get("CLICKY_CHAT_MEMORY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    return mode, prefix, endpoint_id, model_override, inject_memory


# ── Agent (operator voice) mode ──
# Speaking to the Clicky overlay can drive the Odysseus agent loop with a scoped
# operator tool set. See openspec/changes/add-clicky-operator-voice.

_OPERATOR_TOOLS = frozenset({
    "screen_look", "screen_recall", "spec_trace",
    "desktop_act", "browser_act", "operator_research",
})
# Passed explicitly so the loop skips ChromaDB retrieval — the Clicky worker is
# a separate process that may not have the tool index.
_CLICKY_AGENT_TOOLS = frozenset(_OPERATOR_TOOLS | {"web_search", "manage_memory"})

_DONE_SENTINEL = "__CLICKY_AGENT_DONE__"


def _clicky_session_id() -> str:
    return (os.environ.get("CLICKY_SESSION_ID") or "clicky-voice").strip() or "clicky-voice"


def _clicky_owner() -> Optional[str]:
    return (os.environ.get("CLICKY_CHAT_OWNER") or "").strip() or None


def _operator_consent_enabled() -> bool:
    return (os.environ.get("CLICKY_OPERATOR_CONSENT") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _clicky_max_rounds() -> int:
    try:
        return max(1, min(int(os.environ.get("CLICKY_AGENT_MAX_ROUNDS") or 8), 50))
    except (TypeError, ValueError):
        return 8


def _strip_images(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop image blocks for agent mode.

    Clicky attaches a screenshot every turn, but agent mode reads the screen
    through the ``screen_look`` tool (OCR) — and strong tools-capable local
    models (qwen2.5, llama3.1) are text-only and HARD-ERROR on image input
    ("model does not support multimodal requests"). Collapse each message to
    its text, leaving a breadcrumb so the model knows a screenshot exists.
    """
    cleaned: List[Dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            cleaned.append(msg)
            continue
        texts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        had_image = any(
            isinstance(block, dict) and block.get("type") == "image_url" for block in content
        )
        joined = " ".join(t for t in texts if t).strip()
        if had_image and not joined:
            joined = "(a screenshot is attached; call screen_look to read the screen)"
        cleaned.append({**msg, "content": joined})
    return cleaned


def translate_agent_chunk(chunk: str) -> Optional[str]:
    """Map ONE agent-loop SSE chunk to what Clicky should stream.

    Returns an Anthropic ``content_block_delta`` SSE string for spoken text,
    the ``_DONE_SENTINEL`` when the stream is complete, or None to swallow
    (tool machinery, reasoning/thinking deltas, non-data lines). Pure and
    side-effect free so the translation is unit-testable.
    """
    if chunk.startswith("event: error"):
        err = _parse_stream_llm_error(chunk)
        return _anthropic_text_delta(f"Error: {err}") if err else None
    if not chunk.startswith("data:"):
        return None
    raw = chunk[5:].strip()  # tolerant of "data: X" and "data:X"
    if raw == "[DONE]":
        return _DONE_SENTINEL
    if not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if "delta" in data:
        if data.get("thinking"):
            return None  # reasoning tokens are never spoken
        text = data.get("delta") or ""
        return _anthropic_text_delta(text) if text else None

    dtype = data.get("type")
    if dtype == "ask_user":
        # Voice can't render multiple-choice; speak the question text so the
        # user at least hears what was asked.
        question = data.get("question") or data.get("prompt") or ""
        return _anthropic_text_delta(question) if question else None
    if dtype == "error":
        msg = data.get("error") or data.get("text") or data.get("message") or "agent error"
        return _anthropic_text_delta(f"Error: {msg}")
    # tool_start, tool_output, agent_step, metrics, model_actual, fallback,
    # web_sources, doc_*, ui_control, plan_update, rounds_exhausted, ... swallowed
    return None


async def stream_agent_chat(body: Dict[str, Any]) -> AsyncIterator[str]:
    """Stream a Clicky /chat request through the Odysseus agent loop.

    The model can invoke the scoped operator tool set; the loop's event stream
    is translated back into the Anthropic SSE text the clicky-windows client
    consumes. When CLICKY_OPERATOR_CONSENT is enabled, operator action consent
    is pre-granted for the Clicky session (holding push-to-talk is the consent).
    """
    from src.agent_loop import stream_agent_loop
    from tools.clicky_worker_api import anthropic_sse_from_text

    url, model, headers = resolve_clicky_endpoint()
    if not url or not model:
        yield anthropic_sse_from_text(
            "No Odysseus model endpoint is configured for Clicky. "
            "Set Default Model in Odysseus Settings, or CLICKY_CHAT_ENDPOINT_ID / "
            "CLICKY_CHAT_MODEL in memory_stack.env."
        )
        yield "data: [DONE]\n\n"
        return

    messages, max_tokens = anthropic_body_to_openai_messages(body)
    messages = _strip_images(messages)  # agent mode reads the screen via screen_look
    session_id = _clicky_session_id()
    owner = _clicky_owner()

    if _operator_consent_enabled():
        try:
            from services.operator.core import grant_consent
            grant_consent(session_id)
        except Exception:
            logger.warning("clicky: could not pre-grant operator consent", exc_info=True)

    logger.info("clicky chat via agent loop model=%r url=%r", model, url)
    emitted = False
    try:
        async for chunk in stream_agent_loop(
            url,
            model,
            messages,
            headers=headers,
            max_tokens=max_tokens,
            max_rounds=_clicky_max_rounds(),
            session_id=session_id,
            owner=owner,
            relevant_tools=set(_CLICKY_AGENT_TOOLS),
        ):
            out = translate_agent_chunk(chunk)
            if out == _DONE_SENTINEL:
                break
            if out:
                emitted = True
                yield out
    except Exception as exc:  # never leave Clicky hanging on an agent failure
        logger.exception("clicky agent chat failed")
        yield anthropic_sse_from_text(f"Agent error: {exc}")
        yield "data: [DONE]\n\n"
        return

    if not emitted:
        yield anthropic_sse_from_text("I couldn't produce a spoken response for that.")
    yield "data: [DONE]\n\n"


def resolve_clicky_endpoint() -> Tuple[Optional[str], Optional[str], Optional[Dict[str, str]]]:
    """Resolve the configured Odysseus endpoint for Clicky chat."""
    _, prefix, endpoint_id, model_override, _ = clicky_chat_config()
    if endpoint_id:
        resolved = resolve_endpoint_by_id(endpoint_id, model_override or None)
        if resolved:
            return resolved
    url, model, headers = resolve_endpoint(prefix)
    if model_override:
        model = model_override
    return url, model, headers


def anthropic_body_to_openai_messages(body: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
    """Convert a Clicky Anthropic Messages body to OpenAI-style messages."""
    messages: List[Dict[str, Any]] = []

    system = body.get("system")
    if isinstance(system, str) and system.strip():
        messages.append({"role": "system", "content": system.strip()})
    elif isinstance(system, list):
        parts = [
            str(block.get("text") or "")
            for block in system
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        joined = "\n\n".join(part for part in parts if part.strip())
        if joined:
            messages.append({"role": "system", "content": joined})

    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role not in ("user", "assistant"):
            continue
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            continue

        blocks: List[Dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                blocks.append({"type": "text", "text": block.get("text") or ""})
            elif block_type == "image":
                source = block.get("source") or {}
                if source.get("type") == "base64":
                    media_type = source.get("media_type") or "image/jpeg"
                    data = source.get("data") or ""
                    blocks.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{data}"},
                        }
                    )
                elif source.get("type") == "url" and source.get("url"):
                    blocks.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": source.get("url")},
                        }
                    )
        messages.append({"role": role, "content": blocks})

    max_tokens = body.get("max_tokens") or 1024
    try:
        max_tokens = int(max_tokens)
    except (TypeError, ValueError):
        max_tokens = 1024
    return messages, max_tokens


def _anthropic_text_delta(text: str) -> str:
    payload = json.dumps(
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": text},
        }
    )
    return f"data: {payload}\n\n"


def _parse_stream_llm_error(event: str) -> Optional[str]:
    if not event.startswith("event: error"):
        return None
    for line in event.splitlines():
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        return (
            data.get("text")
            or data.get("error")
            or data.get("raw")
            or f"Model error (HTTP {data.get('status')})"
        )
    return "Model request failed"


async def stream_endpoint_chat(body: Dict[str, Any]) -> AsyncIterator[str]:
    """Stream Clicky chat through the configured Odysseus ModelEndpoint."""
    from tools.clicky_worker_api import (
        anthropic_sse_from_text,
        build_memory_answer,
        build_search_context,
        extract_user_prompt,
        should_clicky_web_search,
    )

    url, model, headers = resolve_clicky_endpoint()
    if not url or not model:
        yield anthropic_sse_from_text(
            "No Odysseus model endpoint is configured for Clicky. "
            "Set Default Model in Odysseus Settings, or set CLICKY_CHAT_ENDPOINT_ID "
            "and CLICKY_CHAT_MODEL in memory_stack.env."
        )
        return

    messages, max_tokens = anthropic_body_to_openai_messages(body)
    _, _, _, _, inject_memory = clicky_chat_config()
    prompt = extract_user_prompt(body)
    memory_answer: Optional[str] = None
    context_insert_at = 0
    if inject_memory and prompt:
        memory_answer = build_memory_answer(prompt)
        messages.insert(
            context_insert_at,
            {
                "role": "system",
                "content": (
                    "Relevant Odysseus memory (use only if helpful):\n"
                    f"{memory_answer}"
                ),
            },
        )
        context_insert_at += 1

    if prompt and should_clicky_web_search(prompt, memory_answer if inject_memory else None):
        search_context = await asyncio.to_thread(build_search_context, prompt)
        messages.insert(
            context_insert_at,
            {
                "role": "system",
                "content": (
                    "Relevant web search results (use only if helpful):\n"
                    f"{search_context}"
                ),
            },
        )

    logger.info("clicky chat via endpoint model=%r url=%r", model, url)
    emitted = False
    async for event in stream_llm(
        url,
        model,
        messages,
        max_tokens=max_tokens,
        headers=headers,
        timeout=120,
    ):
        error_text = _parse_stream_llm_error(event)
        if error_text:
            yield anthropic_sse_from_text(f"Model error: {error_text}")
            return

        if not event.startswith("data:"):
            continue
        raw = event[5:].strip()
        if raw == "[DONE]":
            break
        if not raw.startswith("{"):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if payload.get("thinking"):
            continue

        delta = payload.get("delta")
        if isinstance(delta, str) and delta:
            emitted = True
            yield _anthropic_text_delta(delta)

    if not emitted:
        yield anthropic_sse_from_text(
            "The local model returned an empty response. "
            "Check that your Default Model supports vision if screenshots are attached."
        )
        return

    yield "data: [DONE]\n\n"


async def stream_clicky_chat(body: Dict[str, Any]) -> AsyncIterator[str]:
    """Dispatch Clicky chat to agent, endpoint, or legacy memory-only mode."""
    mode, _, _, _, _ = clicky_chat_config()
    if mode == "memory":
        from tools.clicky_worker_api import anthropic_sse_from_text, build_memory_answer, extract_user_prompt

        prompt = extract_user_prompt(body)
        if not prompt:
            yield anthropic_sse_from_text("No user prompt found.")
            return
        answer = build_memory_answer(prompt)
        yield anthropic_sse_from_text(answer)
        return

    if mode == "agent":
        async for chunk in stream_agent_chat(body):
            yield chunk
        return

    async for chunk in stream_endpoint_chat(body):
        yield chunk
