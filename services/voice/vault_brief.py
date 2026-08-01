#!/usr/bin/env python3
"""Compact vault briefing for Jarvis / Realtime voice sessions.

Injected as system context (≤2k chars) so voice knows Relay/Agency/hero
state without dumping the full CMD Center payload.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_BRIEF_CHARS = 2000
MAX_PRIORITY = 3
MAX_MEMORY = 5


def _clip(text: str, n: int = 120) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


# Branch ids → Domain labels for BRIEF ME highlight payloads (hq-openapi BriefLine).
_DOMAIN_BY_BRANCH = {
    "core": "CORE",
    "mem": "MEM",
    "prod": "PROD",
    "comms": "COMMS",
    "agency": "AGENCY",
    "relay": "RELAY",
    "mycelia": "MYCELIA",
    "intel": "COMMS",
    "chat": "CORE",
    "voice": "CORE",
}


def _domain_label(branch: Optional[str]) -> str:
    key = str(branch or "").strip().lower()
    if key in _DOMAIN_BY_BRANCH:
        return _DOMAIN_BY_BRANCH[key]
    upper = str(branch or "").strip().upper()
    if upper in ("CORE", "MEM", "PROD", "COMMS", "AGENCY", "RELAY", "MYCELIA"):
        return upper
    return "PROD"


def _hl_overdue() -> Dict[str, Any]:
    return {"type": "overdue"}


def _hl_domain(branch: Optional[str]) -> Dict[str, Any]:
    return {"type": "domain", "domain": _domain_label(branch)}


def _hl_all() -> Dict[str, Any]:
    return {"type": "all"}


def _speech_num(n: int, singular: str, plural: str) -> str:
    if n == 1:
        return f"1 {singular}"
    return f"{n} {plural}"


def _speech_overdue_age(days: Optional[int]) -> str:
    if days is None:
        return ""
    try:
        d = int(days)
    except (TypeError, ValueError):
        return ""
    if d <= 0:
        return "due earlier today"
    if d == 1:
        return "one day overdue"
    return f"{d} days overdue"


def _speech_when_future(iso_or_dt: Any) -> str:
    """Relative future phrase for speech — never an ISO timestamp."""
    from datetime import datetime, timezone

    if iso_or_dt is None:
        return ""
    if isinstance(iso_or_dt, datetime):
        dt = iso_or_dt
    else:
        raw = str(iso_or_dt).strip()
        if not raw:
            return ""
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    seconds = (dt - now).total_seconds()
    if seconds < 0:
        return "already started"
    if seconds < 60:
        return "in under a minute"
    if seconds < 3600:
        mins = max(1, int(seconds // 60))
        return f"in {mins} minute{'s' if mins != 1 else ''}"
    if seconds < 86400:
        hours = max(1, int(seconds // 3600))
        return f"in about {hours} hour{'s' if hours != 1 else ''}"
    days = max(1, int(seconds // 86400))
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def build_brief_script(
    *,
    hero: Optional[Dict[str, Any]] = None,
    priority_queue: Optional[List[Dict[str, Any]]] = None,
    counts: Optional[Dict[str, Any]] = None,
    agenda: Optional[Dict[str, Any]] = None,
    overdue_count: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Build a 3–6 line BRIEF ME script with synced highlight cues.

    Each line is ``{text, highlight: {type: overdue|domain|all, domain?}}``.
    Speech-friendly: no ISO dates.
    """
    hero = hero or {}
    priority_queue = list(priority_queue or [])
    counts = counts or {}
    agenda = agenda or {}

    queue_overdue = sum(1 for i in priority_queue if i.get("status") == "overdue")
    agenda_overdue = len(agenda.get("overdue") or [])
    if overdue_count is None:
        overdue_n = max(queue_overdue, agenda_overdue)
        hero_unit = str(hero.get("unit") or "").upper()
        if hero_unit == "OVERDUE":
            try:
                overdue_n = max(overdue_n, int(hero.get("value") or 0))
            except (TypeError, ValueError):
                pass
    else:
        try:
            overdue_n = max(0, int(overdue_count))
        except (TypeError, ValueError):
            overdue_n = max(queue_overdue, agenda_overdue)

    inflight = 0
    for key in ("handoffs_in_progress", "agents_inflight", "in_progress"):
        if counts.get(key) is not None:
            try:
                inflight = max(inflight, int(counts.get(key) or 0))
            except (TypeError, ValueError):
                pass

    lines: List[Dict[str, Any]] = []

    # 1 — overdue / attention
    if overdue_n > 0:
        lines.append(
            {
                "text": (
                    f"Good morning. {_speech_num(overdue_n, 'item needs', 'items need')} "
                    f"your attention — overdue."
                ),
                "highlight": _hl_overdue(),
            }
        )
    else:
        lines.append(
            {
                "text": "Good morning. Nothing is overdue — the deck looks clear.",
                "highlight": _hl_all(),
            }
        )

    # 2 — top priority
    top = priority_queue[0] if priority_queue else None
    if top:
        title = _clip(str(top.get("title") or top.get("label") or "priority item"), 90)
        age = _speech_overdue_age(top.get("overdue_days"))
        if top.get("status") == "overdue":
            text = f"Top priority: {title}. {age}." if age else f"Top priority: {title}."
            lines.append({"text": text, "highlight": _hl_overdue()})
        else:
            branch = top.get("branch") or hero.get("branch")
            lines.append(
                {
                    "text": f"Top priority: {title}.",
                    "highlight": _hl_domain(str(branch) if branch else "prod"),
                }
            )
    elif hero.get("title"):
        title = _clip(str(hero.get("title")), 90)
        lines.append(
            {
                "text": f"Primary directive: {title}.",
                "highlight": _hl_domain(str(hero.get("branch") or "core")),
            }
        )

    # 3 — in-flight agents
    if inflight > 0:
        lines.append(
            {
                "text": (
                    f"{_speech_num(inflight, 'agent is', 'agents are')} in flight "
                    "on the relay."
                ),
                "highlight": _hl_domain("relay"),
            }
        )
    else:
        lines.append(
            {
                "text": "Zero agents in flight.",
                "highlight": _hl_domain("relay"),
            }
        )

    # 4 — calendar / up-next (optional)
    next_event = agenda.get("next_event") or {}
    if next_event.get("title"):
        when = _speech_when_future(next_event.get("start"))
        title = _clip(str(next_event.get("title")), 80)
        when_bit = f" {when}" if when else ""
        lines.append(
            {
                "text": f"Up next on the calendar: {title}{when_bit}.",
                "highlight": _hl_domain("comms"),
            }
        )
    else:
        due_soon = (agenda.get("due_soon") or [])[:1]
        if due_soon:
            item = due_soon[0]
            title = _clip(str(item.get("title") or "reminder"), 80)
            when = _speech_when_future(item.get("due_date"))
            when_bit = f" — {when}" if when else ""
            lines.append(
                {
                    "text": f"Coming due soon: {title}{when_bit}.",
                    "highlight": _hl_domain("prod"),
                }
            )
        else:
            next_task = agenda.get("next_task_run") or {}
            if next_task.get("name") or next_task.get("title"):
                name = _clip(str(next_task.get("name") or next_task.get("title")), 80)
                when = _speech_when_future(next_task.get("next_run"))
                when_bit = f" {when}" if when else ""
                lines.append(
                    {
                        "text": f"Next scheduled task: {name}{when_bit}.",
                        "highlight": _hl_domain("prod"),
                    }
                )

    # 5 — close (always, if room)
    if len(lines) < 6:
        lines.append(
            {
                "text": "That's the state of the V.A.U.L.T.",
                "highlight": _hl_all(),
            }
        )

    # Clamp 3–6 (pad if somehow short).
    while len(lines) < 3:
        lines.append(
            {
                "text": "Vault standing by.",
                "highlight": _hl_all(),
            }
        )
    return lines[:6]


def format_vault_brief(
    *,
    hero: Optional[Dict[str, Any]] = None,
    priority_queue: Optional[List[Dict[str, Any]]] = None,
    counts: Optional[Dict[str, Any]] = None,
    branch_health: Optional[List[Dict[str, Any]]] = None,
    pinned_facts: Optional[List[str]] = None,
    open_note_id: Optional[str] = None,
) -> str:
    """Render a speech-friendly markdown vault brief."""
    hero = hero or {}
    priority_queue = priority_queue or []
    counts = counts or {}
    branch_health = branch_health or []
    pinned_facts = pinned_facts or []

    lines: List[str] = [
        "# Vault brief (live CMD Center)",
        "",
        "You are Jarvis for Odysseus. Use this snapshot to answer "
        "'what's on fire' / status questions. Prefer tools or agent mode "
        "for actions. Keep spoken answers short.",
        "",
    ]

    title = _clip(str(hero.get("title") or "No primary directive"), 160)
    label = _clip(str(hero.get("label") or "Hero"), 80)
    explain = _clip(str(hero.get("explain") or ""), 160)
    lines.append(f"## Primary directive — {label}")
    lines.append(f"- {title}")
    if explain:
        lines.append(f"- {explain}")
    if hero.get("cta_label"):
        lines.append(f"- Suggested action: {_clip(str(hero.get('cta_label')), 80)}")
    lines.append("")

    # Branch snapshot (Relay / Agency / Voice matter most for Jarvis)
    interesting = {
        b.get("id"): b
        for b in branch_health
        if b.get("id") in ("relay", "agency", "voice", "prod", "mycelia", "mem")
    }
    if interesting:
        lines.append("## Branch health")
        for key in ("relay", "agency", "voice", "prod", "mycelia", "mem"):
            b = interesting.get(key)
            if not b:
                continue
            lines.append(
                f"- {b.get('label') or key}: {b.get('state')} — "
                f"{_clip(str(b.get('summary') or ''), 100)}"
            )
        lines.append("")

    if counts:
        lines.append("## Counts")
        lines.append(
            "- "
            + ", ".join(
                f"{k}={v}"
                for k, v in (
                    ("handoffs_waiting", counts.get("handoffs_attention")),
                    ("handoffs_inflight", counts.get("handoffs_in_progress")),
                    ("jobs_ready", counts.get("jobs_ready")),
                    ("jobs_review", counts.get("jobs_review")),
                    ("notes", counts.get("notes")),
                    ("tasks", counts.get("tasks")),
                )
                if v is not None
            )
        )
        lines.append("")

    top = priority_queue[:MAX_PRIORITY]
    if top:
        lines.append("## Top priority")
        for i, item in enumerate(top, 1):
            lines.append(
                f"{i}. {_clip(str(item.get('title') or item.get('label') or 'item'), 100)}"
                + (f" [{item.get('kind')}]" if item.get("kind") else "")
            )
        lines.append("")

    facts = [f for f in pinned_facts if (f or "").strip()][:MAX_MEMORY]
    if facts:
        lines.append("## Pinned memory (use naturally, don't recite)")
        for f in facts:
            lines.append(f"- {_clip(f, 140)}")
        lines.append("")

    if open_note_id:
        lines.append(f"Open note id: {open_note_id}")
        lines.append("")

    text = "\n".join(lines).strip() + "\n"
    if len(text) > MAX_BRIEF_CHARS:
        text = text[: MAX_BRIEF_CHARS - 1] + "…\n"
    return text


def build_vault_brief(owner: Optional[str] = None) -> Dict[str, Any]:
    """Assemble a live vault brief for the given owner (best-effort)."""
    from services.voice.realtime_gateway import _load_pinned_memory_facts

    pinned = _load_pinned_memory_facts(owner)
    hero: Dict[str, Any] = {}
    priority_queue: List[Dict[str, Any]] = []
    counts: Dict[str, Any] = {}
    branch_health: List[Dict[str, Any]] = []

    try:
        payload = _load_cmd_snapshot(owner)
        hero = payload.get("hero") or {}
        priority_queue = payload.get("priority_queue") or []
        counts = payload.get("counts") or {}
        branch_health = payload.get("branch_health") or []
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("vault_brief: cmd snapshot failed: %s", e)
        # Minimal fallback from jobs only
        try:
            from src.job_pipeline.brief import get_jobs_for_brief

            jobs = get_jobs_for_brief(owner=owner)
            counts = {
                "jobs_ready": jobs.get("ready_to_apply_count") or 0,
                "jobs_review": jobs.get("needs_review_count") or 0,
            }
            hero = {
                "label": "Agency",
                "title": jobs.get("headline") or "Job pipeline",
                "explain": f"{counts['jobs_ready']} ready · {counts['jobs_review']} review",
            }
        except Exception as e2:  # pragma: no cover
            logger.warning("vault_brief: jobs fallback failed: %s", e2)

    markdown = format_vault_brief(
        hero=hero,
        priority_queue=priority_queue,
        counts=counts,
        branch_health=branch_health,
        pinned_facts=pinned,
    )
    return {
        "markdown": markdown,
        "chars": len(markdown),
        "owner": owner or "anonymous",
        "hero_title": (hero.get("title") or "")[:160],
        "pinned_count": len(pinned[:MAX_MEMORY]),
    }


def _load_cmd_snapshot(owner: Optional[str]) -> Dict[str, Any]:
    """Reuse CMD Center builder with a trimmed DB fetch (same shape as HUD)."""
    from sqlalchemy import func

    from core.database import Document, Note, ScheduledTask, Session as DbSession, SessionLocal
    from core.database import get_upcoming_events
    from routes.document_helpers import _owner_session_filter
    from routes.home_routes import _note_row_to_cmd
    from services.home.cmd_center import build_cmd_center
    from src.auth_helpers import owner_filter
    from src.handoff_bin import bucket_handoff_notes
    from src.job_pipeline.brief import get_jobs_for_brief

    user = owner
    db = SessionLocal()
    try:
        note_q = db.query(Note).filter(Note.archived == False)  # noqa: E712
        if user:
            note_q = owner_filter(note_q, Note, user)
        notes = [_note_row_to_cmd(n) for n in note_q.order_by(Note.updated_at.desc()).limit(80).all()]

        doc_q = (
            db.query(Document)
            .outerjoin(DbSession, Document.session_id == DbSession.id)
            .filter(Document.is_active == True)  # noqa: E712
            .filter((Document.archived == False) | (Document.archived.is_(None)))  # noqa: E712
        )
        doc_q = _owner_session_filter(doc_q, user)
        documents = [
            {
                "id": doc.id,
                "title": doc.title,
                "content": (doc.current_content or "")[:4000],
                "language": doc.language,
                "archived": bool(doc.archived),
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
            for doc in doc_q.order_by(Document.updated_at.desc()).limit(40).all()
        ]

        task_q = db.query(ScheduledTask)
        if user:
            task_q = task_q.filter(ScheduledTask.owner == user)
        tasks = [
            {
                "id": t.id,
                "name": t.name,
                "prompt": (t.prompt or "")[:200],
                "status": t.status,
                "schedule": t.schedule,
                "next_run": t.next_run.isoformat() if t.next_run else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in task_q.order_by(ScheduledTask.updated_at.desc()).limit(40).all()
        ]

        sess_q = db.query(DbSession).filter(DbSession.archived == False)  # noqa: E712
        if user:
            sess_q = owner_filter(sess_q, DbSession, user)
        activity = func.coalesce(DbSession.last_message_at, DbSession.updated_at, DbSession.created_at)
        sessions = [
            {
                "id": s.id,
                "title": (s.name or "").strip() or "Untitled chat",
                "last_message_at": (
                    (s.last_message_at or s.updated_at or s.created_at).isoformat()
                    if (s.last_message_at or s.updated_at or s.created_at)
                    else None
                ),
            }
            for s in sess_q.filter(DbSession.message_count > 0).order_by(activity.desc()).limit(12).all()
        ]

        handoff_q = db.query(Note).filter(Note.handoff_doc_id.isnot(None))
        if user:
            handoff_q = owner_filter(handoff_q, Note, user)
        handoffs = bucket_handoff_notes(
            [_note_row_to_cmd(n) for n in handoff_q.order_by(Note.updated_at.desc()).limit(40).all()]
        )

        jobs = get_jobs_for_brief(owner=user)
        calendar_events = get_upcoming_events(owner=user, horizon_days=7, limit=10)

        return build_cmd_center(
            notes=notes,
            documents=documents,
            tasks=tasks,
            sessions=sessions,
            handoffs=handoffs,
            jobs=jobs,
            calendar_events=calendar_events,
        )
    finally:
        db.close()
