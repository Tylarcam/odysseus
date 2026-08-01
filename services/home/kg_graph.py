"""Knowledge-graph payload for the V.A.U.L.T. center globe."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from core.lineage import lineage_for

MAX_GLOBE_NODES = 50

# Branch anchor positions on the sphere (phi, theta radians) — mirrors cmdCenterScene.js.
_BRANCH_ANCHOR: Dict[str, Tuple[float, float]] = {
    "core": (math.pi * 0.48, 0.0),
    "mem": (math.pi * 0.32, 0.65),
    "prod": (math.pi * 0.32, 2.05),
    "intel": (math.pi * 0.32, 3.45),
    "comms": (math.pi * 0.32, 4.85),
    "agency": (math.pi * 0.64, 0.95),
    "relay": (math.pi * 0.64, 2.75),
    "voice": (math.pi * 0.64, 4.55),
    "mycelia": (math.pi * 0.50, 1.55),
    "chat": (math.pi * 0.40, 5.50),
}


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return text or "item"


def _stable_hash(text: str) -> int:
    h = 0
    for ch in text:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h


def _sphere_position(branch: str, node_id: str, *, outward: float = 0.0) -> Dict[str, float]:
    phi0, theta0 = _BRANCH_ANCHOR.get(branch, _BRANCH_ANCHOR["prod"])
    h = _stable_hash(node_id)
    dphi = ((h % 1000) / 1000.0 - 0.5) * 0.32
    dtheta = (((h // 1000) % 1000) / 1000.0 - 0.5) * 0.55
    phi = max(0.12, min(math.pi - 0.12, phi0 + dphi + outward * 0.06))
    theta = theta0 + dtheta
    return {"phi": phi, "theta": theta}


def _make_node(
    *,
    node_id: str,
    kind: str,
    label: str,
    branch: str,
    size: float,
    tone: str,
    action: str,
    target_id: Optional[str] = None,
    summary: str = "",
    ts: Any = None,
    outward: float = 0.0,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    pos = _sphere_position(branch, node_id, outward=outward)
    node: Dict[str, Any] = {
        "id": node_id,
        "kind": kind,
        "label": label,
        "branch": branch,
        "size": round(size, 2),
        "tone": tone,
        "action": action,
        "target_id": target_id,
        "summary": summary,
        "ts": ts,
        **pos,
    }
    if status:
        node["status"] = status
    return node


def _add_edge(edges: List[Dict[str, str]], source: str, target: str, kind: str) -> None:
    if source == target:
        return
    key = f"{source}|{target}|{kind}"
    if any(f"{e['source']}|{e['target']}|{e['kind']}" == key for e in edges):
        return
    edges.append({"source": source, "target": target, "kind": kind})


def _dominant_branch_for_project(items: List[Dict[str, Any]]) -> str:
    counts: Dict[str, int] = {}
    for item in items:
        if item.get("type") == "document":
            counts["intel"] = counts.get("intel", 0) + 1
        else:
            counts["prod"] = counts.get("prod", 0) + 1
    if not counts:
        return "prod"
    return max(counts, key=counts.get)


def build_globe_graph(
    *,
    notes: Iterable[Dict[str, Any]],
    documents: Iterable[Dict[str, Any]],
    tasks: Iterable[Dict[str, Any]],
    handoffs: Optional[Dict[str, Any]] = None,
    priority_queue: Optional[List[Dict[str, Any]]] = None,
    agent_activity: Optional[List[Dict[str, Any]]] = None,
    projects: Optional[Dict[str, Any]] = None,
    calendar_events: Optional[List[Dict[str, Any]]] = None,
    mempalace_nodes: Optional[List[Dict[str, Any]]] = None,
    mempalace_edges: Optional[List[Dict[str, str]]] = None,
    mempalace_status: str = "skipped",
) -> Dict[str, Any]:
    """Build nodes/edges for the CMD Center globe from live Odysseus surfaces."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []
    seen_ids: Set[str] = set()

    def _push(node: Dict[str, Any]) -> bool:
        if node["id"] in seen_ids:
            return False
        if len(nodes) >= MAX_GLOBE_NODES:
            return False
        seen_ids.add(node["id"])
        nodes.append(node)
        return True

    handoffs = handoffs or {}
    priority_queue = priority_queue or []
    agent_activity = agent_activity or []
    projects = projects or {}
    notes_list = [n for n in notes if not n.get("archived")]
    tasks_list = list(tasks)

    # --- Projects (large bright nodes) ----------------------------------------
    project_list = projects.get("projects") or []
    for rank, project in enumerate(project_list[:5]):
        name = str(project.get("name") or "Project")
        items = project.get("items") or []
        pid = f"project:{_slug(name)}"
        branch = _dominant_branch_for_project(items)
        size = min(6.0, 4.5 + len(items) * 0.25 + max(0, 4 - rank) * 0.1)
        node = _make_node(
            node_id=pid,
            kind="project",
            label=name,
            branch=branch,
            size=size,
            tone="bright",
            action="library",
            target_id=None,
            summary=f"{len(items)} recent item(s)",
            ts=project.get("last_activity_at"),
            outward=0.35 + rank * 0.04,
        )
        if _push(node):
            _add_edge(edges, f"branch:{branch}", pid, "hosts")
            for item in items[:3]:
                item_type = item.get("type") or "note"
                item_id = item.get("id")
                if not item_id:
                    continue
                child_id = f"{item_type}:{item_id}"
                _add_edge(edges, pid, child_id, "contains")

    # --- Urgent nodes from priority queue -------------------------------------
    for item in priority_queue:
        if int(item.get("urgency") or 0) < 80:
            continue
        kind = item.get("kind") or "urgent"
        iid = item.get("id")
        if not iid:
            continue
        node_id = f"{kind}:{iid}"
        branch = str(item.get("branch") or "prod")
        node = _make_node(
            node_id=node_id,
            kind="urgent",
            label=str(item.get("title") or "Urgent"),
            branch=branch,
            size=min(4.5, 3.0 + int(item.get("urgency") or 80) / 40.0),
            tone="urgent",
            action=str(item.get("action") or "refresh"),
            target_id=item.get("target_id"),
            summary=str(item.get("subtitle") or ""),
            ts=item.get("ts"),
        )
        if _push(node):
            _add_edge(edges, f"branch:{branch}", node_id, "attention")

    # --- Handoffs with doc links ------------------------------------------------
    for h in handoffs.get("needs_attention") or []:
        hid = h.get("id")
        if not hid or f"handoff:{hid}" in seen_ids:
            continue
        node_id = f"handoff:{hid}"
        node = _make_node(
            node_id=node_id,
            kind="urgent",
            label=str(h.get("title") or "Handoff"),
            branch="relay",
            size=4.2,
            tone="urgent",
            action="agent_bin",
            target_id=hid,
            summary=f"→ {h.get('handoff_target') or '?'}",
            ts=h.get("handoff_at") or h.get("updated_at"),
        )
        if _push(node):
            _add_edge(edges, "branch:relay", node_id, "attention")
            doc_id = h.get("handoff_doc_id")
            if doc_id:
                _add_edge(edges, node_id, f"document:{doc_id}", "handoff_doc")

    # --- Notes with due dates ---------------------------------------------------
    for note in notes_list:
        if not note.get("due_date"):
            continue
        nid = note.get("id")
        if not nid:
            continue
        node_id = f"note:{nid}"
        if node_id in seen_ids:
            continue
        title = str(note.get("title") or "Due note")
        node = _make_node(
            node_id=node_id,
            kind="urgent",
            label=title,
            branch="prod",
            size=3.8,
            tone="urgent",
            action="open_note",
            target_id=nid,
            summary=f"Due {note.get('due_date')}",
            ts=note.get("updated_at"),
        )
        if _push(node):
            _add_edge(edges, "branch:prod", node_id, "due")

    # --- Scheduled tasks --------------------------------------------------------
    for task in tasks_list:
        schedule = str(task.get("schedule") or "").strip()
        status = str(task.get("status") or "").lower()
        if not schedule or status == "paused":
            continue
        tid = task.get("id")
        if not tid:
            continue
        node_id = f"task:{tid}"
        if node_id in seen_ids:
            continue
        title = str(task.get("name") or task.get("title") or "Scheduled task")
        node = _make_node(
            node_id=node_id,
            kind="scheduled",
            label=title,
            branch="prod",
            size=3.4,
            tone="scheduled",
            action="open_task",
            target_id=tid,
            summary=schedule,
            ts=task.get("updated_at"),
        )
        if _push(node):
            _add_edge(edges, "branch:prod", node_id, "scheduled")

    # --- Agent activity (yellow nodes) ------------------------------------------
    for agent in agent_activity[:8]:
        aid = agent.get("id")
        if not aid:
            continue
        node_id = f"agent:{aid}"
        if node_id in seen_ids:
            continue
        branch = "mycelia" if agent.get("swarm") else "prod"
        status = str(agent.get("status") or "running")
        node = _make_node(
            node_id=node_id,
            kind="agent",
            label=str(agent.get("agent") or "Agent"),
            branch=branch,
            size=3.0 if status in ("running", "") else 2.6,
            tone="agent",
            action=str(agent.get("action") or "open_task"),
            target_id=agent.get("target_id"),
            summary=str(agent.get("text") or ""),
            ts=agent.get("ts"),
            status=status,
        )
        if _push(node):
            _add_edge(edges, f"branch:{branch}", node_id, "activity")
            target = agent.get("target_id")
            if target:
                _add_edge(edges, node_id, f"task:{target}", "run")

    # --- Upcoming calendar events (Up Next card connector) ----------------------
    for event in (calendar_events or [])[:5]:
        uid = event.get("uid")
        if not uid:
            continue
        node_id = f"event:{uid}"
        if node_id in seen_ids:
            continue
        title = str(event.get("title") or "Event")
        node = _make_node(
            node_id=node_id,
            kind="scheduled",
            label=title,
            branch="comms",
            size=3.4,
            tone="scheduled",
            action="calendar",
            target_id=uid,
            summary=str(event.get("start") or ""),
            ts=event.get("start"),
        )
        if _push(node):
            _add_edge(edges, "branch:comms", node_id, "scheduled")

    # --- MemPalace memory nodes (Phase 2) -------------------------------------
    for mp_node in mempalace_nodes or []:
        if _push(mp_node):
            branch = str(mp_node.get("branch") or "mem")
            _add_edge(edges, f"branch:{branch}", mp_node["id"], "memory")
    for mp_edge in mempalace_edges or []:
        _add_edge(edges, mp_edge["source"], mp_edge["target"], mp_edge.get("kind") or "tunnel")

    # --- Cross-object lineage edges (cmd-center-core-system) -------------------
    _add_lineage_edges(edges, seen_ids)

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "mempalace": mempalace_status,
        },
    }


def _parse_globe_node_pair(node_id: str) -> Optional[Tuple[str, str]]:
    """Map a rendered globe node id (``kind:id``) to a lineage (kind, id) pair."""
    if not node_id or ":" not in node_id:
        return None
    kind, oid = node_id.split(":", 1)
    kind = (kind or "").strip()
    oid = (oid or "").strip()
    # Branch anchors and synthetic project/mem nodes are not lineage objects.
    if not kind or not oid or kind in ("branch", "project", "agent", "event", "mem"):
        return None
    return (kind, oid)


def _add_lineage_edges(edges: List[Dict[str, str]], seen_ids: Set[str]) -> None:
    """Add edges between two rendered non-branch nodes when a lineage edge links them."""
    pairs: List[Tuple[str, str]] = []
    node_by_pair: Dict[Tuple[str, str], str] = {}
    for nid in seen_ids:
        pair = _parse_globe_node_pair(nid)
        if not pair:
            continue
        if pair not in node_by_pair:
            pairs.append(pair)
            node_by_pair[pair] = nid

    if not pairs:
        return

    related = lineage_for(pairs)
    for pair, neighbors in related.items():
        src_node = node_by_pair.get(pair)
        if not src_node:
            continue
        for n in neighbors or []:
            nkind = str(n.get("kind") or "").strip()
            nid = str(n.get("id") or "").strip()
            if not nkind or not nid:
                continue
            tgt_node = node_by_pair.get((nkind, nid))
            if not tgt_node or tgt_node == src_node:
                continue
            # lineage_for is bidirectional — emit one undirected edge per pair.
            if src_node > tgt_node:
                continue
            # Prefer the stored relation; fall back to a generic lineage kind.
            edge_kind = str(n.get("relation") or "").strip() or "lineage"
            _add_edge(edges, src_node, tgt_node, edge_kind)
