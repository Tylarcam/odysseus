#!/usr/bin/env python3
"""Export recent Screenpipe captures into archivist.ai screenshot/transcript dirs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.memory_stack_env import load_memory_stack_env, resolve_path

_SAFE_TS = re.compile(r"[^0-9A-Za-z]+")


def _screenpipe_api_url(env: Dict[str, str]) -> str:
    return (env.get("SCREENPIPE_API_URL") or "http://localhost:3030").rstrip("/")


def _fetch_search(api_url: str, *, limit: int = 100) -> List[Dict[str, Any]]:
    query = urllib.parse.urlencode({"limit": str(limit), "content_type": "all"})
    endpoint = f"{api_url}/search?{query}"
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10.0) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []

    if not isinstance(body, dict):
        return []
    data = body.get("data") or []
    return [row for row in data if isinstance(row, dict)]


def _safe_name(timestamp: str, frame_id: int) -> str:
    ts = _SAFE_TS.sub("-", timestamp.replace(":", "-").replace("T", "_")).strip("-")
    return f"screen_{ts}_f{frame_id}"


def _resolve_video_path(raw_path: str, data_dir: Path) -> Path:
    path = Path(raw_path)
    if path.is_file():
        return path
    candidate = data_dir / raw_path
    if candidate.is_file():
        return candidate
    candidate = data_dir / "data" / Path(raw_path).name
    if candidate.is_file():
        return candidate
    return path


def _extract_frame_png(
    video_path: Path,
    offset_index: int,
    output_png: Path,
) -> bool:
    if not video_path.is_file():
        return False
    if shutil.which("ffmpeg") is None:
        return False

    output_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"select=eq(n\\,{max(0, int(offset_index))})",
        "-vframes",
        "1",
        str(output_png),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    return output_png.is_file()


def export_screenpipe(
    *,
    screens_dir: Path | None = None,
    transcripts_dir: Path | None = None,
    metadata_path: Path | None = None,
    api_url: str | None = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Pull recent OCR/audio rows from Screenpipe and materialize archivist inputs."""
    env = load_memory_stack_env()
    screens = screens_dir or resolve_path("SCREENPIPE_SCREENS_DIR", env=env)
    transcripts = transcripts_dir or resolve_path("SCREENPIPE_TRANSCRIPTS_DIR", env=env)
    metadata_out = metadata_path or resolve_path("TILES_METADATA_PATH", env=env)
    data_dir = resolve_path("SCREENPIPE_DATA_DIR", env=env)
    base_api = api_url or _screenpipe_api_url(env)

    screens.mkdir(parents=True, exist_ok=True)
    transcripts.mkdir(parents=True, exist_ok=True)

    rows = _fetch_search(base_api, limit=limit)
    metadata: Dict[str, Dict[str, Any]] = {}
    exported_frames = 0
    exported_transcripts = 0

    for row in rows:
        item_type = str(row.get("type") or "")
        content = row.get("content") or {}
        if not isinstance(content, dict):
            continue

        timestamp = str(content.get("timestamp") or datetime.now(timezone.utc).isoformat())
        app_name = str(content.get("app_name") or content.get("app") or "")

        if item_type == "OCR":
            frame_id = int(content.get("frame_id") or 0)
            text = str(content.get("text") or "")
            file_path = str(content.get("file_path") or "")
            offset_index = int(content.get("offset_index") or 0)
            stem = _safe_name(timestamp, frame_id)
            png_name = f"{stem}.png"
            png_path = screens / png_name

            video_path = _resolve_video_path(file_path, data_dir)
            if _extract_frame_png(video_path, offset_index, png_path):
                exported_frames += 1

            transcript_path = transcripts / f"{stem}.json"
            transcript_path.write_text(
                json.dumps(
                    {
                        "timestamp": timestamp,
                        "window_title": app_name,
                        "app_name": app_name,
                        "text": text,
                        "frame_id": frame_id,
                        "file_path": file_path,
                        "offset_index": offset_index,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            exported_transcripts += 1

            metadata[png_name] = {
                "timestamp": timestamp[:19],
                "url": "",
                "window_title": app_name,
                "screenpipe_path": str(png_path.resolve()) if png_path.is_file() else file_path,
                "transcript_path": str(transcript_path.resolve()),
                "ocr_preview": text[:240],
            }

        elif item_type == "Audio":
            chunk_id = int(content.get("chunk_id") or 0)
            transcription = str(content.get("transcription") or "")
            stem = _safe_name(timestamp, chunk_id)
            transcript_path = transcripts / f"audio_{stem}.json"
            transcript_path.write_text(
                json.dumps(
                    {
                        "timestamp": timestamp,
                        "transcription": transcription,
                        "chunk_id": chunk_id,
                        "file_path": content.get("file_path") or "",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            exported_transcripts += 1

    metadata_out.parent.mkdir(parents=True, exist_ok=True)
    metadata_out.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {
        "api_url": base_api,
        "rows_fetched": len(rows),
        "frames_exported": exported_frames,
        "transcripts_exported": exported_transcripts,
        "screens_dir": str(screens.resolve()),
        "transcripts_dir": str(transcripts.resolve()),
        "metadata_path": str(metadata_out.resolve()),
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Screenpipe API data for archivist.ai")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--api-url", default=None)
    args = parser.parse_args(argv)

    summary = export_screenpipe(api_url=args.api_url, limit=args.limit)
    print(json.dumps(summary, indent=2))
    if summary["rows_fetched"] == 0:
        print(
            "WARNING: No Screenpipe rows yet (non-fatal). Capture needs time after start:\n"
            "  C:\\Users\\tylar\\code\\screen-pipe\\target\\release\\screenpipe.exe --port 3030"
        )
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
