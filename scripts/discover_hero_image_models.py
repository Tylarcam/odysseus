#!/usr/bin/env python3
"""Discover open-source text-to-image models for Deep Research hero images.

Cross-references the Odysseus hwfit image registry with an optional Firecrawl
web search for recent OSS models. Does not modify any config files.

Usage:
  python scripts/discover_hero_image_models.py
  python scripts/discover_hero_image_models.py --no-firecrawl
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RECOMMENDED_IDS = (
    "Tongyi-MAI/Z-Image-Turbo",
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-3.5-medium",
)


def _registry_models():
    import importlib.util

    path = ROOT / "services" / "hwfit" / "image_models.py"
    spec = importlib.util.spec_from_file_location("odysseus_image_models", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load registry from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    registry = mod.IMAGE_MODEL_REGISTRY
    rows = []
    for entry in registry:
        if "text-to-image" not in entry.get("capabilities", []):
            continue
        rows.append(entry)
    return rows


def _firecrawl_hits(query: str, limit: int = 8) -> list[str]:
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        try:
            from src.settings import load_settings
            api_key = load_settings().get("firecrawl_api_key") or ""
        except Exception:
            api_key = ""

    if not api_key:
        return []

    try:
        from services.search.providers import firecrawl_search
    except Exception as exc:
        print(f"Firecrawl import failed: {exc}", file=sys.stderr)
        return []

    hits = []
    try:
        for row in firecrawl_search(query, count=limit):
            title = (row.get("title") or "").strip()
            url = (row.get("url") or "").strip()
            snippet = (row.get("snippet") or row.get("description") or "").strip()
            line = " — ".join(p for p in (title, snippet, url) if p)
            if line:
                hits.append(line[:240])
    except Exception as exc:
        print(f"Firecrawl search failed: {exc}", file=sys.stderr)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-firecrawl",
        action="store_true",
        help="Skip Firecrawl web search (registry only)",
    )
    args = parser.parse_args()

    registry = _registry_models()
    by_id = {m["id"]: m for m in registry}

    print("=== Odysseus hero image model discovery ===\n")
    print("Recommended local models (Cookbook -> Serve):")
    for repo_id in RECOMMENDED_IDS:
        entry = by_id.get(repo_id)
        if not entry:
            print(f"  - {repo_id} (not in registry)")
            continue
        vram = entry.get("vram_fp8") or entry.get("vram_bf16") or "?"
        print(
            f"  - {repo_id}\n"
            f"      {entry.get('name')} | ~{vram} GB VRAM ({entry.get('default_quant', 'BF16')})\n"
            f"      {entry.get('description', '')}"
        )

    print("\nAll registry text-to-image models:")
    for entry in sorted(registry, key=lambda m: (-(m.get("quality") or 0), m.get("id", ""))):
        vram = entry.get("vram_fp8") or entry.get("vram_bf16") or "?"
        print(f"  - {entry['id']} (~{vram} GB)")

    if not args.no_firecrawl:
        print("\nFirecrawl search (optional):")
        query = "free open source text-to-image models 2026 huggingface apache flux z-image"
        hits = _firecrawl_hits(query)
        if not hits:
            print("  (no results — set FIRECRAWL_API_KEY or firecrawl_api_key in settings)")
        else:
            for i, hit in enumerate(hits, 1):
                print(f"  {i}. {hit}")

    print(
        "\nNext steps:\n"
        "  1. Set HF_TOKEN for gated downloads\n"
        "  2. Cookbook -> download + serve a model above\n"
        "  3. Admin -> Image Generation: confirm image_gen_enabled\n"
        "  4. Run Deep Research — hero image generates after completion\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
