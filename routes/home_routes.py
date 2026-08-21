"""Home dashboard routes — recent projects with notes and documents."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request
from sqlalchemy import and_, func, or_

from core.database import Document, Note, ScheduledTask, SessionLocal, TaskRun
from core.database import Session as DbSession
from core.database import get_upcoming_events
from routes.document_helpers import _owner_session_filter
from services.home.cmd_center import build_cmd_center, fetch_comms_inbox_emails
from services.home.dashboard import build_recent_projects
from services.documents.ceo_brief_script import (
    GRANT_CATALOG_BODY_CHARS,
    is_grant_catalog_title,
)
from src.auth_helpers import effective_user, get_current_user
from src.handoff_bin import bucket_handoff_notes

logger = logging.getLogger(__name__)

# Vault Sync / cmd-center sit under app.py's 45s REQUEST_HARD_TIMEOUT.
# CalDAV + IMAP in series used to blow that budget and 504 the whole HUD
# (and every other in-flight request waiting on the same event loop).
_VAULT_CALDAV_TIMEOUT_SEC = 15.0
_VAULT_INBOX_TIMEOUT_SEC = 8.0

# Recency-80 / recency-40 can drop Jarvis ranking sources. Always splice
# these stubs back into the HUD snapshot when the rows still exist.
HUD_PINNED_NOTE_PREFIXES = (
    "08e7c105",  # Impact+ nomination-gate packet
    "506a37f1",  # Herald fruit ledger
    "ccd47cbf",  # Objectives charter
    "f1cf1f16",  # Upwork send checklist (HUMAN GATE)
    "4be22ee3",  # NPR Panel 2 thank-you · Greta
    "8504c427",  # NPR Panel 2 thank-you · Kriti
    "80aa4a73",  # NPR Panel 2 thank-you · Nicolette
)
HUD_PINNED_DOC_PREFIXES = (
    "7785722b",  # Grant Scout catalog
    "4f9a694f",  # Upwork Send Pack Library doc (HUMAN GATE)
)


def _is_fruit_ledger_title(title: Optional[str]) -> bool:
    blob = (title or "").lower()
    return "fruit" in blob and "ledger" in blob


def _id8(rid: Optional[str]) -> str:
    return str(rid or "").strip()[:8]


def _snapshot_has_prefix(rows: list, prefix: str) -> bool:
    stub = (prefix or "")[:8]
    return bool(stub) and any(_id8(r.get("id")) == stub for r in rows)


def _id_prefix_filter(column, prefixes: tuple):
    clauses = []
    for prefix in prefixes:
        clauses.append(column == prefix)
        clauses.append(column.like(f"{prefix}%"))
    return or_(*clauses) if clauses else None


def _pick_row_for_prefix(rows, prefix: str):
    stub = (prefix or "")[:8]
    exact = None
    like = None
    for row in rows:
        rid = str(getattr(row, "id", "") or "")
        if rid == prefix or rid == stub:
            exact = row
            break
        if rid.startswith(stub) and like is None:
            like = row
    return exact or like


def _pin_hud_ids(
    db,
    user: Optional[str],
    notes: list,
    documents: list,
) -> None:
    """Force-include ranking sources that recency caps would otherwise drop."""
    from src.auth_helpers import owner_filter

    missing_notes = tuple(
        p for p in HUD_PINNED_NOTE_PREFIXES if not _snapshot_has_prefix(notes, p)
    )
    if missing_notes:
        # Include archived rows: HUMAN GATE checklists can leave recency
        # and still need to appear so the operator can tick them.
        nq = db.query(Note)
        if user:
            nq = owner_filter(nq, Note, user)
        nq = nq.filter(_id_prefix_filter(Note.id, missing_notes))
        found = nq.order_by(Note.archived.asc(), Note.updated_at.desc()).limit(24).all()
        for prefix in missing_notes:
            row = _pick_row_for_prefix(found, prefix)
            if row and not _snapshot_has_prefix(notes, prefix):
                notes.insert(0, _note_row_to_cmd(row))

    missing_docs = tuple(
        p for p in HUD_PINNED_DOC_PREFIXES if not _snapshot_has_prefix(documents, p)
    )
    if missing_docs:
        dq = (
            db.query(Document)
            .outerjoin(DbSession, Document.session_id == DbSession.id)
            .filter(Document.is_active == True)  # noqa: E712
            .filter((Document.archived == False) | (Document.archived.is_(None)))  # noqa: E712
            .filter(_id_prefix_filter(Document.id, missing_docs))
        )
        dq = _owner_session_filter(dq, user)
        found_docs = dq.order_by(Document.updated_at.desc()).limit(16).all()
        for prefix in missing_docs:
            row = _pick_row_for_prefix(found_docs, prefix)
            if row and not _snapshot_has_prefix(documents, prefix):
                documents.insert(0, _doc_row_to_cmd(row))


def _doc_row_to_cmd(doc: Document) -> Dict[str, Any]:
    title = doc.title or ""
    if is_grant_catalog_title(title):
        cap = GRANT_CATALOG_BODY_CHARS
    elif title.lower().startswith("ceo brief"):
        cap = 16000
    else:
        cap = 4000
    return {
        "id": doc.id,
        "title": doc.title,
        "content": (doc.current_content or "")[:cap],
        "language": doc.language,
        "archived": bool(doc.archived),
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


def _pin_today_ceo_brief(db, user: Optional[str], documents: list) -> None:
    """Recency-40 drops today's Library brief; without it Money Move goes STALE."""
    from services.documents.ceo_brief_store import load_ceo_brief_snapshot

    snap = load_ceo_brief_snapshot(db, user)
    did = str(snap.get("id") or "").strip()
    if not did or _snapshot_has_prefix(documents, did):
        return
    row = db.query(Document).filter(Document.id == did).first()
    if row:
        documents.insert(0, _doc_row_to_cmd(row))


def _ensure_fruit_ledger_snapshot(
    db,
    user: Optional[str],
    notes: list,
    documents: list,
) -> None:
    """Pin ranking sources (and fruit/grant title fallbacks) into the HUD snapshot.

    Gate-clear writes, charter ranking, and Mycelia parse miss these rows
    when they fall outside the recency caps (80 notes / 40 docs).
    """
    from src.auth_helpers import owner_filter
    from services.home.mycelia_feed import FRUIT_LEDGER_NOTE_ID

    _pin_hud_ids(db, user, notes, documents)
    _pin_today_ceo_brief(db, user, documents)

    stub = FRUIT_LEDGER_NOTE_ID[:8]
    if not any(_id8(n.get("id")) == stub for n in notes):
        nq = db.query(Note).filter(Note.archived == False)  # noqa: E712
        if user:
            nq = owner_filter(nq, Note, user)
        nq = nq.filter(or_(
            Note.id == FRUIT_LEDGER_NOTE_ID,
            Note.id.like(f"{FRUIT_LEDGER_NOTE_ID}%"),
            and_(Note.title.ilike("%fruit%"), Note.title.ilike("%ledger%")),
        ))
        row = None
        for cand in nq.order_by(Note.updated_at.desc()).limit(8).all():
            if _id8(cand.id) == stub:
                row = cand
                break
            if row is None:
                row = cand
        if row:
            notes.insert(0, _note_row_to_cmd(row))

    if not any(_is_fruit_ledger_title(d.get("title")) for d in documents):
        dq = (
            db.query(Document)
            .outerjoin(DbSession, Document.session_id == DbSession.id)
            .filter(Document.is_active == True)  # noqa: E712
            .filter((Document.archived == False) | (Document.archived.is_(None)))  # noqa: E712
            .filter(Document.title.ilike("%fruit%"))
            .filter(Document.title.ilike("%ledger%"))
        )
        dq = _owner_session_filter(dq, user)
        doc = dq.order_by(Document.updated_at.desc()).first()
        if doc:
            documents.insert(0, _doc_row_to_cmd(doc))

    if not any(is_grant_catalog_title(d.get("title") or "") for d in documents):
        gq = (
            db.query(Document)
            .outerjoin(DbSession, Document.session_id == DbSession.id)
            .filter(Document.is_active == True)  # noqa: E712
            .filter((Document.archived == False) | (Document.archived.is_(None)))  # noqa: E712
            .filter(or_(
                Document.title.ilike("%grant scout%"),
                Document.title.ilike("%grant catalog%"),
            ))
        )
        gq = _owner_session_filter(gq, user)
        gdoc = gq.order_by(Document.updated_at.desc()).first()
        if gdoc and "grant grafter" not in (gdoc.title or "").lower():
            documents.insert(0, _doc_row_to_cmd(gdoc))


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
        include_inbox: bool = Query(
            True, description="Fetch live IMAP inbox for COMMS — false on the hot poll path"
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
                await asyncio.wait_for(
                    sync_caldav(calendar_owner_key(user)),
                    timeout=_VAULT_CALDAV_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                logger.warning("CalDAV sync timed out during vault refresh")
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
                _doc_row_to_cmd(doc)
                for doc in doc_q.order_by(Document.updated_at.desc()).limit(40).all()
            ]
            _ensure_fruit_ledger_snapshot(db, user, notes, documents)

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
            if include_inbox:
                try:
                    inbox_emails, inbox_account_id = await asyncio.wait_for(
                        asyncio.to_thread(fetch_comms_inbox_emails, user or ""),
                        timeout=_VAULT_INBOX_TIMEOUT_SEC,
                    )
                except asyncio.TimeoutError:
                    logger.warning("COMMS inbox preview timed out during vault refresh")
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
            if not include_inbox:
                # Same contract as include_globe=0: omit so the HUD keeps the
                # last live snapshot instead of swapping in an empty inbox.
                payload.pop("comms_preview", None)
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
    async def ceo_brief_run(request: Request, force: bool = Query(False)) -> Dict[str, Any]:
        """Compile today's CEO Brief when missing, stale, or not the full-picture harvest.

        Pass ``force=true`` to re-harvest even when today's full-picture brief
        already exists (e.g. fruit source ranking changed). Does not start
        Open Notebook / Listen. Returns the document body for inline MEM
        display. The Library doc is storage only.
        """
        from src.builtin_actions import action_ceo_brief
        from services.documents.ceo_brief_script import is_full_picture_brief
        user = effective_user(request)
        db = SessionLocal()
        try:
            existing = _ceo_brief_payload(db, user, compiled=False)
            if (
                not force
                and existing.get("status") == "ready"
                and is_full_picture_brief(existing.get("content") or "")
            ):
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
