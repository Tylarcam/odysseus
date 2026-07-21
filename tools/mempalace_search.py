#!/usr/bin/env python3
"""MemPalace markdown notes indexer and search for archivist.ai."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.memory_stack_env import load_memory_stack_env, resolve_path

_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def notes_index_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    load_memory_stack_env()
    return resolve_path("NOTES_INDEX_PATH", default="./data/archivist/notes_index.json")


def notes_dir(path: Path | None = None) -> Path:
    if path is not None:
        return path
    load_memory_stack_env()
    return resolve_path("MEMPALACE_NOTES_DIR", default="./notes")


def _extract_title(text: str, fallback: str) -> str:
    match = _HEADING_RE.search(text)
    if match:
        return match.group(1).strip()
    return fallback


def _extract_keywords(text: str, limit: int = 12) -> List[str]:
    words = [w.lower() for w in _WORD_RE.findall(text)]
    seen: List[str] = []
    for word in words:
        if len(word) < 4:
            continue
        if word in seen:
            continue
        seen.append(word)
        if len(seen) >= limit:
            break
    return seen


def build_notes_index(
    *,
    notes_root: Path | None = None,
    index_path: Path | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Scan markdown files and write notes_index.json."""
    root = notes_root or notes_dir()
    out_path = notes_index_path(index_path)
    index: Dict[str, Dict[str, Any]] = {}

    if root.is_dir():
        for md_path in sorted(root.rglob("*.md")):
            rel_name = md_path.name
            try:
                text = md_path.read_text(encoding="utf-8")
            except OSError:
                continue
            index[rel_name] = {
                "title": _extract_title(text, md_path.stem.replace("_", " ").title()),
                "path": str(md_path.resolve()),
                "keywords": _extract_keywords(text),
            }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index


def search_notes_index(
    query_text: str,
    index_path: Path | None = None,
    *,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Keyword search over title, path, and keywords."""
    path = notes_index_path(index_path)
    if not path.is_file():
        return []

    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    needle = query_text.strip().lower()
    if not needle or not isinstance(index, dict):
        return []

    hits: List[tuple[int, Dict[str, Any]]] = []
    for filename, meta in index.items():
        if not isinstance(meta, dict):
            continue
        haystack = " ".join(
            [
                filename,
                str(meta.get("title") or ""),
                str(meta.get("path") or ""),
                " ".join(str(k) for k in meta.get("keywords") or []),
            ]
        ).lower()
        if needle in haystack:
            hit = dict(meta)
            hit["filename"] = filename
            hits.append((haystack.count(needle), hit))

    hits.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in hits[:limit]]
