#!/usr/bin/env python3
"""Standalone embedding worker run under the Python 3.12 interpreter.

Invoked by ``tools.embed_incremental.embed_items_subprocess`` with:
    --items-json <path to JSON list of chunk items>
    --output-npz  <path to write>
    --model       <huggingface model id>
    --device      <auto|cpu|mps|cuda>

Imports ``pixelrag_embed.embed_cpu.embed_items`` and saves the resulting npz
with the exact keys ``pixelrag build-index build`` expects:
    embeddings (float16, N x D), article_ids (int64), tile_indices (int32),
    chunk_indices (int32), y_offsets (int32), tile_heights (int32).

This file is intentionally minimal and has no dependency on the repo's tools
package so it can run standalone under any interpreter that has pixelrag_embed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description="Embed a JSON list of chunk items.")
    parser.add_argument("--items-json", required=True)
    parser.add_argument("--output-npz", required=True)
    parser.add_argument("--model", default="Qwen/Qwen3-VL-Embedding-2B")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    items = json.loads(Path(args.items_json).read_text(encoding="utf-8"))
    if not items:
        raise SystemExit("No items to embed.")

    from pixelrag_embed.embed_cpu import embed_items

    embeddings = embed_items(items, args.model, device=args.device)

    out_path = Path(args.output_npz)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        out_path,
        embeddings=embeddings.astype(np.float16),
        article_ids=np.array([int(it["article_id"]) for it in items], dtype=np.int64),
        tile_indices=np.array([int(it["tile_index"]) for it in items], dtype=np.int32),
        chunk_indices=np.array([int(it["chunk_index"]) for it in items], dtype=np.int32),
        y_offsets=np.array([int(it["y_offset"]) for it in items], dtype=np.int32),
        tile_heights=np.array([int(it["height"]) for it in items], dtype=np.int32),
    )
    print(f"Saved {len(items)} embeddings to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
