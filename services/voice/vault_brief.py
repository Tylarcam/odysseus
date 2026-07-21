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
