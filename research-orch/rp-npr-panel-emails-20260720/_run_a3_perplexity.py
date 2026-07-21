"""One-shot Perplexity research for NPR panel contact emails (A3)."""
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
Find the best-supported professional email addresses or contact paths for these three NPR people, for a candidate thank-you after an AI Research Ethics & Readiness panel interview. Do NOT invent addresses. Only report emails that appear in public sources, or clearly label pattern-based inferences as unverified.

People:
1) Greta Pittenger — Research, Archives & Data Strategy (RAD), NPR. NPR people page: https://www.npr.org/people/g-s1-111855/greta-pittenger ; LinkedIn: gretapittenger
2) Nicolette Khan — Research, Archives & Data Strategy (RAD), NPR. LinkedIn: nicolette-khan-889393109
3) Kriti Singh — AI Labs, NPR. LinkedIn: kritisinghh ; GitHub: kritisgh

Also document NPR @npr.org email naming patterns from public evidence (e.g. firstname.lastname vs first-initial+lastname). Prior signal only (not for these three): Ben Raynor reportedly used braynor@npr.org.

For each person return:
- Best public contact path (email if found, else LinkedIn / shared inbox / recruiter)
- Confidence: verified | directory-claim | pattern-inference | none
- Exact source URLs
- Contradictions

Prefer primary sources (NPR.org, conference bios, academic pages, GitHub) over paywalled people-finder blurbs. If RocketReach/Hunter only show masked emails, say so and do not expand the mask into a guessed full address.
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
        "category": "interview_prep",
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
            raw["odysseus_error"] = odysseus
        except Exception as e:
            raw = {**odysseus, "direct_error": f"{type(e).__name__}: {e}"}
    elif odysseus and odysseus.get("ok") is False and odysseus.get("odysseus_route") in {"unreachable", None}:
        try:
            raw = await try_direct_perplexity()
        except Exception as e:
            raw = {"ok": False, "engine": "perplexity_agent", "error": str(e)}
    else:
        try:
            raw = await try_direct_perplexity()
            if odysseus:
                raw["odysseus_error"] = odysseus
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
