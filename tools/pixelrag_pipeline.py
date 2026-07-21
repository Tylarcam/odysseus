#!/usr/bin/env python3
"""Chunk, embed, and build a PixelRAG FAISS index from archivist tile dirs."""

from __future__ import annotations

import argparse
import json
import logging
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from tools.memory_stack_env import load_memory_stack_env, repo_root, resolve_path

logger = logging.getLogger("pixelrag_pipeline")


def _python_has_pixelrag_embed(python_exe: str) -> bool:
    try:
        subprocess.run(
            [python_exe, "-c", "import pixelrag_embed"],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def resolve_pixelrag_python() -> str:
    """Return a Python executable that has pixelrag_embed installed."""
    env = load_memory_stack_env()
    configured = env.get("PIXELRAG_PYTHON", "").strip()
    if configured and _python_has_pixelrag_embed(configured):
        return configured

    if _python_has_pixelrag_embed(sys.executable):
        return sys.executable

    pixelrag_exe = shutil.which("pixelrag")
    if pixelrag_exe:
        scripts_dir = Path(pixelrag_exe).resolve().parent
        candidates = [
            scripts_dir / "python.exe",
            scripts_dir.parent / "python.exe",
        ]
        for candidate in candidates:
            if candidate.is_file() and _python_has_pixelrag_embed(str(candidate)):
                return str(candidate)

    raise RuntimeError(
        "pixelrag_embed is not installed for the active Python interpreter. "
        "Either run: pip install \"pixelrag[embed,index,serve]\" "
        "or set PIXELRAG_PYTHON in memory_stack.env to the Python that has pixelrag."
    )


def _run_pixelrag_cli(args: List[str]) -> None:
    pixelrag_exe = shutil.which("pixelrag")
    if not pixelrag_exe:
        raise RuntimeError("pixelrag CLI not found on PATH")
    subprocess.run([pixelrag_exe, *args], check=True)


def _load_embed_settings() -> Dict[str, str]:
    env = load_memory_stack_env()
    model = env.get("PIXELRAG_EMBED_MODEL", "Qwen/Qwen3-VL-Embedding-2B")
    device = env.get("PIXELRAG_EMBED_DEVICE", "auto")
    yaml_path = repo_root() / "pixelrag.yaml"
    if yaml_path.is_file():
        try:
            import yaml

            cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            embed = cfg.get("embed") or {}
            if isinstance(embed, dict):
                model = str(embed.get("model") or model)
                device = str(embed.get("device") or device)
        except Exception as exc:
            logger.warning("Could not parse pixelrag.yaml: %s", exc)
    return {"model": model, "device": device}


def _count_tile_articles(tiles_dir: Path) -> int:
    if not tiles_dir.is_dir():
        return 0
    return sum(1 for p in tiles_dir.iterdir() if p.is_dir() and p.name.endswith(".png.tiles"))


def _count_chunks(tiles_dir: Path) -> int:
    """Count embeddable chunk images (mirrors pixelrag_embed scan logic)."""
    total = 0
    for article_dir in tiles_dir.iterdir():
        if not article_dir.is_dir() or not article_dir.name.endswith(".png.tiles"):
            continue
        chunks_json = article_dir / "chunks.json"
        tiles_json = article_dir / "tiles.json"
        try:
            if chunks_json.is_file():
                manifest = json.loads(chunks_json.read_text(encoding="utf-8"))
                total += len(manifest.get("chunks", []))
            elif tiles_json.is_file():
                manifest = json.loads(tiles_json.read_text(encoding="utf-8"))
                total += len(manifest.get("tiles", []))
        except (OSError, json.JSONDecodeError):
            continue
    return total


def _pick_nlist(n_vectors: int) -> int:
    """FAISS IVF needs train points >= nlist; ~sqrt(n) clusters for small sets."""
    if n_vectors <= 0:
        return 1
    return max(1, min(4096, int(math.sqrt(n_vectors))))


def build_pixelrag_index(
    *,
    tiles_dir: Path | None = None,
    index_dir: Path | None = None,
    embeddings_dir: Path | None = None,
    device: str | None = None,
    model: str | None = None,
    force_full: bool = False,
) -> Path | None:
    """Run chunk -> (incremental) embed -> build-index for archivist tiles.

    By default embeds only chunks not already present in the embeddings dir
    (delegated to ``tools.embed_incremental.build_incremental_index``). When
    ``force_full`` is True, existing npz shards are removed and every chunk is
    re-embedded (the old behavior). Returns the index dir, or ``None`` when the
    index was already up to date and left untouched.
    """
    from tools.embed_incremental import build_incremental_index

    return build_incremental_index(
        tiles_dir=tiles_dir,
        index_dir=index_dir,
        embeddings_dir=embeddings_dir,
        device=device,
        model=model,
        force_full=force_full,
    )


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build PixelRAG FAISS index from archivist tiles")
    parser.add_argument("--tiles-dir", type=Path, default=None)
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument("--embeddings-dir", type=Path, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Delete existing npz shards and re-embed every chunk (skip incremental diff).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = build_pixelrag_index(
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
