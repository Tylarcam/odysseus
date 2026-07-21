"""Subprocess bridge to MemPalace for CMD Center globe memory nodes."""

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


def _run_status() -> str:
    palace = mempalace_palace_path()
    cmd = [
        "mempalace",
        "--palace",
        palace,
        "--backend",
        "sqlite_exact",
        "status",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=2.0,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "mempalace status failed").strip())
    return result.stdout or ""


def _build_nodes_and_edges(wings: List[Dict[str, Any]], limit: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
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
    """Return memory nodes, tunnel edges, and status string."""
    if not mempalace_enabled():
        return [], [], "disabled"

    now = time.time()
    if not force and now - float(_cache.get("ts") or 0) < _CACHE_TTL_SEC:
        return _cache["nodes"], _cache["edges"], _cache["status"]

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
