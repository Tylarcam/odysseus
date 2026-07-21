#!/usr/bin/env python3
"""Run inside Odysseus container: probe enabled endpoints (chat + tools)."""

from __future__ import annotations

import json
import sys

from core.database import SessionLocal, ModelEndpoint
from routes.model_routes import _probe_single_model, _resolve_probe_key

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "qwen/qwen3-32b",
    "openai/gpt-oss-120b",
]


def main() -> int:
    db = SessionLocal()
    eps = db.query(ModelEndpoint).filter(ModelEndpoint.is_enabled == True).all()
    print("Endpoint probe (inside container)\n")
    any_fail = False
    for ep in eps:
        base = ep.base_url or ""
        key = _resolve_probe_key(ep)
        print(f"=== {ep.name} ({ep.id}) ===")
        print(f"    {base}")
        if "groq" in base.lower():
            for m in GROQ_MODELS:
                chat = _probe_single_model(base, key, m, timeout=20, with_tools=False)
                tools = _probe_single_model(base, key, m, timeout=20, with_tools=True)
                ok = chat.get("status") == "ok" and tools.get("status") == "ok"
                if not ok:
                    any_fail = True
                flag = "PASS" if ok else "FAIL"
                print(f"  [{flag}] {m}")
                print(f"       chat:  {chat}")
                print(f"       tools: {tools}")
        else:
            cached = json.loads(ep.cached_models or "[]") if ep.cached_models else []
            sample = cached[0] if cached else None
            if sample:
                r = _probe_single_model(base, key, sample, timeout=15, with_tools=False)
                if r.get("status") != "ok":
                    any_fail = True
                print(f"    sample {sample}: {r}")
        print()
    db.close()
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
