"""Subprocess bridge to MemPalace for CMD Center globe memory nodes.

Callable from the Odysseus backend today
----------------------------------------
- ``mempalace status`` — wing/room/drawer inventory (structure)
- ``mempalace search`` — real content hits (snippets + wing/room) — preferred signal

Deferred (MCP-only; do not partially fake)
------------------------------------------
MemPalace graph tools ``kg_query`` / ``traverse`` / ``graph_stats`` /
``find_tunnels`` are exposed only over the MCP stdio protocol. They are not
importable as a Python library and have no CLI/HTTP equivalent in MemPalace
3.4.0. Wiring them into this backend process is explicitly deferred pending an
upstream queryable interface — see design.md Decision D5 / Open Questions and
``openspec/.../specs/cmd-center-mycelia-system/spec.md``.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from services.home.kg_graph import _make_node, _slug

_CACHE_TTL_SEC = 60
_cache: Dict[str, Any] = {"ts": 0.0, "nodes": [], "edges": [], "status": "skipped"}

_WING_RE = re.compile(r"^\s*WING:\s*(.+?)\s*$")
_ROOM_RE = re.compile(r"^\s*ROOM:\s+(\S+)\s+(\d+)\s+drawers")
_SEARCH_HIT_RE = re.compile(r"^\s*\[(\d+)\]\s+(.+?)\s*/\s+(.+?)\s*$")
_SEARCH_SOURCE_RE = re.compile(r"^\s*Source:\s+(.+?)\s*$")
_SEARCH_MATCH_RE = re.compile(r"^\s*Match:\s+(.+?)\s*$")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def mempalace_enabled() -> bool:
    if not _env_bool("MEMPALACE_ENABLED", default=(os.name == "nt")):
        return False
    return os.path.isdir(mempalace_palace_path())


def mempalace_palace_path() -> str:
    return os.environ.get("MEMPALACE_PALACE_PATH", r"C:\Users\tylar\code\MemPalace")


def mempalace_node_limit() -> int:
    try:
        return max(1, min(24, int(os.environ.get("MEMPALACE_NODE_LIMIT", "12"))))
    except ValueError:
        return 12


def mempalace_search_query() -> str:
    return (os.environ.get("MEMPALACE_SEARCH_QUERY") or "memory").strip() or "memory"


def mempalace_search_results() -> int:
    try:
        return max(1, min(12, int(os.environ.get("MEMPALACE_SEARCH_RESULTS", "8"))))
    except ValueError:
        return 8


def _parse_status_output(text: str) -> List[Dict[str, Any]]:
    wings: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for line in text.splitlines():
        wing_match = _WING_RE.match(line)
        if wing_match:
            current = {"name": wing_match.group(1).strip(), "rooms": []}
            wings.append(current)
            continue
        room_match = _ROOM_RE.match(line)
        if room_match and current is not None:
            current["rooms"].append(
                {
                    "name": room_match.group(1).strip(),
                    "drawers": int(room_match.group(2)),
                }
            )
    return wings


def _parse_search_output(text: str) -> List[Dict[str, Any]]:
    """Parse ``mempalace search`` text into content hits.

    Expected block shape (verified against MemPalace 3.4.0)::

        [1] WingName / room
            Source: path
            Match: cosine=...  bm25=...

            <snippet lines...>
    """
    hits: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    snippet_lines: List[str] = []

    def _flush() -> None:
        nonlocal current, snippet_lines
        if current is None:
            return
        snippet = " ".join(" ".join(snippet_lines).split()).strip()
        current["snippet"] = snippet[:180]
        hits.append(current)
        current = None
        snippet_lines = []

    for raw in text.splitlines():
        line = raw.rstrip()
        hit_match = _SEARCH_HIT_RE.match(line)
        if hit_match:
            _flush()
            current = {
                "rank": int(hit_match.group(1)),
                "wing": hit_match.group(2).strip(),
                "room": hit_match.group(3).strip(),
                "source": "",
                "match": "",
                "snippet": "",
            }
            snippet_lines = []
            continue
        if current is None:
            continue
        source_match = _SEARCH_SOURCE_RE.match(line)
        if source_match:
            current["source"] = source_match.group(1).strip()
            continue
        match_match = _SEARCH_MATCH_RE.match(line)
        if match_match:
            current["match"] = match_match.group(1).strip()
            continue
        if line.strip().startswith("─"):
            continue
        if line.strip().startswith("="):
            continue
        if line.strip():
            snippet_lines.append(line.strip())

    _flush()
    return hits


def _cli_base() -> List[str]:
    return [
        "mempalace",
        "--palace",
        mempalace_palace_path(),
        "--backend",
        "sqlite_exact",
    ]


def _run_status() -> str:
    result = subprocess.run(
        _cli_base() + ["status"],
        capture_output=True,
        text=True,
        timeout=2.0,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "mempalace status failed").strip())
    return result.stdout or ""


def _run_search(query: str, *, results: int) -> str:
    result = subprocess.run(
        _cli_base() + ["search", query, "--results", str(results)],
        capture_output=True,
        text=True,
        timeout=4.0,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "mempalace search failed").strip())
    return result.stdout or ""


def _build_nodes_from_search(
    hits: List[Dict[str, Any]], limit: int
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Content-signal nodes from search hits (not drawer-count decoration)."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []
    wing_ids: Dict[str, str] = {}

    for hit in hits:
        if len(nodes) >= limit:
            break
        wing = str(hit.get("wing") or "Wing")
        room = str(hit.get("room") or "room")
        source = str(hit.get("source") or "drawer")
        wing_slug = _slug(wing)
        wing_id = f"memory:wing:{wing_slug}"
        if wing_id not in wing_ids:
            if len(nodes) >= limit:
                break
            wing_ids[wing_id] = wing
            nodes.append(
                _make_node(
                    node_id=wing_id,
                    kind="memory",
                    label=wing,
                    branch="mem",
                    size=3.0,
                    tone="memory",
                    action="notes",
                    target_id=None,
                    summary="MemPalace wing (search)",
                    outward=0.2,
                )
            )

        hit_id = f"memory:hit:{wing_slug}:{_slug(room)}:{_slug(source)}:{hit.get('rank', 0)}"
        snippet = str(hit.get("snippet") or "").strip()
        summary = snippet or str(hit.get("match") or f"{room} · {source}")
        nodes.append(
            _make_node(
                node_id=hit_id,
                kind="memory",
                label=f"{wing} · {source}" if source else f"{wing} · {room}",
                branch="mem",
                size=2.4,
                tone="memory",
                action="notes",
                target_id=None,
                summary=summary[:120],
                outward=0.1,
            )
        )
        edges.append({"source": wing_id, "target": hit_id, "kind": "hosts"})

    hit_nodes = [n for n in nodes if str(n.get("id") or "").startswith("memory:hit:")]
    for a, b in zip(hit_nodes, hit_nodes[1:]):
        edges.append({"source": a["id"], "target": b["id"], "kind": "related"})

    return nodes, edges


def _build_nodes_and_edges(wings: List[Dict[str, Any]], limit: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Fallback: status-derived wing/room topology when search yields nothing."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []
    ranked_wings = sorted(
        wings,
        key=lambda w: sum(r.get("drawers", 0) for r in w.get("rooms") or []),
        reverse=True,
    )

    for wing in ranked_wings:
        if len(nodes) >= limit:
            break
        wing_name = str(wing.get("name") or "Wing")
        wing_slug = _slug(wing_name)
        wing_id = f"memory:wing:{wing_slug}"
        wing_drawers = sum(r.get("drawers", 0) for r in wing.get("rooms") or [])
        nodes.append(
            _make_node(
                node_id=wing_id,
                kind="memory",
                label=wing_name,
                branch="mem",
                size=3.0,
                tone="memory",
                action="notes",
                target_id=None,
                summary=f"{wing_drawers} drawers",
                outward=0.2,
            )
        )

        rooms = sorted(wing.get("rooms") or [], key=lambda r: r.get("drawers", 0), reverse=True)
        room_budget = 2 if len(ranked_wings) <= 4 else 1
        for room in rooms[:room_budget]:
            if len(nodes) >= limit:
                break
            room_name = str(room.get("name") or "room")
            room_id = f"memory:room:{wing_slug}:{_slug(room_name)}"
            nodes.append(
                _make_node(
                    node_id=room_id,
                    kind="memory",
                    label=f"{wing_name} · {room_name}",
                    branch="mem",
                    size=2.4,
                    tone="memory",
                    action="notes",
                    target_id=None,
                    summary=f"{room.get('drawers', 0)} drawers",
                    outward=0.1,
                )
            )
            edges.append({"source": wing_id, "target": room_id, "kind": "hosts"})

        if len(rooms) >= 2:
            a = f"memory:room:{wing_slug}:{_slug(rooms[0]['name'])}"
            b = f"memory:room:{wing_slug}:{_slug(rooms[1]['name'])}"
            edges.append({"source": a, "target": b, "kind": "tunnel"})

    return nodes, edges


def fetch_mempalace_globe_graph(*, force: bool = False) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], str]:
    """Return memory nodes, edges, and status string.

    Prefers ``mempalace search`` content hits. Falls back to ``status`` wing/room
    inventory when search is empty/unavailable. Never claims MCP graph-tool
    parity (``kg_query`` / ``traverse``) — see module docstring.
    """
    if not mempalace_enabled():
        return [], [], "disabled"

    now = time.time()
    if not force and now - float(_cache.get("ts") or 0) < _CACHE_TTL_SEC:
        return _cache["nodes"], _cache["edges"], _cache["status"]

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []
    status = "unavailable"

    try:
        search_out = _run_search(mempalace_search_query(), results=mempalace_search_results())
        hits = _parse_search_output(search_out)
        if hits:
            nodes, edges = _build_nodes_from_search(hits, mempalace_node_limit())
            status = "ok"
    except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError):
        hits = []

    if not nodes:
        try:
            output = _run_status()
            wings = _parse_status_output(output)
            if not wings:
                status = "empty"
                nodes, edges = [], []
            else:
                nodes, edges = _build_nodes_and_edges(wings, mempalace_node_limit())
                status = "ok"
        except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError):
            status = "unavailable"
            nodes, edges = [], []

    _cache.update({"ts": now, "nodes": nodes, "edges": edges, "status": status})
    return nodes, edges, status
