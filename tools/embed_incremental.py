#!/usr/bin/env python3
"""Incremental PixelRAG embedding for the archivist tile dirs.

``tools.pixelrag_pipeline.build_pixelrag_index`` previously re-embedded every
chunk on each run (~2h on CPU). This module makes embedding incremental:

1. Scan the tiles dir for chunk items (mirrors ``pixelrag_embed.embed_cpu.scan_chunks``
   in pure Python so it runs under the venv interpreter that does NOT have
   pixelrag_embed installed).
2. Load the id arrays (``article_ids``, ``tile_indices``, ``chunk_indices``) from
   every ``*.npz`` shard already in the embeddings dir and build a set of
   ``(article_id, tile_index, chunk_index)`` tuples that are already embedded.
3. The diff is the missing items. If empty -> print "up to date" and exit 0
   without touching the FAISS index.
4. Otherwise embed only the missing items into a NEW uniquely-named shard
   (``shard_001.npz``, ``shard_002.npz``, ...) via a subprocess running under the
   Python 3.12 interpreter that actually has pixelrag_embed installed
   (``resolve_pixelrag_python`` from ``tools.pixelrag_pipeline``). embed_cpu always
   writes to a fixed ``shard_000.npz`` and would overwrite prior work, so the
   worker writes a caller-chosen filename instead.
5. Rebuild the FAISS index. ``pixelrag build-index build`` merges and dedups all
   ``*.npz`` shards in ``--embeddings-dir``, and index rebuild is seconds at this
   scale (only embedding is slow).

article_id mapping note: ``tools.build_tiles`` assigns article_ids by sorted
screenshot filename order (chronological, stable as long as you only append
screenshots). If screenshots are ever DELETED, the filename->article_id mapping
shifts and a ``--force-full`` rebuild is required (the incremental diff would
otherwise leave stale embeddings pointing at the wrong articles).
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import numpy as np

from tools.memory_stack_env import load_memory_stack_env, resolve_path
from tools.pixelrag_pipeline import (
    _pick_nlist,
    _run_pixelrag_cli,
    resolve_pixelrag_python,
)

logger = logging.getLogger("embed_incremental")

# npz shard key names (must match pixelrag_embed.embed_cpu main() output).
_EMBED_KEY = "embeddings"
_ARTICLE_KEY = "article_ids"
_TILE_KEY = "tile_indices"
_CHUNK_KEY = "chunk_indices"
_Y_OFFSET_KEY = "y_offsets"
_HEIGHT_KEY = "tile_heights"


def _scan_chunks(tiles_dir: Path) -> List[Dict[str, Any]]:
    """Pure-Python port of pixelrag_embed.embed_cpu.scan_chunks.

    Iterates the tiles dir the same way (sorted, *.png.tiles dirs first, then
    nested subdirs that contain *.png.tiles) and emits the same item dicts so the
    incremental diff matches what embed_cpu would embed on a full run.
    """
    if not tiles_dir.is_dir():
        return []

    items: List[Dict[str, Any]] = []
    for entry in sorted(tiles_dir.iterdir()):
        if not entry.is_dir():
            continue

        if entry.name.endswith(".png.tiles"):
            tile_dirs = [entry]
        else:
            tile_dirs = sorted(
                d for d in entry.iterdir() if d.is_dir() and d.name.endswith(".png.tiles")
            )

        for td in tile_dirs:
            article_id_str = td.name.replace(".png.tiles", "")
            try:
                article_id = int(article_id_str)
            except ValueError:
                article_id = hash(article_id_str) % (2**31)

            chunks_json = td / "chunks.json"
            tiles_json = td / "tiles.json"

            if chunks_json.is_file():
                try:
                    manifest = json.loads(chunks_json.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    logger.warning("Could not read %s; skipping", chunks_json)
                    continue
                for chunk_info in manifest.get("chunks", []):
                    chunk_path = td / chunk_info["file"]
                    if chunk_path.exists():
                        items.append(
                            {
                                "path": str(chunk_path),
                                "article_id": article_id,
                                "tile_index": int(chunk_info.get("tile_index", 0)),
                                "chunk_index": int(chunk_info.get("chunk_index", 0)),
                                "y_offset": int(chunk_info.get("y_offset", 0)),
                                "height": int(chunk_info.get("height", 1024)),
                            }
                        )
            elif tiles_json.is_file():
                try:
                    manifest = json.loads(tiles_json.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    logger.warning("Could not read %s; skipping", tiles_json)
                    continue
                for i, tile_name in enumerate(manifest.get("tiles", [])):
                    tile_path = td / tile_name
                    if tile_path.exists():
                        items.append(
                            {
                                "path": str(tile_path),
                                "article_id": article_id,
                                "tile_index": i,
                                "chunk_index": 0,
                                "y_offset": 0,
                                "height": 0,
                            }
                        )
    return items


def _load_embedded_keys(embeddings_dir: Path) -> Set[Tuple[int, int, int]]:
    """Return the set of (article_id, tile_index, chunk_index) already embedded."""
    embedded: Set[Tuple[int, int, int]] = set()
    if not embeddings_dir.is_dir():
        return embedded

    for shard in sorted(embeddings_dir.glob("*.npz")):
        try:
            with np.load(shard, allow_pickle=False) as data:
                article_ids = data[_ARTICLE_KEY]
                tile_indices = data[_TILE_KEY]
                chunk_indices = data[_CHUNK_KEY]
        except (OSError, KeyError, ValueError) as exc:
            logger.warning("Could not read id arrays from %s: %s", shard, exc)
            continue

        if not (len(article_ids) == len(tile_indices) == len(chunk_indices)):
            logger.warning("Length mismatch in %s; skipping", shard)
            continue

        for art, tile, chunk in zip(article_ids, tile_indices, chunk_indices):
            embedded.add((int(art), int(tile), int(chunk)))
    return embedded


def find_missing_items(tiles_dir: Path, embeddings_dir: Path) -> List[Dict[str, Any]]:
    """Return chunk items that are not yet present in any embeddings shard."""
    all_items = _scan_chunks(tiles_dir)
    embedded = _load_embedded_keys(embeddings_dir)
    missing = [
        item
        for item in all_items
        if (item["article_id"], item["tile_index"], item["chunk_index"]) not in embedded
    ]
    return missing


def next_shard_path(embeddings_dir: Path) -> Path:
    """Return the first free shard_NNN.npz path under embeddings_dir."""
    embeddings_dir.mkdir(parents=True, exist_ok=True)
    existing = {p.name for p in embeddings_dir.glob("shard_*.npz")}
    n = 0
    while True:
        name = f"shard_{n:03d}.npz"
        if name not in existing:
            return embeddings_dir / name
        n += 1


def _embed_worker_path() -> Path:
    return Path(__file__).resolve().parent / "_embed_worker.py"


def embed_items_subprocess(
    items: List[Dict[str, Any]],
    output_npz: Path,
    *,
    model: str,
    device: str,
    python_exe: str | None = None,
) -> Path:
    """Embed items via the Python 3.12 worker (pixelrag_embed.embed_cpu.embed_items).

    Writes the npz shard with the exact keys pixelrag expects. Never call this in
    tests (real embedding takes hours); mock the subprocess instead.
    """
    interpreter = python_exe or resolve_pixelrag_python()
    items_json = output_npz.with_suffix(".items.json")
    items_json.parent.mkdir(parents=True, exist_ok=True)
    items_json.write_text(json.dumps(items), encoding="utf-8")

    cmd = [
        interpreter,
        str(_embed_worker_path()),
        "--items-json",
        str(items_json),
        "--output-npz",
        str(output_npz),
        "--model",
        model,
        "--device",
        device,
    ]
    logger.info("Embedding %d items -> %s via %s", len(items), output_npz, interpreter)
    subprocess.run(cmd, check=True)

    # Clean up the temp items manifest after success.
    try:
        items_json.unlink()
    except OSError:
        pass
    return output_npz


def build_incremental_index(
    *,
    tiles_dir: Path | None = None,
    index_dir: Path | None = None,
    embeddings_dir: Path | None = None,
    device: str | None = None,
    model: str | None = None,
    force_full: bool = False,
) -> Path | None:
    """Chunk -> (incremental) embed -> build FAISS index.

    Returns the index dir on success, or ``None`` when nothing needed embedding
    and the index was left untouched (the "up to date" case).
    """
    from tools.pixelrag_pipeline import _load_embed_settings, _count_chunks

    env = load_memory_stack_env()
    settings = _load_embed_settings()
    index_root = index_dir or resolve_path("PIXELRAG_INDEX_DIR", env=env)
    tiles_root = tiles_dir or resolve_path("PIXELRAG_TILES_DIR", env=env)
    if tiles_dir is None and tiles_root == resolve_path("PIXELRAG_TILES_DIR", env=env):
        tiles_root = index_root / "tiles"
    embed_root = embeddings_dir or resolve_path("PIXELRAG_EMBED_DIR", env=env)
    if embeddings_dir is None and embed_root == resolve_path("PIXELRAG_EMBED_DIR", env=env):
        embed_root = index_root / "embeddings"

    embed_root.mkdir(parents=True, exist_ok=True)

    embed_device = device or settings["device"]
    embed_model = model or settings["model"]

    # Chunk stage: pixelrag chunk skips articles that already have chunks.json.
    _run_pixelrag_cli(["chunk", "--shard-dir", str(tiles_root)])

    if force_full:
        logger.info("force_full: removing existing npz shards before full embed")
        for shard in embed_root.glob("*.npz"):
            try:
                shard.unlink()
            except OSError as exc:
                logger.warning("Could not delete %s: %s", shard, exc)
        missing = _scan_chunks(tiles_root)
    else:
        missing = find_missing_items(tiles_root, embed_root)

    if not missing:
        print("up to date")
        logger.info("No missing chunks; leaving FAISS index untouched.")
        return None

    out_npz = next_shard_path(embed_root)
    embed_items_subprocess(
        missing,
        out_npz,
        model=embed_model,
        device=embed_device,
    )

    n_chunks = _count_chunks(tiles_root)
    nlist = _pick_nlist(n_chunks)
    nprobe = max(1, min(nlist, 16))
    logger.info("Building FAISS index: %d chunks, nlist=%d, nprobe=%d", n_chunks, nlist, nprobe)
    _run_pixelrag_cli(
        [
            "build-index",
            "build",
            "--embeddings-dir",
            str(embed_root),
            "--output-dir",
            str(index_root),
            "--nlist",
            str(nlist),
            "--nprobe",
            str(nprobe),
        ]
    )
    return index_root


def main(argv: List[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Incrementally embed new archivist tile chunks and rebuild the FAISS index."
    )
    parser.add_argument("--tiles-dir", type=Path, default=None)
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument("--embeddings-dir", type=Path, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Delete existing npz shards and re-embed everything.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = build_incremental_index(
        tiles_dir=args.tiles_dir,
        index_dir=args.index_dir,
        embeddings_dir=args.embeddings_dir,
        device=args.device,
        model=args.model,
        force_full=args.force_full,
    )
    if out is None:
        return 0
    print(f"PixelRAG index built at {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
