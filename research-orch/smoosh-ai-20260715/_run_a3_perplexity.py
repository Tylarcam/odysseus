"""One-shot Perplexity Agent research for Smoosh AI identity correction."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", encoding="utf-8-sig")

from src.perplexity_agent import get_api_key, run_deep_research  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
RAW_PATH = OUT_DIR / "a3_perplexity_raw.json"

QUERY = """
CRITICAL IDENTITY CORRECTION: Research **Smoosh AI** (NOT smoosh.dev). Prior research wrongly equated them. smoosh.dev is a DIFFERENT UK calendar SaaS brand-collision — call out as NOT the target unless evidence links them.

Primary identity to reconcile:
1) Handshake recruiter Janice Nam → CTO role at "Smoosh AI"
2) LinkedIn https://www.linkedin.com/company/smooshai — fan data unification platform
3) GetLatka https://getlatka.com/companies/smoosh.app — Sophie Poultney founder/CEO, founded ~2025
4) Domain smoosh.app / product footprint

Synthesis questions (answer with citations):
- Who is Smoosh AI (fan-data / Sophie Poultney / LinkedIn smooshai)? What do they build (product thesis, ICP, jobs-to-be-done)?
- Official web / LinkedIn / social footprint (domains, founders, HQ)?
- Who is Sophie Poultney and any other leaders? How does Janice Nam fit (recruiter vs internal)?
- Stage/funding/team signals (founded year, funding, team size, Microsoft for Startups, pilots)?
- What should a CTO interview candidate assume about technical ownership (data/AI architecture, integrations, GTM tech)?
- Explicitly separate Smoosh AI from smoosh.dev calendar product.

Return a structured research report with sources.
""".strip()


async def main() -> int:
    key = get_api_key()
    if not key:
        RAW_PATH.write_text(
            json.dumps(
                {
                    "ok": False,
                    "engine": "perplexity_agent_direct",
                    "odysseus_route": "blocked_scope_aware",
                    "error": "no_perplexity_key",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("NO_KEY")
        return 1

    print(f"KEY {key[:6]}...{key[-4:]}")
    try:
        parsed = await run_deep_research(QUERY, preset="pro-search", timeout=600)
    except Exception as e:
        RAW_PATH.write_text(
            json.dumps(
                {
                    "ok": False,
                    "engine": "perplexity_agent_direct",
                    "odysseus_route": "blocked_scope_aware",
                    "error": f"{type(e).__name__}: {e}",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"FAIL {type(e).__name__}: {e}")
        return 1

    RAW_PATH.write_text(
        json.dumps(
            {
                "ok": True,
                "engine": "perplexity_agent_direct",
                "odysseus_route": "blocked_scope_aware_403",
                "preset": "pro-search",
                "result": parsed,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    report = (parsed or {}).get("report") or ""
    print(f"SAVED {RAW_PATH}")
    print(f"REPORT_LEN {len(report)}")
    print(report[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
