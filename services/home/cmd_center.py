"""Command Center (V.A.U.L.T.) dashboard aggregation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from services.home.dashboard import build_recent_projects
from services.home.kg_graph import build_globe_graph
from services.mempalace.bridge import fetch_mempalace_globe_graph


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


def _build_priority_queue(
    *,
    notes_list: List[Dict[str, Any]],
    active_tasks: List[Dict[str, Any]],
    handoffs: Dict[str, Any],
    jobs: Dict[str, Any],
) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    items: List[Dict[str, Any]] = []

    for h in handoffs.get("needs_attention") or []:
        target = h.get("handoff_target") or "?"
        items.append(
            {
                "id": h.get("id"),
                "kind": "handoff",
                "title": _title(h, "Handoff"),
                "subtitle": f"Relay · pick up → {target}",
                "branch": "relay",
                "urgency": 100,
                "action": "agent_bin",
                "target_id": h.get("id"),
                "ts": h.get("handoff_at") or h.get("updated_at"),
            }
        )

    for job in jobs.get("needs_review") or []:
        company = job.get("company") or "Company"
        role = job.get("role") or "Role"
        items.append(
            {
                "id": job.get("id"),
                "kind": "job",
                "title": f"{company} — {role}",
                "subtitle": "Agency · needs review",
                "branch": "agency",
                "urgency": 95,
                "action": "jobs",
                "target_id": job.get("id"),
                "ts": job.get("updated_at"),
            }
        )

    for job in jobs.get("ready_to_apply") or []:
        company = job.get("company") or "Company"
        role = job.get("role") or "Role"
        items.append(
            {
                "id": job.get("id"),
                "kind": "job",
                "title": f"{company} — {role}",
                "subtitle": "Agency · ready to apply",
                "branch": "agency",
                "urgency": 90,
                "action": "jobs",
                "target_id": job.get("id"),
                "ts": job.get("updated_at"),
            }
        )

    for note in notes_list:
        if not _is_directive_note(note):
            continue
        open_items = _note_open_items(note)
        meta = note.get("label") or note.get("note_type") or "note"
        subtitle = f"Prod · {meta}"
        if open_items:
            subtitle = f"Prod · {open_items} open item(s)"
        if note.get("due_date"):
            subtitle = f"Prod · due {note.get('due_date')}"
        due_dt = _parse_dt(note.get("due_date"))
        if due_dt and due_dt < now:
            urgency = 85
        elif note.get("due_date"):
            urgency = 80
        elif note.get("pinned"):
            urgency = 70
        else:
            urgency = 60
        items.append(
            {
                "id": note.get("id"),
                "kind": "note",
                "title": _title(note, "Untitled note"),
                "subtitle": subtitle,
                "branch": "prod",
                "urgency": urgency,
                "action": "open_note",
                "target_id": note.get("id"),
                "ts": note.get("updated_at"),
            }
        )

    for task in active_tasks[:8]:
        items.append(
            {
                "id": task.get("id"),
                "kind": "task",
                "title": _title(task, "Untitled task"),
                "subtitle": f"Prod · {task.get('schedule') or task.get('status') or 'task'}",
                "branch": "prod",
                "urgency": 50,
                "action": "open_task",
                "target_id": task.get("id"),
                "ts": task.get("updated_at"),
            }
        )

    items.sort(
        key=lambda x: (
            -int(x.get("urgency") or 0),
            -(_parse_dt(x.get("ts")) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
        )
    )
    return items[:12]


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
) -> List[Dict[str, Any]]:
    pinned = sum(1 for n in notes_list if n.get("pinned"))
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
            "state": "online" if docs_list else "idle",
            "count": len(docs_list),
            "summary": f"{len(docs_list)} documents",
            "action": "library",
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
        }

    if jobs_review:
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
        }

    if directives:
        top = priority_queue[0] if priority_queue else directives[0]
        return {
            "label": "Primary Directive — Prod",
            "title": top.get("title") or _title(directives[0], "Open directive"),
            "value": len(directives),
            "unit": "DIRECTIVES",
            "velocity": top.get("subtitle") or f"{len(sessions_list)} recent chats",
            "explain": "Pinned, due, or checklist notes need attention",
            "cta_label": "Open directive",
            "branch": "prod",
            "action": top.get("action") or "open_note",
            "target_id": top.get("target_id") or top.get("id"),
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
    }


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

    active_tasks = [t for t in tasks_list if (t.get("status") or "").lower() in ("active", "running", "idle", "")]
    paused_tasks = [t for t in tasks_list if (t.get("status") or "").lower() == "paused"]
    attention = int(handoffs.get("counts", {}).get("needs_attention") or 0)
    in_progress = int(handoffs.get("counts", {}).get("in_progress") or 0)
    jobs_ready = int(jobs.get("ready_to_apply_count") or 0)
    jobs_review = int(jobs.get("needs_review_count") or 0)

    plan_note = _find_plan_note(notes_list)
    morning_note = _find_morning_note(notes_list)
    plan_note_id = plan_note.get("id") if plan_note else None

    # --- Mycelia swarm wiring -------------------------------------------------
    # The swarm is native Odysseus rows: tasks id-prefixed "swarm-" + a few docs.
    # Surface it as a first-class branch + command group using existing actions.
    def _find_doc(*keys: str) -> Optional[Dict[str, Any]]:
        for d in docs_list:
            title = _title(d).lower()
            if all(k in title for k in keys):
                return d
        return None

    swarm_tasks = [t for t in tasks_list if str(t.get("id") or "").startswith("swarm-")]
    swarm_active = [t for t in swarm_tasks if (t.get("status") or "").lower() in ("active", "running")]
    swarm_paused = [t for t in swarm_tasks if (t.get("status") or "").lower() == "paused"]
    swarm_coo = next(
        (t for t in swarm_tasks if t.get("id") == "swarm-t-sporangium-am"),
        swarm_tasks[0] if swarm_tasks else None,
    )
    swarm_doc_ledger = _find_doc("fruit", "ledger")
    swarm_doc_doctrine = _find_doc("swarm", "doctrine")
    swarm_doc_board = _find_doc("substrate")

    swarm_by_id = {t.get("id"): t for t in swarm_tasks}
    mycelia_commands: List[Dict[str, Any]] = []

    def _dispatch(cmd_id: str, label: str, task_id: str) -> None:
        # "Send to work" — run_task fires POST /api/tasks/{id}/run from the HUD.
        if task_id in swarm_by_id:
            mycelia_commands.append({"id": cmd_id, "label": label, "action": "run_task",
                                     "target_id": task_id, "group": "Mycelia"})

    if swarm_tasks:
        if swarm_coo:
            mycelia_commands.append({"id": "myc_coo", "label": "Run COO Plan", "action": "run_task",
                                     "target_id": swarm_coo.get("id"), "group": "Mycelia"})
        _dispatch("myc_forager", "Dispatch Forager", "swarm-t-forager")
        _dispatch("myc_rhizo", "Send to Research", "swarm-t-rhizo")
        _dispatch("myc_scout", "Dispatch Scout", "swarm-t-scout")
        mycelia_commands.append({"id": "myc_tasks", "label": "All Agents", "action": "tasks", "group": "Mycelia"})
        if swarm_doc_ledger:
            mycelia_commands.append({"id": "myc_fruit", "label": "Fruit Ledger", "action": "open_doc",
                                     "target_id": swarm_doc_ledger.get("id"), "group": "Mycelia"})
        if swarm_doc_board:
            mycelia_commands.append({"id": "myc_board", "label": "Blackboard", "action": "open_doc",
                                     "target_id": swarm_doc_board.get("id"), "group": "Mycelia"})
        if swarm_doc_doctrine:
            mycelia_commands.append({"id": "myc_doc", "label": "Swarm Doctrine", "action": "open_doc",
                                     "target_id": swarm_doc_doctrine.get("id"), "group": "Mycelia"})

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
        mark = "✓" if st in ("success", "completed", "ok") else ("✗" if st == "error" else "⋯")
        body = _snippet(r.get("result") or r.get("error") or "(running…)")
        agent_activity.append({
            "id": r.get("id"),
            "agent": _agent_label(r.get("task_name")),
            "status": st or "running",
            "text": f"{mark} {body}",
            "swarm": tid.startswith("swarm-"),
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
    )

    directives = [
        {
            "id": item.get("id"),
            "kind": item.get("kind"),
            "title": item.get("title"),
            "meta": item.get("subtitle", ""),
            "open_items": 0,
            "action": item.get("action"),
            "target_id": item.get("target_id"),
            "branch": item.get("branch"),
            "urgency": item.get("urgency"),
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

    if plan_note:
        plan_subtitle = f"{_note_open_items(plan_note)} open · {len(agenda['overdue'])} overdue"
    else:
        plan_subtitle = "Create today's plan"

    # Today's CEO Brief voice rundown — upfront so it's the first card read.
    ceo_doc = next((d for d in docs_list if str(d.get("id") or "").startswith("ceo-brief-")), None)
    ceo_subtitle = (
        f"Voice rundown ready · {ceo_doc.get('title') or 'CEO Brief'}"
        if ceo_doc else "Morning chron wave → voice rundown"
    )
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
            "action": "open_note" if plan_note else "plan_today",
            "target_id": plan_note_id,
            "branch": "prod",
        },
        {
            "id": "metrics_pull",
            "label": "Vault Sync",
            "subtitle": f"{len(notes_list)} notes · {len(docs_list)} docs · {attention} handoffs",
            "action": "refresh",
            "target_id": None,
            "branch": "core",
        },
        _build_up_next_card(agenda, now),
    ]

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
            "text": f"{a['agent']} {a['text']}",
            "action": "open_task",
            "target_id": a.get("target_id"),
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
        suggested_commands = [
            {"id": "s_plan", "label": "Plan Today", "action": "plan_today", "target_id": plan_note_id},
            {"id": "s_inbox", "label": "Inbox Brief", "action": "email"},
        ]
    suggested_commands.append({"id": "s_sync", "label": "Vault Sync", "action": "refresh"})

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
    )

    if swarm_tasks:
        branch_health.append({
            "id": "mycelia",
            "label": "Mycelia",
            "state": "alive" if swarm_active else ("armed" if swarm_paused else "idle"),
            "count": len(swarm_tasks),
            "summary": f"{len(swarm_active)} active · {len(swarm_paused)} paused",
            "action": "tasks",
        })

    status = [
        {"id": b["id"], "label": b["label"], "state": b["state"], "action": b["action"], "summary": b["summary"]}
        for b in branch_health
        if b["id"] in ("core", "mem", "prod", "comms", "agency", "relay", "mycelia")
    ]

    synced_at = datetime.now(timezone.utc).isoformat()

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

    return {
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
        "stage_cards": stage_cards,
        "hero": hero,
        "commands": commands,
        "suggested_commands": suggested_commands,
        "wire": wire_events[:16],
        "jobs_detail": {
            "ready_to_apply": jobs.get("ready_to_apply") or [],
            "needs_review": jobs.get("needs_review") or [],
            "headline": jobs.get("headline"),
        },
        "plan_note_id": plan_note_id,
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
            "jobs_ready": jobs_ready,
            "jobs_review": jobs_review,
        },
        "globe_graph": globe_graph,
        "agenda": agenda,
    }
