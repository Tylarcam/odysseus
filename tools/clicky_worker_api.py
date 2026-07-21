#!/usr/bin/env python3
"""Clicky worker adapter: speaks the clicky-windows Worker protocol locally.

clicky-windows talks to a single "Worker" base URL with three routes:
  POST /chat       -> Anthropic Messages body in, Anthropic SSE stream out
  POST /transcribe -> WAV bytes in, {"transcript": str} out
  POST /tts        -> {"text", "voice_id"} in, MP3 bytes out

This adapter answers /chat through Odysseus ModelEndpoint models (Settings →
Default Model, or CLICKY_CHAT_* in memory_stack.env). Legacy memory-only mode
is available via CLICKY_CHAT_MODE=memory. /transcribe uses local STT first;
/tts is proxied to CLICKY_UPSTREAM_WORKER_URL for cloud voices.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

from clicky_integration.clicky_client import format_overlay_summary, query_unified_memory
from tools.memory_stack_env import load_memory_stack_env

logger = logging.getLogger("clicky_worker_api")

DEFAULT_UPSTREAM_WORKER_URL = "https://clicky-proxy.tylarcam.workers.dev"


def _memory_query_timeout() -> float:
    raw = os.environ.get("CLICKY_MEMORY_TIMEOUT", "30")
    try:
        return float(raw)
    except ValueError:
        return 30.0


def _upstream_worker_url() -> str:
    url = os.environ.get("CLICKY_UPSTREAM_WORKER_URL") or DEFAULT_UPSTREAM_WORKER_URL
    return url.rstrip("/")


def extract_user_prompt(body: Dict[str, Any]) -> str:
    """Pull the spoken user prompt out of an Anthropic Messages request body.

    clicky-windows builds the last user message as content blocks:
    [image, label, image, label, ..., final text = the transcript]. The last
    text block is the actual user prompt.
    """
    messages = body.get("messages")
    if not isinstance(messages, list):
        return ""

    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_blocks = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            if text_blocks:
                return str(text_blocks[-1]).strip()
        return ""
    return ""


def build_memory_answer(query_text: str, *, k: int = 3) -> str:
    """Query unified memory and format a spoken-friendly answer."""
    result = query_unified_memory(query_text, k=k, timeout=_memory_query_timeout())
    summary = format_overlay_summary(result)
    if summary == "No matching memory found.":
        return (
            "I could not find anything in your Odysseus memory about that. "
            "Try rephrasing, or make sure the archivist stack has recent captures."
        )
    if result.get("error"):
        return f"I could not reach your Odysseus memory. {summary}"
    return f"From your Odysseus memory. {summary}"


def clicky_chat_search_enabled() -> bool:
    return (os.environ.get("CLICKY_CHAT_SEARCH") or "true").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _clicky_search_max_pages() -> int:
    raw = os.environ.get("CLICKY_SEARCH_MAX_PAGES", "2")
    try:
        return max(1, min(5, int(raw)))
    except ValueError:
        return 2


def memory_answer_is_empty(answer: str) -> bool:
    low = (answer or "").lower()
    return (
        "could not find anything" in low
        or "could not reach your odysseus memory" in low
    )


def should_clicky_web_search(prompt: str, memory_answer: Optional[str] = None) -> bool:
    """True when Clicky should inject Odysseus web search into the chat prompt."""
    if not clicky_chat_search_enabled():
        return False
    q = (prompt or "").lower()
    hints = (
        "search for",
        "look up",
        "look online",
        "google ",
        "web search",
        "find online",
        "latest news",
        "breaking news",
        "what is the current",
        "who is ",
        "when did ",
        "how much is ",
        "price of ",
    )
    if any(h in q for h in hints):
        return True
    if memory_answer and memory_answer_is_empty(memory_answer):
        return True
    return False


def build_search_context(query_text: str, *, max_pages: Optional[int] = None) -> str:
    """Run Odysseus web search and format for Clicky prompt injection."""
    pages = max_pages if max_pages is not None else _clicky_search_max_pages()
    try:
        from src.search import comprehensive_web_search

        text, _sources = comprehensive_web_search(
            query_text,
            max_pages=pages,
            return_sources=True,
        )
    except Exception as exc:
        logger.warning("clicky web search failed: %s", exc)
        return f"Web search failed: {exc}"
    text = (text or "").strip()
    if not text:
        return "Web search returned no results."
    if "disabled" in text.lower():
        return text
    if len(text) > 4000:
        text = text[:4000] + "\n[...truncated]"
    return text


def anthropic_sse_from_text(text: str) -> str:
    """Encode text as the Anthropic SSE stream clicky-windows parses.

    ClaudeApiClient only consumes lines starting with "data: " whose payload
    has type == content_block_delta and delta.type == text_delta, stopping at
    "data: [DONE]".
    """
    events: List[str] = []
    for line in text.splitlines() or [text]:
        payload = json.dumps(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": line + "\n"},
            }
        )
        events.append(f"data: {payload}\n\n")
    events.append("data: [DONE]\n\n")
    return "".join(events)


def _proxy_upstream(
    path: str,
    body: bytes,
    content_type: str,
    timeout: float = 60.0,
) -> Tuple[int, bytes, str]:
    """POST raw bytes to the upstream Cloudflare worker via httpx (not urllib).

    urllib triggers Cloudflare Browser Integrity Check (error 1010) on the worker
    zone; httpx with explicit headers matches what succeeds from other clients.
    """
    url = f"{_upstream_worker_url()}{path}"
    headers = {
        "Content-Type": content_type or "application/octet-stream",
        "User-Agent": "Odysseus-Clicky-Worker/1.0",
        "Accept": "application/json, */*",
    }
    try:
        response = httpx.post(url, content=body, headers=headers, timeout=timeout)
        return (
            response.status_code,
            response.content,
            response.headers.get("Content-Type", "application/octet-stream"),
        )
    except httpx.RequestError as exc:
        detail = json.dumps({"error": f"upstream worker unreachable: {exc}"})
        return 502, detail.encode("utf-8"), "application/json"


def transcribe_clicky_audio(raw: bytes, content_type: str) -> Tuple[int, bytes, str]:
    """Transcribe Clicky push-to-talk audio: local STT first, upstream fallback."""
    ct = content_type or "audio/wav"
    try:
        from services.stt import get_stt_service

        stt = get_stt_service()
        stats = stt.get_stats()
        provider = stats.get("provider") or "disabled"
        if provider not in ("disabled", "browser") and stats.get("available"):
            text = stt.transcribe(raw, content_type=ct, filename="clicky.wav")
            if text and text.strip():
                logger.info("clicky transcribe via local STT (%s): %d chars", provider, len(text))
                payload = json.dumps({"transcript": text.strip()}).encode("utf-8")
                return 200, payload, "application/json"
            logger.info("clicky local STT returned empty (provider=%s)", provider)
    except Exception as exc:
        logger.warning("clicky local STT failed, trying upstream: %s", exc)

    status, payload, out_ct = _proxy_upstream("/transcribe", raw, ct)
    if status == 200:
        logger.info("clicky transcribe via upstream worker")
    else:
        logger.warning("clicky upstream transcribe failed status=%s body=%r", status, payload[:200])
    return status, payload, out_ct


# ---------------------------------------------------------------------------
# Pointer actions (agentic operator desktop_act — runs on the Windows host)
# ---------------------------------------------------------------------------

_POINTER_ACTIONS = {"move", "click", "double_click", "drag"}
_MOUSE_BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}  # down, up flags


def perform_pointer_action(args: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """Execute a pointer action via user32 SendCursor/mouse_event.

    Returns (http_status, payload). Separated from the route for testability;
    non-Windows hosts report unsupported_platform instead of raising.
    """
    action = str(args.get("action") or "").lower()
    if action not in _POINTER_ACTIONS:
        return 400, {"ok": False, "reason": "unsupported_action",
                     "supported": sorted(_POINTER_ACTIONS)}

    if os.name != "nt":
        return 501, {"ok": False, "reason": "unsupported_platform"}

    try:
        x, y = int(args["x"]), int(args["y"])
    except (KeyError, TypeError, ValueError):
        return 400, {"ok": False, "reason": "bad_coordinates"}

    button = str(args.get("button") or "left").lower()
    down_flag, up_flag = _MOUSE_BUTTONS.get(button, _MOUSE_BUTTONS["left"])

    import ctypes
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    user32.SetCursorPos(x, y)

    def _click_once():
        user32.mouse_event(down_flag, 0, 0, 0, 0)
        user32.mouse_event(up_flag, 0, 0, 0, 0)

    if action == "click":
        _click_once()
    elif action == "double_click":
        _click_once()
        _click_once()
    elif action == "drag":
        try:
            to_x, to_y = int(args["to_x"]), int(args["to_y"])
        except (KeyError, TypeError, ValueError):
            return 400, {"ok": False, "reason": "bad_coordinates"}
        user32.mouse_event(down_flag, 0, 0, 0, 0)
        user32.SetCursorPos(to_x, to_y)
        user32.mouse_event(up_flag, 0, 0, 0, 0)

    return 200, {"ok": True, "action": action, "x": x, "y": y, "button": button}


def create_app():
    """Starlette app factory (mirrors tools/unified_memory_api.py conventions)."""
    from starlette.applications import Starlette
    from starlette.concurrency import run_in_threadpool
    from starlette.requests import Request
    from starlette.responses import JSONResponse, PlainTextResponse, Response
    from starlette.routing import Route

    async def chat_endpoint(request: Request):
        from clicky_integration.clicky_chat import stream_clicky_chat
        from starlette.responses import StreamingResponse

        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "invalid body"}, status_code=400)

        prompt = extract_user_prompt(body)
        if not prompt:
            return JSONResponse({"error": "no user prompt found"}, status_code=400)

        logger.info("chat prompt=%r", prompt)
        return StreamingResponse(
            stream_clicky_chat(body),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    async def transcribe_endpoint(request: Request):
        raw = await request.body()
        status, payload, content_type = await run_in_threadpool(
            transcribe_clicky_audio,
            raw,
            request.headers.get("content-type", "audio/wav"),
        )
        return Response(payload, status_code=status, media_type=content_type)

    async def tts_endpoint(request: Request):
        raw = await request.body()
        status, payload, content_type = await run_in_threadpool(
            _proxy_upstream,
            "/tts",
            raw,
            request.headers.get("content-type", "application/json"),
        )
        return Response(payload, status_code=status, media_type=content_type)

    async def mic_status(_request: Request):
        from services.voice.mic_lease import get_status

        return JSONResponse(get_status())

    async def mic_claim(request: Request):
        from services.voice.mic_lease import claim

        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse({"ok": False, "reason": "invalid json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "reason": "invalid body"}, status_code=400)

        holder = str(body.get("holder") or "clicky")
        mode = str(body.get("mode") or "ptt")
        ttl_raw = body.get("ttl_sec", 90)
        try:
            ttl_sec = int(ttl_raw)
        except (TypeError, ValueError):
            ttl_sec = 90

        result = claim(holder, mode=mode, ttl_sec=ttl_sec)
        status = 200 if result.get("ok") else 409
        return JSONResponse(result, status_code=status)

    async def mic_release(request: Request):
        from services.voice.mic_lease import release

        try:
            body = await request.json()
        except json.JSONDecodeError:
            body = {}
        if not isinstance(body, dict):
            body = {}

        holder = str(body.get("holder") or "clicky")
        token = body.get("token")
        result = release(holder, str(token) if token else None)
        status = 200 if result.get("ok") else 409
        return JSONResponse(result, status_code=status)

    async def health(_request: Request):
        stt_provider = "unknown"
        stt_available = False
        try:
            from services.stt import get_stt_service

            stats = get_stt_service().get_stats()
            stt_provider = stats.get("provider") or "disabled"
            stt_available = bool(stats.get("available"))
        except Exception:
            pass
        chat_url = None
        chat_model = None
        chat_mode = "endpoint"
        chat_memory = False
        chat_search = False
        try:
            from clicky_integration.clicky_chat import clicky_chat_config, resolve_clicky_endpoint

            chat_mode, _, _, _, chat_memory = clicky_chat_config()
            chat_url, chat_model, _ = resolve_clicky_endpoint()
            chat_search = clicky_chat_search_enabled()
        except Exception:
            pass
        return JSONResponse(
            {
                "status": "ok",
                "upstream": _upstream_worker_url(),
                "stt_provider": stt_provider,
                "stt_available": stt_available,
                "transcribe": "local-first",
                "chat_mode": chat_mode,
                "chat_model": chat_model,
                "chat_endpoint_url": chat_url,
                "chat_memory": chat_memory,
                "chat_search": chat_search,
            }
        )

    async def pointer_endpoint(request: Request):
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse({"ok": False, "reason": "invalid json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "reason": "invalid body"}, status_code=400)
        status, payload = await run_in_threadpool(perform_pointer_action, body)
        return JSONResponse(payload, status_code=status)

    async def root(_request: Request):
        # ClaudeApiClient sends a HEAD / for TLS warmup at startup.
        return PlainTextResponse("clicky worker adapter")

    return Starlette(
        routes=[
            Route("/chat", chat_endpoint, methods=["POST"]),
            Route("/transcribe", transcribe_endpoint, methods=["POST"]),
            Route("/tts", tts_endpoint, methods=["POST"]),
            Route("/health", health, methods=["GET"]),
            Route("/mic/status", mic_status, methods=["GET"]),
            Route("/mic/claim", mic_claim, methods=["POST"]),
            Route("/mic/release", mic_release, methods=["POST"]),
            Route("/pointer", pointer_endpoint, methods=["POST"]),
            Route("/", root, methods=["GET", "HEAD"]),
        ],
    )


def main() -> int:
    import uvicorn

    env = load_memory_stack_env()
    raw_port = env.get("CLICKY_WORKER_PORT", "40002")
    try:
        port = int(raw_port)
    except ValueError:
        port = 40002

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("clicky worker adapter on :%s (upstream %s)", port, _upstream_worker_url())
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
