"""Smoke-test Perplexity APIs used by Odysseus research.

1. Sonar (OpenAI-compatible) — fast API-key check, same as:

       from openai import OpenAI
       client = OpenAI(api_key=..., base_url="https://api.perplexity.ai")
       client.chat.completions.create(model="sonar-pro", messages=[...])

2. Agent API — pro-search preset with the shorter teaching-jobs prompt.

Usage:
    python scripts/test_perplexity_pro_search.py           # both steps
    python scripts/test_perplexity_pro_search.py --quick # Sonar only (~10s)
    python scripts/test_perplexity_pro_search.py --agent # Agent pro-search only
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", encoding="utf-8-sig")

SHORT_QUERY = """\
Find **15-20 US-remote online teaching/tutoring platforms** hiring in 2026 for someone with a **STEM background and no K-12 teaching license**. Include EdTech tutors, marketplaces (Outschool, Wyzant, Varsity Tutors, Cambly, Chegg), and STEM-relevant higher-ed adjunct paths. Exclude scams and license-only K-12 roles unless noted as "license required."

Return a markdown table: name | type (W-2/1099/gig) | license_required | pay_range | application_url | status | fit_score_1-5 | notes.

Verify URLs from official careers/apply pages. Use "unknown" when pay or requirements are not published."""


async def test_sonar() -> int:
    from src.perplexity_agent import get_api_key, verify_sonar_api_key

    key = get_api_key()
    if not key:
        print("FAIL [sonar]: No PERPLEXITY_API_KEY in .env or settings")
        return 1

    print(f"[sonar] API key: {key[:8]}...{key[-4:]}")
    print("[sonar] POST https://api.perplexity.ai/chat/completions model=sonar-pro")
    try:
        result = await verify_sonar_api_key()
    except Exception as e:
        print(f"FAIL [sonar]: {e}")
        return 1

    print("OK [sonar]")
    print("  Reply:", (result.get("message") or "")[:200])
    print("  Cost USD:", result.get("total_cost_usd"))
    return 0


async def test_agent_pro_search() -> int:
    from src.perplexity_agent import get_api_key, run_deep_research

    if not get_api_key():
        print("FAIL [agent]: No PERPLEXITY_API_KEY configured")
        return 1

    print("[agent] POST https://api.perplexity.ai/v1/agent preset=pro-search")
    print("[agent] Query length:", len(SHORT_QUERY), "chars")
    try:
        parsed = await run_deep_research(SHORT_QUERY, preset="pro-search", timeout=600)
    except Exception as e:
        print(f"FAIL [agent]: {type(e).__name__}: {e}")
        return 1

    report = parsed.get("report") or ""
    rows = [
        line
        for line in report.splitlines()
        if line.startswith("|") and "---" not in line and "name" not in line.lower()
    ]

    print("OK [agent]")
    print("  Stats:", parsed.get("stats"))
    print("  Sources:", len(parsed.get("sources") or []))
    print("  Cost USD:", parsed.get("total_cost_usd"))
    print("  Table rows (approx):", len(rows))
    print()
    preview = report[:3500]
    print(preview)
    if len(report) > 3500:
        print("...[truncated]")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="Perplexity API smoke tests")
    parser.add_argument("--quick", action="store_true", help="Sonar key check only")
    parser.add_argument("--agent", action="store_true", help="Agent pro-search only")
    args = parser.parse_args()

    run_sonar = args.quick or not args.agent
    run_agent = args.agent or not args.quick

    code = 0
    if run_sonar:
        code = await test_sonar()
        if code != 0:
            return code
        print()

    if run_agent:
        code = await test_agent_pro_search()

    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
