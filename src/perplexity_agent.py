"""Perplexity Agent API client — Fast Deep Research (Search-as-Code backend).

Uses POST https://api.perplexity.ai/v1/agent with the ``deep-research`` preset
(or another configured preset). See:
https://docs.perplexity.ai/docs/agent-api/quickstart
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx

_RETRY_EXCEPTIONS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.NetworkError,
)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5.0

logger = logging.getLogger(__name__)

PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
AGENT_URL = f"{PERPLEXITY_BASE_URL}/v1/agent"
CHAT_COMPLETIONS_URL = f"{PERPLEXITY_BASE_URL}/chat/completions"
USAGE_FILE = Path(__file__).resolve().parent.parent / "data" / "perplexity_usage.json"


def get_api_key() -> str:
    from src.settings import get_setting

    return (
        (get_setting("perplexity_api_key") or "").strip()
        or (os.environ.get("PERPLEXITY_API_KEY") or "").strip()
    )


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_usage() -> dict:
    try:
        if USAGE_FILE.exists():
            data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning("Failed to read Perplexity usage file: %s", e)
    return {}


def _save_usage(data: dict) -> None:
    try:
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        USAGE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write Perplexity usage file: %s", e)


def get_daily_spend() -> float:
    data = _load_usage()
    day = data.get(_today_key()) or {}
    try:
        return float(day.get("total_usd", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def record_spend(amount_usd: float) -> None:
    if amount_usd <= 0:
        return
    data = _load_usage()
    key = _today_key()
    day = dict(data.get(key) or {})
    day["total_usd"] = round(float(day.get("total_usd", 0) or 0) + amount_usd, 6)
    day["calls"] = int(day.get("calls", 0) or 0) + 1
    data[key] = day
    _save_usage(data)


def check_budget() -> Optional[str]:
    from src.settings import get_setting

    try:
        budget = float(get_setting("perplexity_daily_budget_usd", 0) or 0)
    except (TypeError, ValueError):
        budget = 0.0
    if budget <= 0:
        return None
    spent = get_daily_spend()
    if spent >= budget:
        return (
            f"Perplexity daily budget reached (${spent:.2f} / ${budget:.2f}). "
            "Raise perplexity_daily_budget_usd in Settings or try again tomorrow."
        )
    return None


async def verify_sonar_api_key(
    *,
    model: str = "sonar-pro",
    timeout: float = 60.0,
) -> dict:
    """Quick Sonar chat completion — OpenAI-compatible key check.

    Same endpoint as ``OpenAI(base_url='https://api.perplexity.ai').chat.completions``.
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "Perplexity API key not configured. Set PERPLEXITY_API_KEY in .env or "
            "perplexity_api_key in Settings → Research."
        )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": "Respond with a short sentence so I can test my API key.",
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0)) as client:
        resp = await client.post(CHAT_COMPLETIONS_URL, headers=headers, json=payload)

    if resp.status_code >= 400:
        detail = resp.text[:500]
        try:
            err_body = resp.json()
            if isinstance(err_body, dict):
                detail = err_body.get("error") or err_body.get("message") or detail
        except Exception:
            pass
        raise RuntimeError(f"Perplexity Sonar API error ({resp.status_code}): {detail}")

    body = resp.json()
    if not isinstance(body, dict):
        raise RuntimeError("Perplexity Sonar returned an unexpected response shape")

    choices = body.get("choices") or []
    message = ""
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        if isinstance(msg, dict):
            message = (msg.get("content") or "").strip()

    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    cost = usage.get("cost") if isinstance(usage.get("cost"), dict) else {}
    total_cost = cost.get("total_cost")
    try:
        total_cost_usd = float(total_cost) if total_cost is not None else 0.0
    except (TypeError, ValueError):
        total_cost_usd = 0.0

    return {
        "ok": True,
        "model": model,
        "message": message,
        "total_cost_usd": total_cost_usd,
        "usage": usage,
    }


def parse_agent_response(body: dict, *, preset: str) -> dict:
    """Turn an Agent API JSON body into report, sources, findings, and stats."""
    output = body.get("output") or []
    report_parts: List[str] = []
    all_results: List[dict] = []
    queries: List[str] = []

    for item in output:
        if not isinstance(item, dict):
            continue
        typ = item.get("type")
        if typ == "search_results":
            for q in item.get("queries") or []:
                if isinstance(q, str) and q.strip():
                    queries.append(q.strip())
            for r in item.get("results") or []:
                if isinstance(r, dict) and (r.get("url") or "").strip():
                    all_results.append(r)
        elif typ == "message":
            for block in item.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "output_text":
                    text = (block.get("text") or "").strip()
                    if text:
                        report_parts.append(text)

    sources: List[dict] = []
    findings: List[dict] = []
    seen: set[str] = set()
    for r in all_results:
        url = (r.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        title = (r.get("title") or url).strip()
        snippet = (r.get("snippet") or "").strip()
        sources.append({"url": url, "title": title})
        if snippet:
            findings.append({"url": url, "title": title, "summary": snippet[:2000]})

    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    cost = usage.get("cost") if isinstance(usage.get("cost"), dict) else {}
    total_cost = cost.get("total_cost")
    try:
        total_cost_usd = float(total_cost) if total_cost is not None else 0.0
    except (TypeError, ValueError):
        total_cost_usd = 0.0

    stats = {
        "Engine": "Perplexity Agent",
        "Preset": preset,
        "Queries": len(queries) or len({r.get("url") for r in all_results if r.get("url")}),
        "URLs": len(sources),
        "Rounds": 1,
    }
    if total_cost_usd:
        stats["Cost USD"] = f"${total_cost_usd:.4f}"

    report = "\n\n".join(report_parts).strip()
    return {
        "report": report,
        "sources": sources,
        "findings": findings,
        "stats": stats,
        "total_cost_usd": total_cost_usd,
        "response_id": body.get("id"),
    }


async def run_deep_research(
    query: str,
    *,
    preset: Optional[str] = None,
    timeout: int = 600,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Run one Perplexity Agent deep-research job and return parsed results."""
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "Perplexity API key not configured. Set PERPLEXITY_API_KEY in .env or "
            "perplexity_api_key in Settings → Research."
        )

    budget_err = check_budget()
    if budget_err:
        raise RuntimeError(budget_err)

    from src.settings import get_setting

    preset = (preset or get_setting("perplexity_research_preset") or "deep-research").strip()
    if progress_callback:
        progress_callback({
            "phase": "searching",
            "message": f"Perplexity Agent ({preset})…",
            "provider": "perplexity",
            "model": f"perplexity/{preset}",
        })

    payload = {"preset": preset, "input": query}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(float(timeout), connect=60.0)) as client:
        last_exc: Optional[Exception] = None
        resp = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.post(AGENT_URL, headers=headers, json=payload)
                break
            except _RETRY_EXCEPTIONS as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Perplexity Agent connection error (attempt %d/%d): %s — retrying in %.0fs",
                        attempt + 1, _MAX_RETRIES, exc, delay,
                    )
                    if progress_callback:
                        progress_callback({
                            "phase": "retrying",
                            "message": f"Connection error — retrying ({attempt + 1}/{_MAX_RETRIES})…",
                            "provider": "perplexity",
                        })
                    await asyncio.sleep(delay)
        if resp is None:
            raise RuntimeError(
                f"Perplexity Agent disconnected after {_MAX_RETRIES} attempts: {last_exc}"
            ) from last_exc

    if resp.status_code >= 400:
        detail = resp.text[:500]
        try:
            err_body = resp.json()
            if isinstance(err_body, dict):
                detail = err_body.get("error") or err_body.get("message") or detail
        except Exception:
            pass
        raise RuntimeError(f"Perplexity Agent API error ({resp.status_code}): {detail}")

    body = resp.json()
    if not isinstance(body, dict):
        raise RuntimeError("Perplexity Agent returned an unexpected response shape")

    if body.get("status") == "failed" or body.get("error"):
        raise RuntimeError(f"Perplexity Agent failed: {body.get('error') or body.get('status')}")

    parsed = parse_agent_response(body, preset=preset)
    if parsed["total_cost_usd"]:
        record_spend(parsed["total_cost_usd"])

    if progress_callback:
        progress_callback({"phase": "done", "message": "Research complete"})

    if not parsed["report"]:
        raise RuntimeError("Perplexity Agent returned no report text")

    logger.info(
        "Perplexity Agent completed: preset=%s sources=%s cost=$%.4f id=%s",
        preset,
        len(parsed["sources"]),
        parsed["total_cost_usd"],
        parsed.get("response_id"),
    )
    return parsed


def resolve_research_engine(explicit: Optional[str] = None) -> str:
    """Return ``iterative`` or ``perplexity_agent``."""
    raw = (explicit or "").strip()
    if not raw:
        from src.settings import get_setting

        raw = (get_setting("research_engine") or "iterative").strip()
    if raw in ("perplexity", "perplexity_agent", "agent"):
        return "perplexity_agent"
    return "iterative"
