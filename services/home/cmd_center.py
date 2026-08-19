"""Command Center (V.A.U.L.T.) dashboard aggregation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.constants import DATA_DIR
from core.lineage import count_lineage_edges, lineage_for
from services.home.dashboard import build_recent_projects
from services.home.kg_graph import build_globe_graph
from services.home.stalled import (
    STALLED_SLA,
    apply_stalled_urgency,
    compute_stalled,
    is_briefish as _is_briefish,
    is_stale_brief as _is_stale_brief,
    stale_missed_days as _stale_missed_days,
)
from services.home.swarm_registry import (
    SWARM_DOCS,
    coo_task_spec,
    dispatchable_task_specs,
    filter_swarm_tasks,
    is_swarm_task_id,
    resolve_swarm_docs,
)
from services.home.mycelia_feed import build_mycelia_feed, mycelia_priority_queue_items
from services.documents.ceo_brief_store import select_ceo_brief
from services.mempalace.bridge import fetch_mempalace_globe_graph
from src.research_handler import list_recent_research_reports

# Rolling window for COMMS closed-loop conversion (reminded edges).
COMMS_CONVERSION_WINDOW_DAYS = 7

# Base urgency by kind used when a stalled lineage neighbor escalates a chain.
_STALLED_CHAIN_BASE_URGENCY: Dict[str, int] = {
    "handoff": 100,
    "job": 95,
    "note": 86,
    "task": 50,
    "email": 92,
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


def _title(item: Dict[str, Any], fallback: str = "Untitled") -> str:
    t = str(item.get("title") or item.get("name") or "").strip()
    if t:
        return t
    content = str(item.get("content") or item.get("prompt") or "").strip()
    if content:
        return content.split("\n")[0][:80]
    return fallback


def _note_open_items(note: Dict[str, Any]) -> int:
    items = note.get("items")
    if not isinstance(items, list):
        return 0
    return sum(1 for it in items if isinstance(it, dict) and not it.get("done") and not it.get("checked"))


def _note_queue_urgency(note: Dict[str, Any], now: datetime) -> Tuple[int, str]:
    """Return (urgency, band) for priority-queue ranking + Today Plan banding.

    Bands: stale | overdue | due | fat | pinned | open | calm
    Fat/stale briefs must outrank low queued noise so 38-item Daily Briefs
    don't sink below jobs that aren't the operator's focus today.
    """
    open_items = _note_open_items(note)
    due_dt = _parse_dt(note.get("due_date"))
    status, _, _ = _due_state(due_dt, now)

    if _is_stale_brief(note, now):
        # Below handoffs (100) / job review (95) / ready (90); above overdue (85).
        return min(89, 86 + min(open_items // 10, 3)), "stale"
    if status == "overdue" or (due_dt and due_dt < now):
        return 85, "overdue"
    if note.get("due_date") and status == "due":
        return 80, "due"
    if open_items >= 5:
        # 60 + open_items, capped just under overdue so 38-item briefs rise.
        return min(84, 60 + open_items), "fat"
    if note.get("pinned"):
        return 70, "pinned"
    if open_items > 0:
        return min(75, 60 + open_items * 2), "open"
    return 60, "calm"


def _build_today_plan(
    notes_list: List[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Triage deck for PLAN TODAY — stale briefs, overdue, fat checklists."""
    now = now or datetime.now(timezone.utc)
    rows: List[Dict[str, Any]] = []
    for note in notes_list:
        if note.get("archived"):
            continue
        if not (_is_directive_note(note) or _is_briefish(note)):
            continue
        urgency, band = _note_queue_urgency(note, now)
        open_items = _note_open_items(note)
        # Keep the sheet focused: actionable bands or meaningful open work.
        if band not in ("stale", "overdue", "due", "fat") and open_items < 3 and not note.get("pinned"):
            continue
        due_dt = _parse_dt(note.get("due_date"))
        status, due_label, overdue_days = _due_state(due_dt, now)
        body = str(note.get("content") or note.get("body") or "").strip()
        preview = body.split("\n")[0][:140] if body else ""
        missed = _stale_missed_days(note, now) if band == "stale" else None
        rows.append(
            {
                "id": note.get("id"),
                "title": _title(note, "Untitled note"),
                "band": band,
                "open_items": open_items,
                "urgency": urgency,
                "status": status,
                "due_label": due_label,
                "overdue_days": overdue_days,
                "due_at": note.get("due_date"),
                "pinned": bool(note.get("pinned")),
                "stale": band == "stale",
                "missed_days": missed,
                "preview": preview,
                "action": "open_note",
                "target_id": note.get("id"),
            }
        )

    band_rank = {"stale": 4, "overdue": 3, "due": 2, "fat": 1, "pinned": 0, "open": 0, "calm": 0}
    rows.sort(
        key=lambda r: (
            -band_rank.get(str(r.get("band")), 0),
            -int(r.get("urgency") or 0),
            -int(r.get("open_items") or 0),
        )
    )
    rows = rows[:12]
    summary = {
        "stale": sum(1 for r in rows if r.get("band") == "stale"),
        "overdue": sum(1 for r in rows if r.get("band") == "overdue"),
        "due": sum(1 for r in rows if r.get("band") == "due"),
        "fat": sum(1 for r in rows if r.get("band") == "fat"),
        "total": len(rows),
        "open_items": sum(int(r.get("open_items") or 0) for r in rows),
    }
    return {
        "summary": summary,
        "items": rows,
        "generated_at": now.isoformat(),
    }


def _is_directive_note(note: Dict[str, Any]) -> bool:
    if note.get("archived"):
        return False
    if note.get("pinned"):
        return True
    if note.get("due_date"):
        return True
    if note.get("note_type") in ("checklist", "todo", "reminder"):
        return True
    if _note_open_items(note) > 0:
        return True
    label = str(note.get("label") or "").lower()
    return any(tag in label for tag in ("directive", "todo", "plan", "brief", "digest"))


def _find_plan_note(notes_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for n in notes_list:
        blob = (_title(n) + " " + str(n.get("label") or "")).lower()
        if any(k in blob for k in ("plan today", "plan", "today", "directive")):
            return n
    return notes_list[0] if notes_list else None


def _find_morning_note(notes_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for n in notes_list:
        if any(k in _title(n).lower() for k in ("morning", "brief", "digest")):
            return n
    return None


def _doc_size_label(content: Optional[str]) -> str:
    n = len(content or "")
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}K"
    return f"{n / (1024 * 1024):.1f}M"


def _doc_lang_tag(language: Optional[str]) -> str:
    lang = (language or "md").strip().lower()
    aliases = {
        "markdown": "MD",
        "md": "MD",
        "python": "PY",
        "javascript": "JS",
        "typescript": "TS",
        "text": "TXT",
        "pdf": "PDF",
    }
    return aliases.get(lang, lang.upper()[:6] or "MD")


def build_notes_preview(
    notes_list: Iterable[Dict[str, Any]],
    *,
    limit: int = 16,
) -> List[Dict[str, Any]]:
    """Newest non-archived notes for the MEM tab rail (Orbital-style list)."""
    notes_preview: List[Dict[str, Any]] = []
    for note in sorted(
        notes_list,
        key=lambda n: _parse_dt(n.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[:limit]:
        body = str(note.get("content") or note.get("body") or "").strip()
        preview = body.split("\n")[0][:140] if body else ""
        labels = note.get("tags") or note.get("labels") or []
        if isinstance(labels, str):
            labels = [labels]
        if not isinstance(labels, list):
            labels = []
        if note.get("label") and note.get("label") not in labels:
            labels = [note.get("label"), *labels]
        notes_preview.append(
            {
                "id": note.get("id"),
                "title": _title(note, "Untitled note"),
                "preview": preview,
                "pinned": bool(note.get("pinned")),
                "tags": [str(t) for t in labels[:4] if t],
                "updated_at": note.get("updated_at"),
                "action": "open_note",
                "target_id": note.get("id"),
            }
        )
    return notes_preview


def _relative_time(dt: Optional[datetime], now: datetime) -> str:
    if not dt:
        return ""
    seconds = (dt - now).total_seconds()
    if seconds < 0:
        return "overdue"
    if seconds < 3600:
        return f"in {max(1, int(seconds // 60))}m"
    if seconds < 86400:
        return f"in {int(seconds // 3600)}h"
    return f"in {int(seconds // 86400)}d"


def _overdue_chip(dt: datetime, now: datetime) -> str:
    """Human relative overdue label — never a raw ISO string."""
    seconds = max(0, (now - dt).total_seconds())
    if seconds < 3600:
        return f"{max(1, int(seconds // 60))}m OVERDUE"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h OVERDUE"
    return f"{int(seconds // 86400)}d OVERDUE"


def _due_state(due_dt: Optional[datetime], now: datetime) -> tuple[str, str, Optional[int]]:
    """Return (status, chip_label, overdue_days) for queue / directive rows."""
    if not due_dt:
        return "calm", "", None
    delta = (due_dt - now).total_seconds()
    if delta < 0:
        days = max(0, int((now - due_dt).total_seconds() // 86400))
        return "overdue", _overdue_chip(due_dt, now), days
    if due_dt.date() == now.date():
        return "due", "DUE TODAY", None
    if delta < 86400 * 2:
        return "due", _relative_time(due_dt, now).upper().replace("IN ", "IN "), None
    return "calm", "", None


def _build_priority_queue(
    *,
    notes_list: List[Dict[str, Any]],
    active_tasks: List[Dict[str, Any]],
    handoffs: Dict[str, Any],
    jobs: Dict[str, Any],
    comms_preview: Optional[List[Dict[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    items: List[Dict[str, Any]] = []
    seen_handoff_ids: set[str] = set()

    for h in handoffs.get("needs_attention") or []:
        target = h.get("handoff_target") or "?"
        hid = str(h.get("id") or "")
        if hid:
            seen_handoff_ids.add(hid)
        items.append(
            apply_stalled_urgency(
                {
                    "id": h.get("id"),
                    "kind": "handoff",
                    "title": _title(h, "Handoff"),
                    "subtitle": f"Relay · pick up → {target}",
                    "branch": "relay",
                    "urgency": 100,
                    "status": "overdue",
                    "due_label": "NEEDS PICKUP",
                    "overdue_days": None,
                    "due_at": None,
                    "action": "agent_bin",
                    "target_id": h.get("id"),
                    "ts": h.get("handoff_at") or h.get("updated_at"),
                    "dedup_key": f"handoff:{h.get('id')}",
                },
                compute_stalled("handoff", h, now),
            )
        )

    # Claimed-but-stuck (running past SLA) — distinct from needs_attention.
    for h in handoffs.get("in_progress") or []:
        hid = str(h.get("id") or "")
        if hid and hid in seen_handoff_ids:
            continue
        stalled = compute_stalled("handoff", h, now)
        if not stalled:
            continue
        if hid:
            seen_handoff_ids.add(hid)
        target = h.get("handoff_target") or "?"
        items.append(
            apply_stalled_urgency(
                {
                    "id": h.get("id"),
                    "kind": "handoff",
                    "title": _title(h, "Handoff"),
                    "subtitle": f"Relay · claimed stuck → {target}",
                    "branch": "relay",
                    "urgency": 100,
                    "status": "overdue",
                    "due_label": "CLAIMED STUCK",
                    "overdue_days": None,
                    "due_at": None,
                    "action": "agent_bin",
                    "target_id": h.get("id"),
                    "ts": h.get("handoff_relay_started_at")
                    or h.get("handoff_at")
                    or h.get("updated_at"),
                    "dedup_key": f"handoff:{h.get('id')}",
                },
                stalled,
            )
        )

    for job in jobs.get("needs_review") or []:
        company = job.get("company") or "Company"
        role = job.get("role") or "Role"
        # Bucket membership implies needs_review even if status fields are absent.
        job_obj = {**job, "attention": job.get("attention") or "needs_review"}
        items.append(
            apply_stalled_urgency(
                {
                    "id": job.get("id"),
                    "kind": "job",
                    "title": f"{company} — {role}",
                    "subtitle": "Agency · needs review",
                    "branch": "agency",
                    "urgency": 95,
                    "status": "due",
                    "due_label": "NEEDS REVIEW",
                    "overdue_days": None,
                    "due_at": None,
                    "action": "jobs",
                    "target_id": job.get("id"),
                    "ts": job.get("updated_at"),
                    "dedup_key": f"job:{job.get('id')}",
                },
                compute_stalled("job", job_obj, now),
            )
        )

    for job in jobs.get("ready_to_apply") or []:
        company = job.get("company") or "Company"
        role = job.get("role") or "Role"
        items.append(
            apply_stalled_urgency(
                {
                    "id": job.get("id"),
                    "kind": "job",
                    "title": f"{company} — {role}",
                    "subtitle": "Agency · ready to apply",
                    "branch": "agency",
                    "urgency": 90,
                    "status": "due",
                    "due_label": "READY",
                    "overdue_days": None,
                    "due_at": None,
                    "action": "jobs",
                    "target_id": job.get("id"),
                    "ts": job.get("updated_at"),
                    "dedup_key": f"job:{job.get('id')}",
                },
                compute_stalled("job", job, now),
            )
        )

    for note in notes_list:
        task_stalled = compute_stalled("task", note, now)
        if (
            not _is_directive_note(note)
            and not _is_stale_brief(note, now)
            and not task_stalled
        ):
            continue
        open_items = _note_open_items(note)
        meta = note.get("label") or note.get("note_type") or "note"
        subtitle = f"Prod · {meta}"
        if open_items:
            subtitle = f"Prod · {open_items} open item(s)"
        due_dt = _parse_dt(note.get("due_date"))
        status, due_label, overdue_days = _due_state(due_dt, now)
        if due_label:
            subtitle = f"Prod · {due_label.lower()}"
        urgency, band = _note_queue_urgency(note, now)
        if band == "stale":
            missed = _stale_missed_days(note, now) or 1
            subtitle = f"Prod · stale brief · missed {missed}d · {open_items} open"
            status = "overdue"
            due_label = due_label or f"MISSED {missed}d"
        if task_stalled and not _is_directive_note(note) and not _is_stale_brief(note, now):
            # Stalled in-progress task that wouldn't otherwise qualify — still surface.
            subtitle = "Prod · stalled in progress"
            due_label = due_label or "STALLED"
            status = status if status != "calm" else "overdue"
            urgency = max(urgency, int(_STALLED_CHAIN_BASE_URGENCY.get("note") or 50))
        stalled = compute_stalled("note", note, now) or task_stalled
        items.append(
            apply_stalled_urgency(
                {
                    "id": note.get("id"),
                    "kind": "note",
                    "title": _title(note, "Untitled note"),
                    "subtitle": subtitle,
                    "branch": "prod",
                    "urgency": urgency,
                    "band": band,
                    "open_items": open_items,
                    "status": status,
                    "due_label": due_label,
                    "overdue_days": overdue_days,
                    "due_at": note.get("due_date"),
                    "action": "open_note",
                    "target_id": note.get("id"),
                    "ts": note.get("task_status_at") or note.get("updated_at"),
                    "dedup_key": f"note:{note.get('id')}",
                    "task_status": note.get("task_status"),
                    "task_status_at": note.get("task_status_at"),
                },
                stalled,
            )
        )

    for task in active_tasks[:8]:
        items.append(
            apply_stalled_urgency(
                {
                    "id": task.get("id"),
                    "kind": "task",
                    "title": _title(task, "Untitled task"),
                    "subtitle": f"Prod · {task.get('schedule') or task.get('status') or 'task'}",
                    "branch": "prod",
                    "urgency": 50,
                    "status": "calm",
                    "due_label": "",
                    "overdue_days": None,
                    "due_at": None,
                    "action": "open_task",
                    "target_id": task.get("id"),
                    "ts": task.get("updated_at"),
                    "dedup_key": f"task:{task.get('id')}",
                },
                compute_stalled("task", task, now),
            )
        )

    # Unread urgent emails past SLA — escalate into the queue (not inbox-only).
    for em in comms_preview or []:
        stalled = compute_stalled("email", em, now)
        if not stalled:
            continue
        eid = str(em.get("id") or "").strip()
        if not eid:
            continue
        items.append(
            apply_stalled_urgency(
                {
                    "id": eid,
                    "kind": "email",
                    "title": str(em.get("subject") or "(no subject)"),
                    "subtitle": "Comms · unread urgent",
                    "branch": "comms",
                    "urgency": 92,
                    "status": "overdue",
                    "due_label": "UNREAD 48H+",
                    "overdue_days": None,
                    "due_at": None,
                    "action": "email",
                    "target_id": eid,
                    "ts": stalled.get("since") or em.get("ts"),
                    "dedup_key": f"email:{eid}",
                },
                stalled,
            )
        )

    _attach_related_to(items)
    _escalate_stalled_chain(items, handoffs=handoffs, jobs=jobs, notes_list=notes_list, active_tasks=active_tasks, now=now)

    items.sort(
        key=lambda x: (
            -int(x.get("urgency") or 0),
            -(_parse_dt(x.get("ts")) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
        )
    )
    return items[:12]


def _attach_related_to(items: List[Dict[str, Any]]) -> None:
    """Attach 1-hop ``related_to: [{kind, id}]`` via one batched lineage lookup."""
    pairs: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for item in items:
        kind = str(item.get("kind") or "").strip()
        oid = str(item.get("id") or "").strip()
        if not kind or not oid:
            item["related_to"] = []
            continue
        key = (kind, oid)
        if key not in seen:
            seen.add(key)
            pairs.append(key)

    related = lineage_for(pairs) if pairs else {}
    for item in items:
        kind = str(item.get("kind") or "").strip()
        oid = str(item.get("id") or "").strip()
        if not kind or not oid:
            item["related_to"] = []
            continue
        neighbors = related.get((kind, oid)) or []
        # Cap to 1-hop surface shape: {kind, id} only (no relation / deeper walk).
        item["related_to"] = [
            {"kind": n["kind"], "id": n["id"]}
            for n in neighbors
            if n.get("kind") and n.get("id")
        ]


# Origins a RELAY handoff row may surface as related_to (job/note/email spawners).
_RELAY_ORIGIN_KINDS = frozenset({"job", "note", "email"})
_RELAY_STATS_WINDOW_DAYS = 7


def _handoff_relay_row(
    h: Dict[str, Any],
    *,
    bucket: str,
    stalled: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Compact handoff row for ``relay_board`` buckets."""
    target = h.get("handoff_target") or "?"
    if bucket == "claimed_stuck":
        subtitle = f"Relay · claimed stuck → {target}"
        due_label = "CLAIMED STUCK"
        status = "overdue"
    elif bucket == "needs_attention":
        subtitle = f"Relay · pick up → {target}"
        due_label = "NEEDS PICKUP"
        status = "overdue"
    else:
        subtitle = f"Relay · in flight → {target}"
        due_label = "IN FLIGHT"
        status = "due"
    row: Dict[str, Any] = {
        "id": h.get("id"),
        "kind": "handoff",
        "title": _title(h, "Handoff"),
        "subtitle": subtitle,
        "meta": subtitle,
        "branch": "relay",
        "bucket": bucket,
        "status": status,
        "due_label": due_label,
        "handoff_target": h.get("handoff_target"),
        "handoff_relay_status": h.get("handoff_relay_status"),
        "action": "agent_bin",
        "target_id": h.get("id"),
        "ts": h.get("handoff_relay_started_at") or h.get("handoff_at") or h.get("updated_at"),
        "related_to": [],
    }
    if stalled:
        row["stalled"] = stalled
    return row


def _build_relay_board(
    handoffs: Optional[Dict[str, Any]] = None,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """RELAY left rail: needs_attention vs claimed_stuck (distinct) + lineage."""
    now = now or datetime.now(timezone.utc)
    handoffs = handoffs or {}
    needs: List[Dict[str, Any]] = []
    stuck: List[Dict[str, Any]] = []
    progress: List[Dict[str, Any]] = []

    for h in handoffs.get("needs_attention") or []:
        needs.append(
            _handoff_relay_row(
                h,
                bucket="needs_attention",
                stalled=compute_stalled("handoff", h, now),
            )
        )

    for h in handoffs.get("in_progress") or []:
        stalled = compute_stalled("handoff", h, now)
        if stalled and stalled.get("reason") == "claimed_stuck":
            stuck.append(_handoff_relay_row(h, bucket="claimed_stuck", stalled=stalled))
        else:
            progress.append(_handoff_relay_row(h, bucket="in_progress"))

    all_rows = needs + stuck + progress
    _attach_related_to(all_rows)
    for row in all_rows:
        # Surface origin only (job/note/email), not sibling/child handoff links.
        row["related_to"] = [
            r
            for r in (row.get("related_to") or [])
            if str(r.get("kind") or "") in _RELAY_ORIGIN_KINDS
        ]

    return {
        "needs_attention": needs,
        "claimed_stuck": stuck,
        "in_progress": progress,
        "counts": {
            "needs_attention": len(needs),
            "claimed_stuck": len(stuck),
            "in_progress": len(progress),
        },
    }


def _handoff_outcome(h: Dict[str, Any]) -> str:
    """Classify a handoff as completed / failed / open for close-rate math."""
    status = str(h.get("handoff_relay_status") or "").strip().lower()
    if status == "failed":
        return "failed"
    if status == "complete" or h.get("archived"):
        return "completed"
    return "open"


def _build_relay_stats(
    handoffs: Optional[Dict[str, Any]] = None,
    *,
    now: Optional[datetime] = None,
    window_days: int = _RELAY_STATS_WINDOW_DAYS,
) -> Dict[str, Any]:
    """RELAY right rail: issued / completed / failed / open + close rate."""
    now = now or datetime.now(timezone.utc)
    handoffs = handoffs or {}
    window = max(1, int(window_days))
    cutoff = now - timedelta(days=window)

    issued = completed = failed = open_count = 0
    for bucket in ("needs_attention", "in_progress", "done"):
        for h in handoffs.get(bucket) or []:
            issued_at = _parse_dt(h.get("handoff_at")) or _parse_dt(h.get("created_at"))
            if issued_at is None or issued_at < cutoff:
                continue
            issued += 1
            outcome = _handoff_outcome(h)
            if outcome == "completed":
                completed += 1
            elif outcome == "failed":
                failed += 1
            else:
                open_count += 1

    close_rate: Optional[float] = None
    if issued > 0:
        close_rate = round(completed / issued, 4)

    return {
        "window_days": window,
        "issued": issued,
        "completed": completed,
        "failed": failed,
        "open": open_count,
        "close_rate": close_rate,
    }


def _jobs_with_related_to(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Copy job rows and attach job→handoff ``related_to`` for AGENCY lists."""
    if not rows:
        return []
    items = [{"kind": "job", "id": r.get("id")} for r in rows]
    _attach_related_to(items)
    out: List[Dict[str, Any]] = []
    for row, item in zip(rows, items):
        enriched = dict(row)
        enriched["related_to"] = item.get("related_to") or []
        out.append(enriched)
    return out


def _normalize_job_funnel(jobs: Dict[str, Any]) -> Dict[str, int]:
    """AGENCY funnel stage counts (ingested/evaluated/ready/applied)."""
    raw = jobs.get("funnel") if isinstance(jobs.get("funnel"), dict) else {}
    return {
        "ingested": int(raw.get("ingested") or 0),
        "evaluated": int(raw.get("evaluated") or 0),
        "ready": int(raw.get("ready") or 0),
        "applied": int(raw.get("applied") or 0),
    }


def _object_lookup_for_stalled(
    *,
    handoffs: Dict[str, Any],
    jobs: Dict[str, Any],
    notes_list: List[Dict[str, Any]],
    active_tasks: List[Dict[str, Any]],
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Index input objects by (kind, id) for stalled-chain neighbor checks."""
    lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for bucket in ("needs_attention", "in_progress"):
        for h in handoffs.get(bucket) or []:
            hid = str(h.get("id") or "").strip()
            if hid:
                lookup[("handoff", hid)] = h
    for bucket in ("needs_review", "ready_to_apply"):
        for job in jobs.get(bucket) or []:
            jid = str(job.get("id") or "").strip()
            if not jid:
                continue
            if bucket == "needs_review":
                lookup[("job", jid)] = {**job, "attention": job.get("attention") or "needs_review"}
            else:
                lookup[("job", jid)] = job
    for note in notes_list:
        nid = str(note.get("id") or "").strip()
        if nid:
            lookup[("note", nid)] = note
            # Promoted tasks may still be notes with task_status.
            lookup[("task", nid)] = note
    for task in active_tasks:
        tid = str(task.get("id") or "").strip()
        if tid:
            lookup[("task", tid)] = task
    return lookup


def _escalate_stalled_chain(
    items: List[Dict[str, Any]],
    *,
    handoffs: Dict[str, Any],
    jobs: Dict[str, Any],
    notes_list: List[Dict[str, Any]],
    active_tasks: List[Dict[str, Any]],
    now: datetime,
) -> None:
    """Raise urgency when a related neighbor is stalled so the chain isn't masked.

    Stalled sources themselves already enter the queue via per-kind builders
    (phase 2); this pass ensures a healthy-looking terminal item cannot sit
    above its stalled dependency's escalated tier.
    """
    lookup = _object_lookup_for_stalled(
        handoffs=handoffs,
        jobs=jobs,
        notes_list=notes_list,
        active_tasks=active_tasks,
    )
    boost = int(STALLED_SLA.get("urgency_boost") or 0)
    stalled_floor: Dict[Tuple[str, str], int] = {}
    for key, obj in lookup.items():
        kind = key[0]
        stalled = compute_stalled(kind, obj, now)
        if kind == "note" and not stalled:
            stalled = compute_stalled("task", obj, now)
        if not stalled:
            continue
        base = int(_STALLED_CHAIN_BASE_URGENCY.get(kind) or 50)
        stalled_floor[key] = base + boost

    if not stalled_floor:
        return

    for item in items:
        floor = 0
        for rel in item.get("related_to") or []:
            rkey = (str(rel.get("kind") or ""), str(rel.get("id") or ""))
            if rkey in stalled_floor:
                floor = max(floor, stalled_floor[rkey])
        if floor:
            item["urgency"] = max(int(item.get("urgency") or 0), floor)


def _build_attention_stack(priority_queue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Triage cards for OPEN DIRECTIVE — matches hero directive set.

    Includes handoffs, agency jobs, and all directive notes already on the
    priority queue (pinned / due / checklist / open items) — not only overdue.
    Tasks stay out of the swipe deck (open via Tasks surface).
    """
    stack: List[Dict[str, Any]] = []
    for item in priority_queue:
        kind = item.get("kind")
        if kind not in ("handoff", "job", "note"):
            continue
        stack.append(
            {
                "id": item.get("id"),
                "kind": kind,
                "title": item.get("title"),
                "subtitle": item.get("subtitle") or "",
                "preview": item.get("subtitle") or "",
                "branch": item.get("branch"),
                "status": item.get("status") or "calm",
                "due_label": item.get("due_label") or "",
                "urgency": item.get("urgency"),
                "action": item.get("action"),
                "target_id": item.get("target_id") or item.get("id"),
                "due_at": item.get("due_at"),
            }
        )
    return stack


def _load_email_urgency_state(owner: str = "") -> Dict[str, Any]:
    """Read cached email urgency scan (if any) for COMMS tab inbox preview."""
    slug = "".join(c if (c.isalnum() or c in "-_.@") else "_" for c in (owner or "default"))
    path = Path(DATA_DIR) / f"email_urgency_state_{slug}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def fetch_comms_inbox_emails(owner: str = "", *, limit: int = 15) -> tuple[List[Dict[str, Any]], str]:
    """Recent INBOX rows for COMMS rail — uses the same list path as /api/email/list."""
    try:
        from routes.email_helpers import _get_email_config, list_emails_sync

        cfg = _get_email_config(None, owner=owner)
        account_id = str(cfg.get("account_id") or "")
        result = list_emails_sync("INBOX", limit, 0, "all", None, None, False, owner)
        if result.get("error"):
            return [], account_id
        return list(result.get("emails") or []), account_id
    except Exception:
        return [], ""


def _urgency_verdict_for_uid(
    per_uid: Dict[str, Any],
    uid: str,
    account_id: str = "",
) -> Dict[str, Any]:
    if not uid or not isinstance(per_uid, dict):
        return {}
    candidates = []
    if account_id:
        candidates.append(f"{account_id}:{uid}")
    candidates.append(uid)
    for key in candidates:
        verdict = per_uid.get(key)
        if isinstance(verdict, dict):
            return verdict
    for key, verdict in per_uid.items():
        if isinstance(verdict, dict) and (key == uid or key.endswith(f":{uid}")):
            return verdict
    return {}


def _comms_preview_row_from_verdict(key: str, verdict: Dict[str, Any]) -> Dict[str, Any]:
    score = int(verdict.get("score") or 0)
    return {
        "id": str(key),
        "subject": str(verdict.get("subject") or "(no subject)"),
        "from": str(verdict.get("from") or ""),
        "score": score,
        "reason": str(verdict.get("reason") or ""),
        "urgent": score >= 2,
        "is_read": False,
        "date_epoch": 0.0,
        "ts": verdict.get("ts"),
        "action": "email",
    }


def _build_comms_preview(
    email_urgency: Optional[Dict[str, Any]],
    inbox_emails: Optional[List[Dict[str, Any]]] = None,
    account_id: str = "",
) -> List[Dict[str, Any]]:
    """Live inbox rows with optional urgency overlay — no fabricated messages."""
    per_uid = (email_urgency or {}).get("per_uid") or {}
    if not isinstance(per_uid, dict):
        per_uid = {}

    items: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for em in inbox_emails or []:
        uid = str(em.get("uid") or "").strip()
        if not uid:
            continue
        row_id = f"{account_id}:{uid}" if account_id else uid
        if row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        verdict = _urgency_verdict_for_uid(per_uid, uid, account_id)
        score = int(verdict.get("score") or 0)
        from_display = str(em.get("from_name") or em.get("from_address") or verdict.get("from") or "")
        items.append(
            {
                "id": row_id,
                "uid": uid,
                "account_id": account_id,
                "subject": str(em.get("subject") or verdict.get("subject") or "(no subject)"),
                "from": from_display,
                "score": score,
                "reason": str(verdict.get("reason") or ""),
                "urgent": score >= 2,
                "is_read": bool(em.get("is_read")),
                "date_epoch": float(em.get("date_epoch") or 0.0),
                "ts": verdict.get("ts"),
                "action": "email",
            }
        )

    if not items and per_uid:
        for key, verdict in per_uid.items():
            if not isinstance(verdict, dict):
                continue
            row_id = str(key)
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            items.append(_comms_preview_row_from_verdict(row_id, verdict))

    items.sort(
        key=lambda x: (
            -int(x.get("score") or 0),
            -(float(x.get("date_epoch") or 0.0)),
            str(x.get("subject") or ""),
        )
    )
    return items[:12]


def _build_comms_focus(
    *,
    now: Optional[datetime] = None,
    window_days: int = COMMS_CONVERSION_WINDOW_DAYS,
) -> Dict[str, Any]:
    """COMMS Message Focus payload — closed-loop conversion from reminded edges."""
    now = now or datetime.now(timezone.utc)
    days = max(1, int(window_days or COMMS_CONVERSION_WINDOW_DAYS))
    since = now - timedelta(days=days)
    conversion_count = count_lineage_edges(relation="reminded", since=since)
    return {
        "conversion_count": conversion_count,
        "conversion_window_days": days,
        "conversion_since": since.isoformat(),
    }


def _patch_comms_branch_health(
    branch_health: List[Dict[str, Any]],
    email_urgency: Optional[Dict[str, Any]],
    comms_preview: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Update comms branch counts from urgency scan and/or live inbox preview."""
    total_unread = int((email_urgency or {}).get("total_unread") or 0)
    total_urgent = int((email_urgency or {}).get("total_urgent") or 0)
    preview = comms_preview or []
    if preview and not total_unread:
        total_unread = sum(1 for m in preview if not m.get("is_read"))
    if preview and not total_urgent:
        total_urgent = sum(1 for m in preview if m.get("urgent"))
    if not preview and not email_urgency:
        return
    for b in branch_health:
        if b.get("id") != "comms":
            continue
        b["count"] = total_unread
        if total_urgent:
            b["state"] = "busy"
            b["summary"] = f"{total_unread} unread · {total_urgent} need triage"
        elif total_unread:
            b["state"] = "alive"
            b["summary"] = f"{total_unread} unread"
        else:
            b["state"] = "online"
            b["summary"] = "Inbox ready"
        break


def _build_branch_health(
    *,
    notes_list: List[Dict[str, Any]],
    docs_list: List[Dict[str, Any]],
    active_tasks: List[Dict[str, Any]],
    paused_tasks: List[Dict[str, Any]],
    attention: int,
    in_progress: int,
    jobs_ready: int,
    jobs_review: int,
    voice_state: str = "standby",
    research_count: int = 0,
) -> List[Dict[str, Any]]:
    pinned = sum(1 for n in notes_list if n.get("pinned"))
    intel_count = len(docs_list) + int(research_count or 0)
    if research_count and docs_list:
        intel_summary = f"{len(docs_list)} documents · {research_count} reports"
    elif research_count:
        intel_summary = f"{research_count} research report{'s' if research_count != 1 else ''}"
    else:
        intel_summary = f"{len(docs_list)} documents"
    intel_state = "alive" if research_count else ("online" if docs_list else "idle")
    intel_action = "research" if research_count else "library"
    return [
        {
            "id": "core",
            "label": "Core",
            "state": "online",
            "count": 0,
            "summary": "Odysseus online",
            "action": "refresh",
        },
        {
            "id": "mem",
            "label": "Mem",
            "state": "online",
            "count": len(notes_list),
            "summary": f"{len(notes_list)} notes · {pinned} pinned",
            "action": "notes",
        },
        {
            "id": "prod",
            "label": "Prod",
            "state": "alive" if active_tasks else "idle",
            "count": len(active_tasks),
            "summary": f"{len(active_tasks)} active · {len(paused_tasks)} paused",
            "action": "tasks",
        },
        {
            "id": "intel",
            "label": "Intel",
            "state": intel_state,
            "count": intel_count,
            "summary": intel_summary,
            "action": intel_action,
        },
        {
            "id": "comms",
            "label": "Comms",
            "state": "online",
            "count": 0,
            "summary": "Inbox ready",
            "action": "email",
        },
        {
            "id": "agency",
            "label": "Agency",
            "state": "busy" if (jobs_ready or jobs_review) else "idle",
            "count": jobs_ready + jobs_review,
            "summary": f"{jobs_ready} ready · {jobs_review} review",
            "action": "jobs",
        },
        {
            "id": "relay",
            "label": "Relay",
            "state": "busy" if attention else ("alive" if in_progress else "idle"),
            "count": attention + in_progress,
            "summary": f"{attention} waiting · {in_progress} in flight",
            "action": "agent_bin",
        },
        {
            "id": "voice",
            "label": "Voice",
            "state": "busy" if voice_state in ("listening", "speaking") else (
                "alive" if voice_state in ("armed", "thinking") else "idle"
            ),
            "count": 0,
            "summary": voice_state.replace("_", " ").title(),
            "action": "voice",
        },
    ]


def _build_hero(
    *,
    attention: int,
    in_progress: int,
    jobs_ready: int,
    jobs_review: int,
    jobs: Dict[str, Any],
    priority_queue: List[Dict[str, Any]],
    directives: List[Dict[str, Any]],
    notes_list: List[Dict[str, Any]],
    sessions_list: List[Dict[str, Any]],
    primary_handoff: Optional[Dict[str, Any]],
    plan_note: Optional[Dict[str, Any]],
    overdue_count: int = 0,
    mycelia_feed: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if attention:
        top = priority_queue[0] if priority_queue else {}
        return {
            "label": "Primary Directive — Relay",
            "title": top.get("title") or _title(primary_handoff, "Handoff waiting"),
            "value": attention,
            "unit": "HANDOFFS",
            "velocity": f"{in_progress} agents in flight",
            "explain": f"{attention} handoff(s) need pickup before other work",
            "cta_label": "Open Agent Bin",
            "branch": "relay",
            "action": "agent_bin",
            "target_id": primary_handoff.get("id") if primary_handoff else None,
            "dedup_key": f"handoff:{primary_handoff.get('id')}" if primary_handoff else None,
        }

    if jobs_ready:
        ready = jobs.get("ready_to_apply") or []
        names = ", ".join(
            f"{j.get('company') or '?'}" for j in ready[:3]
        )
        return {
            "label": "Primary Directive — Agency",
            "title": jobs.get("headline") or f"{jobs_ready} job(s) ready to apply",
            "value": jobs_ready,
            "unit": "JOBS READY",
            "velocity": names or jobs.get("headline") or "",
            "explain": "Tailored applications waiting for review and submit",
            "cta_label": "Review job queue",
            "branch": "agency",
            "action": "jobs",
            "target_id": None,
            "dedup_key": f"job:{ready[0].get('id')}" if ready else None,
        }

    if jobs_review:
        needs_review = jobs.get("needs_review") or []
        return {
            "label": "Primary Directive — Agency",
            "title": f"{jobs_review} job(s) need review",
            "value": jobs_review,
            "unit": "NEEDS REVIEW",
            "velocity": jobs.get("headline") or "",
            "explain": "Pipeline flagged roles that need a human decision",
            "cta_label": "Review jobs",
            "branch": "agency",
            "action": "jobs",
            "target_id": None,
            "dedup_key": f"job:{needs_review[0].get('id')}" if needs_review else None,
        }

    if directives:
        top = priority_queue[0] if priority_queue else directives[0]
        # Hero number = actionable overdue count when present (never a
        # separately-maintained "directives" counter that drifts from reality).
        if overdue_count > 0:
            hero_value = overdue_count
            hero_unit = "OVERDUE"
            explain = f"{overdue_count} overdue item(s) need triage"
        else:
            hero_value = len(directives)
            hero_unit = "DIRECTIVES"
            explain = "Pinned, due, or checklist notes need attention"
        return {
            "label": "Primary Directive — Prod",
            "title": top.get("title") or _title(directives[0], "Open directive"),
            "value": hero_value,
            "unit": hero_unit,
            "velocity": top.get("due_label") or top.get("subtitle") or f"{len(sessions_list)} recent chats",
            "explain": explain,
            "cta_label": "Open directive",
            "branch": "prod",
            "action": top.get("action") or "open_note",
            "target_id": top.get("target_id") or top.get("id"),
            "dedup_key": top.get("dedup_key")
            or (f"{top.get('kind')}:{top.get('id')}" if top.get("kind") and top.get("id") else None),
        }

    top3 = (mycelia_feed or {}).get("top3") or []
    if top3:
        first = top3[0]
        board_id = ((mycelia_feed or {}).get("board") or {}).get("id")
        return {
            "label": "Primary Directive — Mycelia",
            "title": first.get("title") or first.get("raw") or "Top priority from blackboard",
            "value": len(top3),
            "unit": "TOP 3",
            "velocity": first.get("rationale") or "From swarm blackboard harvest",
            "explain": "Sporangium's needle-movers for today",
            "cta_label": "Open blackboard",
            "branch": "mycelia",
            "action": "open_doc" if board_id else "tasks",
            "target_id": board_id,
            "dedup_key": "mycelia:top3:1",
        }

    return {
        "label": "Primary Directive — Standby",
        "title": (plan_note and _title(plan_note)) or "Clear deck — nothing queued",
        "value": len(notes_list),
        "unit": "NOTES",
        "velocity": f"{len(sessions_list)} recent chats · all branches calm",
        "explain": "No handoffs, jobs, or directives blocking work",
        "cta_label": "Open notes" if notes_list else "Vault sync",
        "branch": "core",
        "action": "open_note" if plan_note else "refresh",
        "target_id": plan_note.get("id") if plan_note else None,
        "dedup_key": f"note:{plan_note.get('id')}" if plan_note else None,
    }


def _assign_primary_slots(
    *,
    priority_queue: List[Dict[str, Any]],
    hero: Dict[str, Any],
    stage_cards: List[Dict[str, Any]],
    commands: List[Dict[str, Any]],
) -> None:
    """Single-source-of-truth pass: every directive-worthy item gets exactly
    one primary ("act now") slot — the hero when it's top-ranked, else a
    stage card or deck command if one already targets it, else none. Mutates
    priority_queue/stage_cards/commands in place so no panel presents an item
    as the next action when another panel already claims it.
    """
    hero_key = hero.get("dedup_key")

    def _target(entry: Dict[str, Any]) -> str:
        return str(entry.get("target_id") or entry.get("id") or "")

    stage_card_by_target = {_target(c): c.get("id") for c in stage_cards if _target(c)}
    deck_by_target = {_target(c): c.get("id") for c in commands if _target(c)}

    for item in priority_queue:
        key = item.get("dedup_key")
        target = _target(item)
        if key and key == hero_key:
            item["primary_slot"] = "hero"
        elif target in stage_card_by_target:
            item["primary_slot"] = f"stage_card:{stage_card_by_target[target]}"
        elif target in deck_by_target:
            item["primary_slot"] = f"deck:{deck_by_target[target]}"
        else:
            item["primary_slot"] = None

    queue_dedup_by_target = {
        _target(item): item.get("dedup_key") for item in priority_queue if item.get("dedup_key")
    }
    for card in stage_cards:
        dedup_key = queue_dedup_by_target.get(_target(card))
        card["dedup_key"] = dedup_key
        card["primary"] = bool(dedup_key) and dedup_key == hero_key
    for cmd in commands:
        cmd["dedup_key"] = queue_dedup_by_target.get(_target(cmd))


def _build_agenda(
    *,
    calendar_events: List[Dict[str, Any]],
    notes_list: List[Dict[str, Any]],
    active_tasks: List[Dict[str, Any]],
    now: datetime,
) -> Dict[str, Any]:
    """Upcoming calendar events, due/overdue reminders, and the next task run."""
    today = now.date()

    events: List[Dict[str, Any]] = []
    for e in calendar_events or []:
        dt = _parse_dt(e.get("start"))
        if not dt:
            continue
        events.append({**e, "_dt": dt})
    events.sort(key=lambda e: e["_dt"])

    next_event: Optional[Dict[str, Any]] = None
    today_events = 0
    for e in events:
        if e["_dt"].date() == today:
            today_events += 1
        if next_event is None and e["_dt"] >= now:
            next_event = {"uid": e.get("uid"), "title": e.get("title") or "Event", "start": e.get("start")}

    due_soon: List[Dict[str, Any]] = []
    overdue: List[Dict[str, Any]] = []
    for note in notes_list:
        due_dt = _parse_dt(note.get("due_date"))
        if not due_dt:
            continue
        entry = {"id": note.get("id"), "title": _title(note, "Reminder"), "due_date": note.get("due_date")}
        if due_dt < now:
            overdue.append(entry)
        elif (due_dt - now).total_seconds() <= 86400:
            due_soon.append(entry)

    due_soon.sort(key=lambda n: _parse_dt(n.get("due_date")) or datetime.max.replace(tzinfo=timezone.utc))
    overdue.sort(key=lambda n: _parse_dt(n.get("due_date")) or datetime.max.replace(tzinfo=timezone.utc))

    next_task_run: Optional[Dict[str, Any]] = None
    candidates = [t for t in active_tasks if t.get("next_run")]
    candidates.sort(key=lambda t: _parse_dt(t.get("next_run")) or datetime.max.replace(tzinfo=timezone.utc))
    if candidates:
        t = candidates[0]
        next_task_run = {"id": t.get("id"), "name": _title(t, "Task"), "next_run": t.get("next_run")}

    return {
        "next_event": next_event,
        "today_events": today_events,
        "due_soon": due_soon[:5],
        "overdue": overdue[:5],
        "next_task_run": next_task_run,
    }


def _build_up_next_card(agenda: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    base = {"id": "up_next", "label": "Up Next", "branch": "comms"}

    next_event = agenda.get("next_event")
    if next_event:
        rel = _relative_time(_parse_dt(next_event.get("start")), now)
        title = next_event.get("title") or "Upcoming event"
        return {
            **base,
            "subtitle": f"{title} · {rel}" if rel else title,
            "action": "calendar",
            "target_id": next_event.get("uid"),
        }

    due_soon = agenda.get("due_soon") or []
    if due_soon:
        item = due_soon[0]
        rel = _relative_time(_parse_dt(item.get("due_date")), now)
        title = item.get("title") or "Reminder"
        return {
            **base,
            "subtitle": f"{title} · {rel}" if rel else title,
            "action": "open_note",
            "target_id": item.get("id"),
        }

    next_task = agenda.get("next_task_run")
    if next_task:
        rel = _relative_time(_parse_dt(next_task.get("next_run")), now)
        name = next_task.get("name") or "Task"
        return {
            **base,
            "subtitle": f"{name} · {rel}" if rel else name,
            "action": "open_task",
            "target_id": next_task.get("id"),
        }

    return {**base, "subtitle": "Nothing scheduled", "action": "calendar", "target_id": None}


def _compute_payload_hash(payload: Dict[str, Any]) -> str:
    """Deterministic hash over cmd-center payload content — excludes fields
    that change on every call regardless of underlying data (`synced_at`,
    nested `generated_at` / `conversion_since`) or that a caller may have
    skipped (`globe_graph`, `payload_hash` itself), so an otherwise-identical
    poll always hashes the same."""
    volatile = frozenset({"synced_at", "globe_graph", "payload_hash", "generated_at", "conversion_since"})

    def _strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: _strip(v) for k, v in value.items() if k not in volatile}
        if isinstance(value, list):
            return [_strip(v) for v in value]
        return value

    blob = json.dumps(_strip(payload), sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def build_cmd_center(
    *,
    notes: Iterable[Dict[str, Any]],
    documents: Iterable[Dict[str, Any]],
    tasks: Iterable[Dict[str, Any]],
    sessions: Iterable[Dict[str, Any]],
    handoffs: Optional[Dict[str, Any]] = None,
    jobs: Optional[Dict[str, Any]] = None,
    voice: Optional[Dict[str, Any]] = None,
    task_runs: Optional[Iterable[Dict[str, Any]]] = None,
    calendar_events: Optional[Iterable[Dict[str, Any]]] = None,
    email_urgency: Optional[Dict[str, Any]] = None,
    inbox_emails: Optional[List[Dict[str, Any]]] = None,
    inbox_account_id: str = "",
    owner: str = "",
    include_globe: bool = True,
) -> Dict[str, Any]:
    notes_list = [n for n in notes if not n.get("archived")]
    docs_list = [d for d in documents if not d.get("archived")]
    tasks_list = list(tasks)
    sessions_list = list(sessions)
    runs_list = list(task_runs or [])
    calendar_events_list = list(calendar_events or [])
    handoffs = handoffs or {}
    jobs = jobs or {}
    voice = voice or {}
    try:
        recent_research = list_recent_research_reports(
            owner=owner or "", limit=8, include_excerpt=True,
        )
    except Exception:
        recent_research = []
    if email_urgency is None and owner:
        email_urgency = _load_email_urgency_state(owner)
    email_urgency = email_urgency or {}
    comms_preview = _build_comms_preview(email_urgency, inbox_emails, inbox_account_id)

    active_tasks = [t for t in tasks_list if (t.get("status") or "").lower() in ("active", "running", "idle", "")]
    paused_tasks = [t for t in tasks_list if (t.get("status") or "").lower() == "paused"]
    attention = int(handoffs.get("counts", {}).get("needs_attention") or 0)
    in_progress = int(handoffs.get("counts", {}).get("in_progress") or 0)
    jobs_ready = int(jobs.get("ready_to_apply_count") or 0)
    jobs_review = int(jobs.get("needs_review_count") or 0)

    plan_note = _find_plan_note(notes_list)
    morning_note = _find_morning_note(notes_list)
    plan_note_id = plan_note.get("id") if plan_note else None
    today_plan = _build_today_plan(notes_list)

    # --- Mycelia swarm wiring -------------------------------------------------
    # Membership comes from services.home.swarm_registry (explicit metadata),
    # never from an ID-prefix or coincidental title substring.
    swarm_tasks = filter_swarm_tasks(tasks_list)
    swarm_active = [t for t in swarm_tasks if (t.get("status") or "").lower() in ("active", "running")]
    swarm_paused = [t for t in swarm_tasks if (t.get("status") or "").lower() == "paused"]
    swarm_by_id = {t.get("id"): t for t in swarm_tasks}
    swarm_docs = resolve_swarm_docs(docs_list)

    mycelia_commands: List[Dict[str, Any]] = []

    if swarm_tasks:
        for spec in dispatchable_task_specs():
            if spec.task_id not in swarm_by_id:
                continue
            mycelia_commands.append({
                "id": spec.command_id,
                "label": spec.command_label,
                "action": "run_task",
                "target_id": spec.task_id,
                "group": "Mycelia",
            })
        mycelia_commands.append({"id": "myc_tasks", "label": "All Agents", "action": "tasks", "group": "Mycelia"})
        for doc_spec in SWARM_DOCS:
            doc = swarm_docs.get(doc_spec.key)
            if not doc:
                continue
            mycelia_commands.append({
                "id": doc_spec.command_id,
                "label": doc_spec.command_label,
                "action": "open_doc",
                "target_id": doc.get("id"),
                "group": "Mycelia",
            })

    # CEO Brief voice rundown — always available (the action gathers state on
    # demand, so it works even before the swarm has run). Sits atop the Mycelia
    # group so it's the first thing the user reaches for in the morning.
    mycelia_commands.insert(0, {"id": "myc_ceo", "label": "CEO Brief ▶", "action": "ceo_brief",
                                "group": "Mycelia"})

    # --- Agent activity feed (results of agents at work) ----------------------
    def _snippet(txt: Any, n: int = 96) -> str:
        t = " ".join(str(txt or "").split())
        return (t[: n - 1] + "…") if len(t) > n else t

    def _agent_label(name: Any) -> str:
        s = str(name or "Agent").strip()
        for pre in ("Swarm · ", "Swarm - ", "Swarm "):
            if s.startswith(pre):
                return s[len(pre):].strip()
        return s

    agent_activity: List[Dict[str, Any]] = []
    for r in runs_list:
        tid = str(r.get("task_id") or "")
        st = (r.get("status") or "").lower()
        mark = "✓" if st in ("success", "completed", "ok") else ("!" if st == "error" else "·")
        label = _agent_label(r.get("task_name"))
        raw = _snippet(r.get("result") or r.get("error") or "", 240)
        agent_activity.append({
            "id": r.get("id"),
            "agent": label,
            "status": st or "running",
            "icon": mark,
            "label": label,
            "text": f"{mark} {label}",
            "raw": raw,
            "swarm": is_swarm_task_id(tid),
            "ts": r.get("finished_at") or r.get("started_at"),
            "tokens": r.get("tokens_used"),
            "action": "open_task",
            "target_id": tid,
        })
    agent_activity.sort(key=lambda a: (
        0 if a["swarm"] else 1,
        -(_parse_dt(a.get("ts")) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
    ))
    agent_activity = agent_activity[:10]

    mycelia_feed = build_mycelia_feed(
        documents=docs_list,
        notes=notes_list,
        agent_activity=agent_activity,
        now=datetime.now(timezone.utc),
    )
    if swarm_tasks:
        health = mycelia_feed.get("health") or {}
        if health.get("fragmented") and "swarm-t-loam" in swarm_by_id:
            mycelia_commands.append({
                "id": "myc_loam",
                "label": "Run Loam Tidy",
                "action": "run_task",
                "target_id": "swarm-t-loam",
                "group": "Mycelia",
            })

    vitals = [
        {
            "id": "notes",
            "label": "Notes",
            "value": len(notes_list),
            "display": str(len(notes_list)),
            "delta": f"{sum(1 for n in notes_list if n.get('pinned'))} pinned",
            "action": "notes",
        },
        {
            "id": "documents",
            "label": "Documents",
            "value": len(docs_list),
            "display": str(len(docs_list)),
            "delta": f"{len(docs_list)} active",
            "action": "library",
        },
        {
            "id": "tasks",
            "label": "Scheduled Tasks",
            "value": len(active_tasks),
            "display": str(len(active_tasks)),
            "delta": f"{len(paused_tasks)} paused",
            "action": "tasks",
        },
        {
            "id": "agent_bin",
            "label": "Agent Bin",
            "value": attention,
            "display": str(attention),
            "delta": f"{in_progress} in flight",
            "action": "agent_bin",
        },
    ]

    priority_queue = _build_priority_queue(
        notes_list=notes_list,
        active_tasks=active_tasks,
        handoffs=handoffs,
        jobs=jobs,
        comms_preview=comms_preview,
        now=datetime.now(timezone.utc),
    )
    if mycelia_feed.get("top3"):
        priority_queue.extend(mycelia_priority_queue_items(mycelia_feed))
        priority_queue.sort(key=lambda i: -int(i.get("urgency") or 0))

    attention_stack = _build_attention_stack(priority_queue)

    directives = [
        {
            "id": item.get("id"),
            "kind": item.get("kind"),
            "title": item.get("title"),
            "meta": item.get("subtitle", ""),
            "status": item.get("status") or "calm",
            "due_label": item.get("due_label") or "",
            "overdue_days": item.get("overdue_days"),
            "due_at": item.get("due_at"),
            "open_items": int(item.get("open_items") or 0),
            "band": item.get("band") or "",
            "action": item.get("action"),
            "target_id": item.get("target_id"),
            "branch": item.get("branch"),
            "urgency": item.get("urgency"),
            "task_status": item.get("task_status"),
            "task_status_at": item.get("task_status_at"),
            "related_to": item.get("related_to") or [],
            "stalled": item.get("stalled"),
        }
        for item in priority_queue[:10]
    ]

    docs_out = []
    for doc in sorted(
        docs_list,
        key=lambda d: _parse_dt(d.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[:8]:
        docs_out.append(
            {
                "id": doc.get("id"),
                "title": _title(doc, "Untitled doc"),
                "tag": _doc_lang_tag(doc.get("language")),
                "size": _doc_size_label(doc.get("content")),
                "updated_at": doc.get("updated_at"),
                "action": "open_doc",
            }
        )

    notes_preview = build_notes_preview(notes_list)

    now = datetime.now(timezone.utc)
    agenda = _build_agenda(
        calendar_events=calendar_events_list,
        notes_list=notes_list,
        active_tasks=active_tasks,
        now=now,
    )

    top_handoff = (handoffs.get("needs_attention") or [None])[0]

    morning_subtitle = jobs.get("headline") or (morning_note and _title(morning_note))
    if not morning_subtitle:
        morning_subtitle = f"{agenda['today_events']} events · {len(agenda['due_soon'])} due today"

    tp_sum = today_plan.get("summary") or {}
    if tp_sum.get("total"):
        bits = []
        if tp_sum.get("stale"):
            bits.append(f"{tp_sum['stale']} stale")
        if tp_sum.get("overdue"):
            bits.append(f"{tp_sum['overdue']} overdue")
        if tp_sum.get("fat"):
            bits.append(f"{tp_sum['fat']} fat")
        if tp_sum.get("open_items"):
            bits.append(f"{tp_sum['open_items']} open items")
        plan_subtitle = " · ".join(bits) if bits else f"{tp_sum['total']} to triage"
    elif plan_note:
        plan_subtitle = f"{_note_open_items(plan_note)} open · {len(agenda['overdue'])} overdue"
    else:
        plan_subtitle = "Create today's plan"

    # Today's CEO Brief — UUID Library docs or legacy ceo-brief-{date} ids.
    ceo_brief = select_ceo_brief(docs_list)
    ceo_doc = {"id": ceo_brief.get("id"), "title": ceo_brief.get("title")} if ceo_brief.get("id") else None
    ceo_subtitle = (
        f"{'Ready' if ceo_brief.get('status') == 'ready' else 'Stale'} · {ceo_brief.get('title') or 'CEO Brief'}"
        if ceo_brief.get("id") else "Morning chron wave → voice rundown"
    )
    # Stage cards: one Plan Today, no Vault Sync (header sync + deck cover that).
    stage_cards = [
        {
            "id": "ceo_brief",
            "label": "CEO Brief ▶",
            "subtitle": ceo_subtitle,
            "action": "ceo_brief",
            "target_id": ceo_doc.get("id") if ceo_doc else None,
            "branch": "core",
        },
        {
            "id": "morning_report",
            "label": "Morning Report",
            "subtitle": morning_subtitle,
            "action": "jobs" if (jobs_ready or jobs_review) else ("open_note" if morning_note else "notes"),
            "target_id": morning_note.get("id") if morning_note else None,
            "branch": "agency",
        },
        {
            "id": "agent_relay",
            "label": "Agent Relay",
            "subtitle": (
                f"{_title(top_handoff)} → {top_handoff.get('handoff_target') or '?'}"
                if top_handoff
                else f"{in_progress} in flight · {attention} waiting"
            ),
            "action": "agent_bin",
            "target_id": top_handoff.get("id") if top_handoff else None,
            "branch": "relay",
        },
        {
            "id": "plan_today",
            "label": "Plan Today",
            "subtitle": plan_subtitle,
            "action": "plan_today",
            "target_id": plan_note_id,
            "branch": "prod",
        },
        _build_up_next_card(agenda, now),
    ]

    overdue_count = len(agenda.get("overdue") or [])
    # Prefer queue-derived overdue when agenda missed a due note edge case.
    queue_overdue = sum(1 for i in priority_queue if i.get("status") == "overdue" and i.get("kind") == "note")
    if queue_overdue > overdue_count:
        overdue_count = queue_overdue

    primary_handoff = top_handoff
    hero = _build_hero(
        attention=attention,
        in_progress=in_progress,
        jobs_ready=jobs_ready,
        jobs_review=jobs_review,
        jobs=jobs,
        priority_queue=priority_queue,
        directives=directives,
        notes_list=notes_list,
        sessions_list=sessions_list,
        primary_handoff=primary_handoff,
        plan_note=plan_note,
        overdue_count=overdue_count,
        mycelia_feed=mycelia_feed,
    )

    wire_events: List[Dict[str, Any]] = []
    for note in notes_list[:6]:
        wire_events.append(
            {
                "ts": note.get("updated_at"),
                "branch": "prod",
                "text": f"NOTE · {_title(note)}",
                "action": "open_note",
                "target_id": note.get("id"),
            }
        )
    for doc in docs_out[:4]:
        wire_events.append(
            {
                "ts": doc.get("updated_at"),
                "branch": "intel",
                "text": f"DOC · {doc['title']}",
                "action": "open_doc",
                "target_id": doc.get("id"),
            }
        )
    for rp in recent_research[:3]:
        wire_events.append(
            {
                "ts": rp.get("completed_at_iso"),
                "branch": "intel",
                "text": f"RESEARCH · {rp.get('title') or rp.get('query') or 'Report'}",
                "action": "research",
                "target_id": rp.get("id"),
            }
        )
    for h in (handoffs.get("needs_attention") or [])[:3]:
        wire_events.append(
            {
                "ts": h.get("handoff_at") or h.get("updated_at"),
                "branch": "relay",
                "text": f"HANDOFF · {_title(h)} → {h.get('handoff_target') or '?'}",
                "action": "agent_bin",
                "target_id": h.get("id"),
            }
        )
    for line in (jobs.get("summary_lines") or [])[:3]:
        wire_events.append({"ts": None, "branch": "agency", "text": f"JOBS · {line}", "action": "jobs", "target_id": None})
    for sess in sessions_list[:4]:
        wire_events.append(
            {
                "ts": sess.get("last_message_at"),
                "branch": "chat",
                "text": f"CHAT · {_title(sess, 'Untitled chat')}",
                "action": "open_session",
                "target_id": sess.get("id"),
            }
        )

    for a in [x for x in agent_activity if x.get("swarm")][:6]:
        wire_events.append({
            "ts": a.get("ts"),
            "branch": "mycelia",
            "text": f"SWARM · {a.get('label') or a.get('agent') or 'agent'}",
            "action": "open_task",
            "target_id": a.get("target_id"),
        })
    for sig in (mycelia_feed.get("signals") or [])[:4]:
        target = sig.get("target") or "guild"
        wire_events.append({
            "ts": sig.get("date"),
            "branch": "mycelia",
            "text": f"SIGNAL · {sig.get('agent') or 'agent'} → {target}: {str(sig.get('text') or '')[:80]}",
            "action": sig.get("action") or "open_doc",
            "target_id": sig.get("source_id"),
        })

    wire_events.sort(key=lambda e: _parse_dt(e.get("ts")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    commands = [
        {"id": "notes", "label": "Notes", "action": "notes", "group": "Foundation"},
        {"id": "plan_today", "label": "Plan Today", "action": "plan_today", "group": "Foundation", "target_id": plan_note_id},
        {"id": "tasks", "label": "Tasks", "action": "tasks", "group": "Foundation"},
        {"id": "calendar", "label": "Calendar", "action": "calendar", "group": "Foundation"},
        {"id": "inbox", "label": "Inbox Brief", "action": "email", "group": "Intel"},
        {"id": "research", "label": "Research", "action": "research", "group": "Intel"},
        {"id": "library", "label": "Library", "action": "library", "group": "Intel"},
        {"id": "am_report", "label": "AM Report", "action": "jobs", "group": "Agency"},
        {"id": "agent_bin", "label": "Agent Bin", "action": "agent_bin", "group": "Agency"},
        {"id": "relay_watcher", "label": "Install Relay", "action": "relay_watcher", "group": "Ops"},
        # DISABLED: Start Clicky calls POST /api/clicky/start, which runs inside the Docker
        # Linux container and cannot spawn the Windows WPF overlay (see clicky_launcher.IS_WINDOWS).
        # Host launch: deploy/scripts/start-clicky.ps1 on Windows. Re-enable when native Windows
        # Odysseus or a host-side launcher bridge exists.
        # {"id": "start_clicky", "label": "Start Clicky", "action": "start_clicky", "group": "Ops"},
        {"id": "refresh", "label": "Vault Sync", "action": "refresh", "group": "Ops"},
    ]

    # Insert the Mycelia group right after Foundation (first 4 commands).
    if mycelia_commands:
        commands = commands[:4] + mycelia_commands + commands[4:]

    # Signal registry: one primary "act now" slot per item, everywhere else
    # passive. Must run after hero/stage_cards/commands all exist.
    _assign_primary_slots(
        priority_queue=priority_queue,
        hero=hero,
        stage_cards=stage_cards,
        commands=commands,
    )
    _pq_by_id = {str(it.get("id")): it for it in priority_queue}
    for _d in directives:
        _src = _pq_by_id.get(str(_d.get("id")))
        if _src:
            _d["dedup_key"] = _src.get("dedup_key")
            _d["primary_slot"] = _src.get("primary_slot")

    suggested_commands: List[Dict[str, Any]] = []
    branch = hero.get("branch") or "core"
    if branch == "relay":
        suggested_commands = [
            {"id": "s_agent", "label": "Agent Bin", "action": "agent_bin"},
            {"id": "s_relay", "label": "Install Relay", "action": "relay_watcher"},
        ]
    elif branch == "agency":
        suggested_commands = [
            {"id": "s_jobs", "label": "Review jobs", "action": "jobs"},
            {"id": "s_am", "label": "AM Report", "action": "jobs"},
        ]
    else:
        # Plan Today lives on the stage card + Foundation deck — don't triple it here.
        suggested_commands = [
            {"id": "s_inbox", "label": "Inbox Brief", "action": "email"},
            {"id": "s_calendar", "label": "Calendar", "action": "calendar"},
        ]
    # Vault Sync is on the header clock + Ops deck — skip the suggested duplicate.

    # Generalized dedup: never suggest the exact action the hero CTA already
    # performs — extends the ad hoc Vault Sync / Plan Today skips above into
    # one rule (see vault-signal-priority spec).
    if hero.get("dedup_key"):
        suggested_commands = [c for c in suggested_commands if c.get("action") != hero.get("action")]

    voice_state = str(voice.get("state") or "standby")
    branch_health = _build_branch_health(
        notes_list=notes_list,
        docs_list=docs_list,
        active_tasks=active_tasks,
        paused_tasks=paused_tasks,
        attention=attention,
        in_progress=in_progress,
        jobs_ready=jobs_ready,
        jobs_review=jobs_review,
        voice_state=voice_state,
        research_count=len(recent_research),
    )

    if swarm_tasks:
        health = mycelia_feed.get("health") or {}
        mycelia_state = "alive" if swarm_active else ("armed" if swarm_paused else "idle")
        if health.get("fragmented"):
            mycelia_state = "busy"
        branch_health.append({
            "id": "mycelia",
            "label": "Mycelia",
            "state": mycelia_state,
            "count": len(swarm_tasks),
            "summary": (
                f"{health.get('summary')}"
                if health.get("fragmented")
                else f"{len(swarm_active)} active · {len(swarm_paused)} paused"
            ),
            "action": "tasks",
        })

    _patch_comms_branch_health(branch_health, email_urgency, comms_preview)

    status = [
        {"id": b["id"], "label": b["label"], "state": b["state"], "action": b["action"], "summary": b["summary"]}
        for b in branch_health
        if b["id"] in ("core", "mem", "prod", "comms", "agency", "relay", "mycelia")
    ]

    synced_at = datetime.now(timezone.utc).isoformat()

    # Globe graph is the most expensive step (MemPalace network call + a full
    # rebuild) and changes far less often than notes/tasks — skip it entirely
    # on requests that don't need it (e.g. the default 30s live poll) instead
    # of recomputing and discarding it.
    globe_graph: Optional[Dict[str, Any]] = None
    if include_globe:
        projects_payload = build_recent_projects(notes_list, docs_list, project_limit=5, items_per_project=5)
        mp_nodes, mp_edges, mp_status = fetch_mempalace_globe_graph()
        globe_graph = build_globe_graph(
            notes=notes_list,
            documents=docs_list,
            tasks=tasks_list,
            handoffs=handoffs,
            priority_queue=priority_queue,
            agent_activity=agent_activity,
            projects=projects_payload,
            calendar_events=calendar_events_list,
            mempalace_nodes=mp_nodes,
            mempalace_edges=mp_edges,
            mempalace_status=mp_status,
        )

    # BRIEF ME script (Phase 3) — speech lines + orb highlight cues.
    try:
        from services.voice.vault_brief import build_brief_script

        brief_script = build_brief_script(
            hero=hero,
            priority_queue=priority_queue,
            counts={
                "handoffs_attention": attention,
                "handoffs_in_progress": in_progress,
                "jobs_ready": jobs_ready,
                "jobs_review": jobs_review,
            },
            agenda=agenda,
            overdue_count=overdue_count,
            research=recent_research,
            failed_runs=[
                r for r in runs_list
                if str(r.get("status") or "").lower() in ("error", "failed", "timeout")
            ],
            jobs=jobs,
            handoffs=handoffs,
        )
    except Exception:  # pragma: no cover - never block HUD on brief builder
        brief_script = []

    relay_board = _build_relay_board(handoffs, now=datetime.now(timezone.utc))
    relay_stats = _build_relay_stats(handoffs, now=datetime.now(timezone.utc))
    claimed_stuck = int((relay_board.get("counts") or {}).get("claimed_stuck") or 0)

    payload: Dict[str, Any] = {
        "title": "V.A.U.L.T.",
        "subtitle": "Odysseus Command Center",
        "synced_at": synced_at,
        "status": status,
        "branch_health": branch_health,
        "vitals": vitals,
        "priority_queue": priority_queue,
        "agent_activity": agent_activity,
        "directives": directives,
        "documents": docs_out,
        "notes_preview": notes_preview,
        "comms_preview": comms_preview,
        "comms_focus": _build_comms_focus(now=datetime.now(timezone.utc)),
        "relay_board": relay_board,
        "relay_stats": relay_stats,
        "stage_cards": stage_cards,
        "hero": hero,
        "commands": commands,
        "suggested_commands": suggested_commands,
        "wire": wire_events[:16],
        "jobs_detail": {
            "ready_to_apply": _jobs_with_related_to(list(jobs.get("ready_to_apply") or [])),
            "needs_review": _jobs_with_related_to(list(jobs.get("needs_review") or [])),
            "headline": jobs.get("headline"),
            "funnel": _normalize_job_funnel(jobs),
        },
        "plan_note_id": plan_note_id,
        "today_plan": today_plan,
        "ceo_brief": ceo_brief,
        "audio": {
            "tts": voice_state,
            "label": voice.get("label") or "TTS Standby",
            "hint": "Tap Audio or hold Space 3s · delegate in agent voice · Esc dismisses vault",
        },
        "counts": {
            "notes": len(notes_list),
            "documents": len(docs_list),
            "tasks": len(tasks_list),
            "sessions": len(sessions_list),
            "handoffs_attention": attention,
            "handoffs_in_progress": in_progress,
            "handoffs_claimed_stuck": claimed_stuck,
            "jobs_ready": jobs_ready,
            "jobs_review": jobs_review,
        },
        "agenda": agenda,
        "brief_script": brief_script,
        "attention_stack": attention_stack,
        "mycelia_feed": mycelia_feed,
    }
    if include_globe:
        payload["globe_graph"] = globe_graph

    # Content hash for the poll short-circuit (see routes/home_routes.py) —
    # excludes synced_at (changes every call regardless of data) so an
    # otherwise-identical poll produces the same hash.
    payload["payload_hash"] = _compute_payload_hash(payload)
    return payload
