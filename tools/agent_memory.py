#!/usr/bin/env python3
"""JSON-backed agent memory store for archivist.ai."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.memory_stack_env import load_memory_stack_env, resolve_path


def _default_store() -> Dict[str, Any]:
    return {"entries": []}


def _load_store(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return _default_store()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_store()
    if not isinstance(payload, dict):
        return _default_store()
    entries = payload.get("entries")
    if not isinstance(entries, list):
        payload["entries"] = []
    return payload


def _save_store(path: Path, store: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")


def agent_memory_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    load_memory_stack_env()
    return resolve_path("AGENT_MEMORY_PATH", default="./data/archivist/agent_memory.json")


def store_agent_memory(
    summary: str,
    *,
    tags: Optional[List[str]] = None,
    related_tiles: Optional[List[str]] = None,
    related_notes: Optional[List[str]] = None,
    entry_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    path: Path | None = None,
) -> Dict[str, Any]:
    """Append a distilled memory entry."""
    store_path = agent_memory_path(path)
    store = _load_store(store_path)
    entry = {
        "id": entry_id or f"mem-{uuid.uuid4().hex[:8]}",
        "timestamp": timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": summary.strip(),
        "tags": list(tags or []),
        "related_tiles": list(related_tiles or []),
        "related_notes": list(related_notes or []),
    }
    store.setdefault("entries", []).append(entry)
    _save_store(store_path, store)
    return entry


def search_agent_memory(
    query_text: str,
    path: Path | None = None,
    *,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Simple keyword search over summary and tags."""
    store_path = agent_memory_path(path)
    store = _load_store(store_path)
    needle = query_text.strip().lower()
    if not needle:
        return []

    scored: List[tuple[int, Dict[str, Any]]] = []
    for entry in store.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        haystack = " ".join(
            [
                str(entry.get("summary") or ""),
                " ".join(str(t) for t in entry.get("tags") or []),
            ]
        ).lower()
        if needle in haystack:
            score = haystack.count(needle)
            scored.append((score, entry))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in scored[:limit]]
