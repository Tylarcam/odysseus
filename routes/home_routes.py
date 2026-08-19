"""Home dashboard routes — recent projects with notes and documents."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request
from sqlalchemy import func

from core.database import Document, Note, ScheduledTask, SessionLocal, TaskRun
from core.database import Session as DbSession
from core.database import get_upcoming_events
from routes.document_helpers import _owner_session_filter
from services.home.cmd_center import build_cmd_center, fetch_comms_inbox_emails
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
        "task_status": getattr(n, "task_status", None),
        "task_status_at": getattr(n, "task_status_at", None),
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
        since_hash: Optional[str] = Query(
            None, description="Last-seen payload_hash — matching hash short-circuits to a minimal response"
        ),
        include_globe: bool = Query(
            True, description="Compute globe_graph (MemPalace fetch + rebuild) — false on the hot poll path"
        ),
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

            inbox_emails, inbox_account_id = [], ""
            try:
                inbox_emails, inbox_account_id = await asyncio.to_thread(
                    fetch_comms_inbox_emails, user or ""
                )
            except Exception:
                logger.debug("COMMS inbox preview skipped", exc_info=True)

            payload = build_cmd_center(
                notes=notes,
                documents=documents,
                tasks=tasks,
                sessions=sessions,
                handoffs=handoffs,
                jobs=jobs,
                task_runs=task_runs,
                calendar_events=calendar_events,
                inbox_emails=inbox_emails,
                inbox_account_id=inbox_account_id,
                owner=user or "",
                include_globe=include_globe,
            )
            if since_hash and payload.get("payload_hash") == since_hash:
                return {
                    "unchanged": True,
                    "synced_at": payload["synced_at"],
                    "payload_hash": payload["payload_hash"],
                }
            return payload
        finally:
            db.close()

    def _ceo_brief_payload(db, user: Optional[str], *, compiled=None, result: Optional[str] = None, ok: bool = True) -> Dict[str, Any]:
        from services.documents.audio_brief import get_brief_state
        from services.documents.ceo_brief_store import load_ceo_brief_snapshot

        snap = load_ceo_brief_snapshot(db, user)
        state = get_brief_state(snap["id"]) or {} if snap.get("id") else {}
        out = dict(snap)
        out["ok"] = bool(ok)
        out["result"] = result
        out["audio_status"] = state.get("status") or ("pending" if snap.get("id") else "pending")
        out["chunk_count"] = int(state.get("chunk_count") or 0)
        out["mime"] = state.get("mime")
        out["error"] = state.get("error")
        out["generated_at"] = state.get("generated_at")
        if compiled is not None:
            out["compiled"] = bool(compiled)
        return out

    @router.post("/ceo-brief")
    async def ceo_brief_run(request: Request) -> Dict[str, Any]:
        """Open today's CEO Brief, compiling only when missing or stale.

        Returns the document body for inline MEM display. Does not require
        the editor — the Library doc is storage only.
        """
        from src.builtin_actions import action_ceo_brief
        user = effective_user(request)
        db = SessionLocal()
        try:
            existing = _ceo_brief_payload(db, user, compiled=False)
            if existing.get("status") == "ready":
                existing["result"] = "Today's CEO brief is ready."
                existing["ok"] = True
                return existing
        finally:
            db.close()

        result, ok = await action_ceo_brief(owner=user)
        db = SessionLocal()
        try:
            payload = _ceo_brief_payload(db, user, compiled=True, result=result, ok=ok)
            if not payload.get("doc_id"):
                payload["result"] = result or "CEO brief compiled but document was not found."
            return payload
        finally:
            db.close()

    @router.get("/ceo-brief/latest")
    def ceo_brief_latest(request: Request) -> Dict[str, Any]:
        """Latest CEO Brief (UUID or legacy id) + body + audio state for MEM."""
        user = effective_user(request)
        db = SessionLocal()
        try:
            payload = _ceo_brief_payload(db, user)
            payload["ok"] = payload.get("status") != "missing"
            return payload
        finally:
            db.close()

    return router
