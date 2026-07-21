#!/usr/bin/env python3
"""Probe Odysseus model endpoints — chat + tool-calling smoke test.

Prefer running inside Docker (decrypted keys + same runtime as tasks):

    .\\scripts\\test-endpoints-docker.ps1

Or: docker exec odysseus-odysseus-1 python scripts/test-endpoints.py

Host-side direct probes need the project venv and may still 401 if keys
cannot be decrypted outside the container.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "app.db"
BASE = "http://127.0.0.1:7000"

sys.path.insert(0, str(ROOT))


def decrypt_key(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        from src.secret_storage import decrypt

        return decrypt(raw)
    except Exception:
        return raw

MODELS_TO_TEST = [
    "llama-3.3-70b-versatile",
    "qwen/qwen3-32b",
    "openai/gpt-oss-120b",
]


def load_endpoints() -> list[dict]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, base_url, api_key, is_enabled, cached_models "
        "FROM model_endpoints WHERE is_enabled=1 ORDER BY name"
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def chat_url(base: str) -> str:
    base = (base or "").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def probe_chat(base: str, api_key: str | None, model: str, *, tools: bool = False) -> dict:
    url = chat_url(base)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Reply briefly."},
            {"role": "user", "content": "Say OK only."},
        ],
        "max_tokens": 32,
        "temperature": 0,
    }
    if tools:
        payload["tools"] = [{
            "type": "function",
            "function": {
                "name": "ping",
                "description": "Health check",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        payload["tool_choice"] = "auto"
    t0 = time.time()
    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        ms = round((time.time() - t0) * 1000)
        body = {}
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:300]}
        choice = (body.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = (msg.get("content") or "").strip()
        tool_calls = msg.get("tool_calls") or []
        err = body.get("error")
        return {
            "ok": r.is_success and (bool(content) or bool(tool_calls)),
            "status": r.status_code,
            "latency_ms": ms,
            "content": content[:120],
            "tool_calls": len(tool_calls),
            "error": (err.get("message") if isinstance(err, dict) else err) if err else None,
        }
    except Exception as e:
        return {"ok": False, "status": 0, "latency_ms": round((time.time() - t0) * 1000), "error": str(e)[:200]}


def probe_odysseus_api(ep_id: str, model: str) -> dict:
    """Use Odysseus /api/models/probe-selected if server is up."""
    try:
        r = httpx.post(
            f"{BASE}/api/models/probe-selected",
            json={"models": [{"endpoint_id": ep_id, "model": model}]},
            timeout=60.0,
        )
        if r.status_code == 401:
            return {"ok": None, "note": "Odysseus API requires auth — direct probe used instead"}
        return {"ok": r.is_success, "status": r.status_code, "body": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def main() -> int:
    if not DB.exists():
        print(f"DB not found: {DB}", file=sys.stderr)
        return 1

    print(f"Odysseus DB: {DB}")
    print(f"Odysseus URL: {BASE}\n")

    try:
        ping = httpx.get(BASE, timeout=5.0)
        print(f"Odysseus HTTP: {ping.status_code}\n")
    except Exception as e:
        print(f"Odysseus not reachable at {BASE}: {e}\n")

    endpoints = load_endpoints()
    if not endpoints:
        print("No enabled endpoints in DB.")
        return 1

    groq = next((e for e in endpoints if "groq" in (e.get("base_url") or "").lower()), None)
    if groq:
        print(f"=== Groq endpoint: {groq['name']} ({groq['id']}) ===")
        cached = []
        try:
            cached = json.loads(groq.get("cached_models") or "[]")
        except Exception:
            pass
        for model in MODELS_TO_TEST:
            if cached and model not in cached:
                print(f"  skip {model} (not in cached_models)")
                continue
            key = decrypt_key(groq.get("api_key"))
            plain = probe_chat(groq["base_url"], key, model, tools=False)
            tools = probe_chat(groq["base_url"], key, model, tools=True)
            flag = "PASS" if plain.get("ok") and tools.get("ok") else "FAIL"
            print(f"  [{flag}] {model}")
            print(f"       chat:  {plain}")
            print(f"       tools: {tools}")
            api = probe_odysseus_api(groq["id"], model)
            if api.get("note") or api.get("body"):
                print(f"       odysseus probe-selected: {api}")
        print()

    for ep in endpoints:
        if groq and ep["id"] == groq["id"]:
            continue
        print(f"=== {ep['name']} ({ep['id']}) ===")
        print(f"    {ep['base_url']}")
        cached = []
        try:
            cached = json.loads(ep.get("cached_models") or "[]")
        except Exception:
            pass
        test_model = None
        for m in cached:
            if any(x in m.lower() for x in ("llama-3.3", "glm-5.2", "glm-5.1", "gpt-oss-120b", "qwen3-32b")):
                test_model = m
                break
        if not test_model and cached:
            test_model = cached[0]
        if not test_model:
            print("    (no cached models — skipping chat probe)\n")
            continue
        plain = probe_chat(ep["base_url"], decrypt_key(ep.get("api_key")), test_model, tools=False)
        print(f"    sample model {test_model}: {plain}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
