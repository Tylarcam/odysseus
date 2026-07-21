"""Home dashboard routes — recent projects with notes and documents."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request
from sqlalchemy import func

from core.database import Document, Note, ScheduledTask, SessionLocal, TaskRun
from core.database import Session as DbSession
from core.database import get_upcoming_events
from routes.document_helpers import _owner_session_filter
from services.home.cmd_center import build_cmd_center
from services.home.dashboard import build_recent_projects
from src.auth_helpers import effective_user, get_current_user
from src.handoff_bin import bucket_handoff_notes

logger = logging.getLogger(__name__)


def _note_row_to_cmd(n: Note) -> Dict[str, Any]:
    items = None
    if n.items:
        try:
            items = json.loads(n.items)
        except (json.JSONDecodeError, TypeError):
            items = None
    return {
        "id": n.id,
        "title": n.title,
        "content": n.content,
        "items": items,
        "label": n.label,
        "note_type": n.note_type,
        "pinned": bool(n.pinned),
        "archived": bool(n.archived),
        "due_date": n.due_date,
        "handoff_doc_id": getattr(n, "handoff_doc_id", None),
        "handoff_target": getattr(n, "handoff_target", None),
        "handoff_at": getattr(n, "handoff_at", None),
        "handoff_relay_status": getattr(n, "handoff_relay_status", None),
        "handoff_outcome": getattr(n, "handoff_outcome", None),
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


def setup_home_routes() -> APIRouter:
    router = APIRouter(prefix="/api/home", tags=["home"])

    @router.get("/recent-projects")
    def recent_projects(
        request: Request,
        limit: int = Query(5, ge=1, le=20),
        items_per_project: int = Query(5, ge=1, le=20),
    ) -> Dict[str, Any]:
        user = get_current_user(request)
        db = SessionLocal()
        try:
            note_q = db.query(Note).filter(Note.archived == False)  # noqa: E712
            if user:
                from src.auth_helpers import owner_filter

                note_q = owner_filter(note_q, Note, user)
            notes = [
                {
                    "id": n.id,
                    "title": n.title,
                    "content": n.content,
                    "label": n.label,
                    "note_type": n.note_type,
                    "archived": n.archived,
                    "updated_at": n.updated_at.isoformat() if n.updated_at else None,
                }
                for n in note_q.all()
            ]

            doc_q = (
                db.query(Document, DbSession.folder)
                .outerjoin(DbSession, Document.session_id == DbSession.id)
                .filter(Document.is_active == True)  # noqa: E712
                .filter(
                    (Document.archived == False) | (Document.archived.is_(None))  # noqa: E712
                )
            )
            doc_q = _owner_session_filter(doc_q, user)
            documents = [
                {
                    "id": doc.id,
                    "title": doc.title,
                    "content": doc.current_content,
                    "language": doc.language,
                    "archived": bool(doc.archived),
                    "session_folder": folder,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                }
                for doc, folder in doc_q.all()
            ]

            return build_recent_projects(
                notes,
                documents,
                project_limit=limit,
                items_per_project=items_per_project,
            )
        finally:
            db.close()

    @router.get("/jobs-attention")
    def jobs_attention(request: Request) -> Dict[str, Any]:
        from src.job_pipeline.brief import get_jobs_for_brief

        # Bearer tokens resolve to the token owner (same data as the browser UI).
        user = effective_user(request)
        return get_jobs_for_brief(owner=user)

    @router.get("/cmd-center")
    async def cmd_center(
        request: Request,
        sync_calendar: bool = Query(False, description="Pull CalDAV before building the vault snapshot"),
    ) -> Dict[str, Any]:
        """V.A.U.L.T. command center — live notes, docs, tasks, handoffs, jobs."""
        from src.auth_helpers import owner_filter
        from src.job_pipeline.brief import get_jobs_for_brief
        from core.database import calendar_owner_key

        # Cookie sessions and bearer tokens both resolve to the real owner so
        # agents and the desktop HUD see the same notes/docs/jobs.
        user = effective_user(request)
        if sync_calendar:
            from src.caldav_sync import sync_caldav

            try:
                await sync_caldav(calendar_owner_key(user))
            except Exception:
                logger.warning("CalDAV sync during vault refresh failed", exc_info=True)
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

            # Recent agent runs (result/status) — powers the Swarm Activity feed.
            run_q = db.query(TaskRun, ScheduledTask).join(
                ScheduledTask, TaskRun.task_id == ScheduledTask.id
            )
            if user:
                run_q = run_q.filter(ScheduledTask.owner == user)
            task_runs = [
                {
                    "id": r.id,
                    "task_id": r.task_id,
                    "task_name": t.name,
                    "status": r.status,
                    "result": (r.result or "")[:400],
                    "error": (r.error or "")[:400],
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                    "tokens_used": r.tokens_used,
                }
                for r, t in run_q.order_by(TaskRun.started_at.desc()).limit(25).all()
            ]

            return build_cmd_center(
                notes=notes,
                documents=documents,
                tasks=tasks,
                sessions=sessions,
                handoffs=handoffs,
                jobs=jobs,
                task_runs=task_runs,
                calendar_events=calendar_events,
            )
        finally:
            db.close()

    @router.post("/ceo-brief")
    async def ceo_brief_run(request: Request) -> Dict[str, Any]:
        """Manually trigger the CEO Brief gather + audio kickoff.
        Runs the same action as the daily chron task so the button produces a
        fresh voice rundown on demand. Returns the doc id + audio status."""
        from src.builtin_actions import action_ceo_brief
        user = effective_user(request)
        result, ok = await action_ceo_brief(owner=user)
        # Locate the doc id the action just wrote.
        from datetime import datetime as _dt
        doc_id = f"ceo-brief-{_dt.now().strftime('%Y-%m-%d')}"
        from services.documents.audio_brief import get_brief_state
        state = get_brief_state(doc_id) or {}
        return {
            "ok": bool(ok),
            "doc_id": doc_id,
            "result": result,
            "audio_status": state.get("status") or "generating",
        }

    @router.get("/ceo-brief/latest")
    def ceo_brief_latest(request: Request) -> Dict[str, Any]:
        """Latest CEO Brief document + its audio-brief playback state.
        The CMD Center button polls this while playing."""
        from datetime import datetime as _dt
        from src.auth_helpers import owner_filter
        from services.documents.audio_brief import get_brief_state

        user = effective_user(request)
        doc_id = f"ceo-brief-{_dt.now().strftime('%Y-%m-%d')}"
        title = f"CEO Brief — {_dt.now().strftime('%Y-%m-%d')}"
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc is None:
                # Fall back to the most recent CEO Brief doc for this owner.
                q = db.query(Document).filter(Document.id.like("ceo-brief-%"))
                if user:
                    q = owner_filter(q, Document, user)
                doc = q.order_by(Document.updated_at.desc()).first()
            if doc is None:
                return {"ok": False, "doc_id": None, "title": title, "audio_status": "pending"}
            state = get_brief_state(doc.id) or {}
            return {
                "ok": True,
                "doc_id": doc.id,
                "title": doc.title or title,
                "audio_status": state.get("status") or "pending",
                "chunk_count": int(state.get("chunk_count") or 0),
                "mime": state.get("mime"),
                "error": state.get("error"),
                "generated_at": state.get("generated_at"),
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
        finally:
            db.close()

    return router
