"""Clicky client for archivist.ai unified memory queries."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error, request


def _default_api_url() -> str:
    env_url = os.environ.get("UNIFIED_MEMORY_API_URL")
    if env_url:
        return env_url.rstrip("/")
    return "http://localhost:40001/query"


def load_clicky_config(config_path: Path | None = None) -> Dict[str, Any]:
    path = config_path or Path(__file__).resolve().parent.parent / "clicky" / "config" / "clicky_config.json"
    if not path.is_file():
        return {"unified_memory_api_url": _default_api_url()}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"unified_memory_api_url": _default_api_url()}
    return payload if isinstance(payload, dict) else {"unified_memory_api_url": _default_api_url()}


def query_unified_memory(
    query_text: str,
    *,
    k: int = 3,
    config_path: Path | None = None,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Send a quick question to the unified memory API."""
    cfg = load_clicky_config(config_path)
    url = str(cfg.get("unified_memory_api_url") or _default_api_url()).rstrip("/")
    payload = json.dumps({"query": query_text, "k": k}).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "query": query_text,
            "error": str(exc),
            "visual_results": [],
            "agent_memory_results": [],
            "notes_results": [],
        }
    return body if isinstance(body, dict) else {"query": query_text, "raw": body}


def format_overlay_summary(result: Dict[str, Any]) -> str:
    """Compact string for Clicky popup overlay."""
    lines = []
    visual = (result.get("visual_results") or [])[:1]
    if visual:
        meta = visual[0].get("tile_metadata") or {}
        title = meta.get("window_title") or visual[0].get("id") or "screenshot"
        lines.append(f"Screen: {title}")

    memory = (result.get("agent_memory_results") or [])[:1]
    if memory:
        lines.append(f"Memory: {memory[0].get('summary', '')}")

    notes = (result.get("notes_results") or [])[:1]
    if notes:
        lines.append(f"Note: {notes[0].get('title') or notes[0].get('filename')}")

    if result.get("error"):
        lines.append(f"Error: {result['error']}")

    return "\n".join(lines) if lines else "No matching memory found."


def quick_last_reading_query(seconds: int = 120) -> str:
    """Build a natural-language query for recent browsing context."""
    return f"What was I reading in the last {seconds} seconds?"


def quick_page_connections_query(url: str, title: str = "") -> str:
    """Build a query scoped to the current page."""
    if title:
        return f"Show connecting ideas for page titled {title!r}"
    return f"Show connecting ideas for {url}"
