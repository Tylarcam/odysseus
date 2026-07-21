"""One-shot Perplexity research for Hermes Agent setup A3 leg."""
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
Hermes Agent (Nous Research) setup step by step. Prefer official sources:
- https://hermes-agent.nousresearch.com/docs/
- https://github.com/NousResearch/hermes-agent

Cover with citations:
1) Official source of truth (docs site vs GitHub README)
2) Prerequisites (OS, Python/Node, API keys, accounts)
3) Install commands (exact commands from official docs)
4) First-run configuration (env vars, config files, auth)
5) MCP enablement (how to install/enable MCP servers in Hermes)
6) Blender MCP specifically: is `hermes mcp install blender` documented officially?
   Reconcile community/promo claims (e.g. Julian Goldie video) vs official docs.
7) Common failures and troubleshooting from official docs/issues
8) Cost model: what is free vs paid (Hermes itself, Nous API, model providers)
9) Alternatives and when NOT to use Hermes Agent

Do not invent product claims. Mark uncertainty. Cite URLs for each major claim.
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
            status = last_status.get("status")
            print(f"poll status={status} progress={last_status.get('progress')}", flush=True)
            if status in {"done", "error", "cancelled"}:
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
    else:
        print(f"odysseus failed: {json.dumps(odysseus, default=str)[:800]}", flush=True)
        try:
            raw = await try_direct_perplexity()
            if odysseus:
                raw["odysseus_attempt"] = {
                    k: odysseus.get(k)
                    for k in ("ok", "odysseus_route", "status_code", "error", "session_id")
                }
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
