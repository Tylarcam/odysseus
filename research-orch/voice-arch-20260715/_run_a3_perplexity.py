"""One-shot Perplexity research for voice-arch A3 leg."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", encoding="utf-8-sig")

import os  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
RAW_PATH = OUT_DIR / "a3_perplexity_raw.json"

QUERY = """
For a vault-style command center that already uses:
- OpenAI Realtime WebRTC (whisper-1 input transcription)
- Jarvis agent bridge (cancel Realtime reply → text agent loop → TTS)
- Fallbacks: browser Web Speech, local faster-whisper stream/batch
- Mic lease vs other apps

What is the optimal architecture to eliminate friction AT THE TRANSCRIPTION HOP — single happy path, clear fallbacks, turn-taking, empty speech handling — without a greenfield rewrite?

Compare patterns from:
1) Perplexity-class voice UX (voice/comet-style assistants)
2) Jarvis-like ambient assistants
3) Whisper / faster-whisper production pipelines
4) OpenAI Realtime API (input_audio_transcription, turn detection, semantic VAD)
5) Cascaded STT→LLM→TTS vs speech-to-speech (LiveKit Agents, Pipecat)

Focus on transcription hop optimization for an existing stack. Provide:
- Canonical happy-path pipeline (mic → VAD → STT → turn commit → agent)
- How to unify 3 parallel STT modes into one primary + explicit fallbacks
- Turn-taking, partial transcripts, empty/no-speech handling
- Barge-in and mic lease patterns
- Concrete optimization checklist ordered by ROI

Cite authoritative sources (OpenAI docs, LiveKit/Pipecat, Deepgram voice agent architecture, Whisper streaming patterns).
""".strip()


async def try_odysseus_route() -> dict | None:
    base = (os.environ.get("ODYSSEUS_URL") or "http://localhost:7000").rstrip("/")
    token = (os.environ.get("ODYSSEUS_API_TOKEN") or "").strip()
    if not token:
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": QUERY,
        "research_engine": "perplexity_agent",
        "category": "howto",
        "max_time": 600,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        try:
            start = await client.post(f"{base}/api/research/start", headers=headers, json=payload)
        except Exception as e:
            return {"ok": False, "engine": "perplexity_agent", "odysseus_route": "unreachable", "error": str(e)}

        if start.status_code >= 400:
            return {
                "ok": False,
                "engine": "perplexity_agent",
                "odysseus_route": "start_failed",
                "status_code": start.status_code,
                "error": start.text[:500],
            }

        session_id = start.json().get("session_id")
        if not session_id:
            return {"ok": False, "engine": "perplexity_agent", "odysseus_route": "no_session_id", "error": start.text}

        deadline = time.time() + 600
        last_status = {}
        while time.time() < deadline:
            await asyncio.sleep(2)
            try:
                st = await client.get(f"{base}/api/research/status/{session_id}", headers=headers)
            except Exception as e:
                return {
                    "ok": False,
                    "engine": "perplexity_agent",
                    "odysseus_route": "poll_failed",
                    "session_id": session_id,
                    "error": str(e),
                }
            if st.status_code >= 400:
                continue
            last_status = st.json()
            if last_status.get("status") in {"done", "error", "cancelled"}:
                break

        peek = await client.post(f"{base}/api/research/result-peek/{session_id}", headers=headers)
        if peek.status_code >= 400:
            return {
                "ok": False,
                "engine": "perplexity_agent",
                "odysseus_route": "result_failed",
                "session_id": session_id,
                "status": last_status,
                "error": peek.text[:500],
            }
        body = peek.json()
        return {
            "ok": last_status.get("status") == "done",
            "engine": "perplexity_agent",
            "odysseus_route": "api",
            "session_id": session_id,
            "status": last_status,
            "result": body,
        }


async def try_direct_perplexity() -> dict:
    from src.perplexity_agent import get_api_key, run_deep_research

    key = get_api_key()
    if not key:
        return {"ok": False, "engine": "perplexity_agent_direct", "error": "no_perplexity_key"}

    parsed = await run_deep_research(QUERY, preset="pro-search", timeout=600)
    return {
        "ok": True,
        "engine": "perplexity_agent_direct",
        "odysseus_route": "fallback_direct",
        "preset": "pro-search",
        "result": parsed,
    }


async def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    raw: dict
    odysseus = await try_odysseus_route()
    if odysseus and odysseus.get("ok"):
        raw = odysseus
    elif odysseus and odysseus.get("odysseus_route") == "start_failed" and odysseus.get("status_code") == 403:
        try:
            raw = await try_direct_perplexity()
        except Exception as e:
            raw = {**odysseus, "direct_error": f"{type(e).__name__}: {e}"}
    elif odysseus and odysseus.get("ok") is False and odysseus.get("odysseus_route") in {"unreachable", None}:
        try:
            raw = await try_direct_perplexity()
        except Exception as e:
            raw = {"ok": False, "engine": "perplexity_agent", "error": str(e)}
    elif odysseus and odysseus.get("ok"):
        raw = odysseus
    else:
        try:
            raw = await try_direct_perplexity()
        except Exception as e:
            raw = odysseus or {"ok": False, "engine": "perplexity_agent", "error": str(e)}
            raw["direct_error"] = f"{type(e).__name__}: {e}"

    RAW_PATH.write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")
    print(f"SAVED {RAW_PATH}")
    print(f"OK {raw.get('ok')} ENGINE {raw.get('engine')} ROUTE {raw.get('odysseus_route')}")
    report = ""
    if isinstance(raw.get("result"), dict):
        inner = raw["result"]
        report = inner.get("report") or inner.get("result") or ""
        if isinstance(report, dict):
            report = report.get("result", "")
    print(f"REPORT_LEN {len(str(report))}")
    return 0 if raw.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
