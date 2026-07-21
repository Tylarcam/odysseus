#!/usr/bin/env python3
"""Materialize Screenpipe screenshots into PixelRAG-compatible tile directories."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from tools.memory_stack_env import load_memory_stack_env, resolve_path

_TIMESTAMP_RE = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[T_\s-]"
    r"(?P<hour>\d{2})-(?P<minute>\d{2})-(?P<second>\d{2})"
)


def _parse_timestamp_from_name(name: str) -> Optional[str]:
    match = _TIMESTAMP_RE.search(name)
    if not match:
        return None
    parts = match.groupdict()
    return (
        f"{parts['year']}-{parts['month']}-{parts['day']}T"
        f"{parts['hour']}:{parts['minute']}:{parts['second']}"
    )


def _load_transcript_index(transcripts_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Build a coarse index of transcript JSON files keyed by ISO date prefix."""
    index: Dict[str, Dict[str, Any]] = {}
    if not transcripts_dir.is_dir():
        return index

    for path in sorted(transcripts_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        ts = str(payload.get("timestamp") or payload.get("created_at") or path.stem)
        index[ts[:10]] = {
            "url": payload.get("url") or payload.get("browser_url") or "",
            "window_title": payload.get("window_title") or payload.get("title") or "",
            "transcript_path": str(path),
        }
    return index


def _match_transcript(
    screenshot_name: str,
    transcript_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    ts = _parse_timestamp_from_name(screenshot_name)
    if ts:
        day_key = ts[:10]
        if day_key in transcript_index:
            return dict(transcript_index[day_key])
    return {"url": "", "window_title": "", "transcript_path": ""}


def _iter_screenshots(screens_dir: Path) -> Iterable[Path]:
    if not screens_dir.is_dir():
        return []
    shots = list(screens_dir.glob("*.png")) + list(screens_dir.glob("*.jpg"))
    return sorted(shots)


def _image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.size
    except Exception:
        return 875, 600


def _write_article_tiles(
    source: Path,
    article_dir: Path,
    *,
    url: str = "",
) -> None:
    """Copy one screenshot into {N}.png.tiles/ with tiles.json for PixelRAG."""
    article_dir.mkdir(parents=True, exist_ok=True)
    tile_name = "tile_0000.png"
    dest = article_dir / tile_name
    shutil.copy2(source, dest)
    width, height = _image_size(dest)
    manifest = {
        "url": url,
        "page_height": height,
        "viewport_width": width,
        "tile_height": height,
        "tiles": [tile_name],
        "complete": True,
    }
    (article_dir / "tiles.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def build_tiles(
    *,
    screens_dir: Path | None = None,
    tiles_dir: Path | None = None,
    transcripts_dir: Path | None = None,
    metadata_path: Path | None = None,
    articles_path: Path | None = None,
    index_dir: Path | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Build PixelRAG tile dirs (0.png.tiles/, ...) and archivist metadata."""
    env = load_memory_stack_env()
    screens = screens_dir or resolve_path("SCREENPIPE_SCREENS_DIR", env=env)
    index_root = index_dir or resolve_path("PIXELRAG_INDEX_DIR", env=env)
    tiles_root = tiles_dir or resolve_path("PIXELRAG_TILES_DIR", env=env)
    if tiles_root == resolve_path("PIXELRAG_TILES_DIR", env=env) and not tiles_dir:
        # Default tiles live under the index output dir.
        tiles_root = index_root / "tiles"
    transcripts = transcripts_dir or resolve_path("SCREENPIPE_TRANSCRIPTS_DIR", env=env)
    metadata_out = metadata_path or resolve_path("TILES_METADATA_PATH", env=env)
    articles_out = articles_path or (index_root / "articles.json")

    tiles_root.mkdir(parents=True, exist_ok=True)
    transcript_index = _load_transcript_index(transcripts)
    metadata: Dict[str, Dict[str, Any]] = {}
    articles: List[Dict[str, str]] = []

    for article_id, shot in enumerate(_iter_screenshots(screens)):
        extra = _match_transcript(shot.name, transcript_index)
        ts = _parse_timestamp_from_name(shot.name) or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        url = str(extra.get("url") or "")
        title = str(extra.get("window_title") or shot.stem)

        article_dir = tiles_root / f"{article_id}.png.tiles"
        _write_article_tiles(shot, article_dir, url=url)
        articles.append({"title": title, "url": url})

        entry = {
            "article_id": article_id,
            "source_filename": shot.name,
            "timestamp": ts,
            "url": url,
            "window_title": title,
            "screenpipe_path": str(shot.resolve()),
            "transcript_path": extra.get("transcript_path") or "",
            "tile_dir": str(article_dir.resolve()),
        }
        metadata[str(article_id)] = entry
        metadata[shot.name] = entry

    articles_out.parent.mkdir(parents=True, exist_ok=True)
    articles_out.write_text(json.dumps(articles, indent=2), encoding="utf-8")
    metadata_out.parent.mkdir(parents=True, exist_ok=True)
    metadata_out.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build PixelRAG tiles from Screenpipe screenshots")
    parser.add_argument("--screens-dir", type=Path, default=None)
    parser.add_argument("--tiles-dir", type=Path, default=None)
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument("--transcripts-dir", type=Path, default=None)
    parser.add_argument("--metadata-path", type=Path, default=None)
    parser.add_argument("--articles-path", type=Path, default=None)
    args = parser.parse_args(argv)

    metadata = build_tiles(
        screens_dir=args.screens_dir,
        tiles_dir=args.tiles_dir,
        index_dir=args.index_dir,
        transcripts_dir=args.transcripts_dir,
        metadata_path=args.metadata_path,
        articles_path=args.articles_path,
    )
    print(f"Built {len([k for k in metadata if k.isdigit()])} PixelRAG article(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
