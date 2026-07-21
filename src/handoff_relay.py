"""Automatic handoff relay — dispatch agent work and track outcomes."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from core.database import SessionLocal, Note, Document, Session as DbSession
from src.constants import DATA_DIR
from src.handoff_packet import (
    HANDOFF_TITLE_PREFIX,
    VALID_TARGETS,
    handoff_subject_from_doc_title,
    normalize_target,
    parse_handoff_target_from_title,
    pickup_hint,
)

logger = logging.getLogger(__name__)

_session_manager = None
_task_scheduler = None

RELAY_STATUSES = frozenset({"queued", "running", "complete", "failed"})
EXTERNAL_RELAY_TARGETS = frozenset({"cursor", "claude", "hermes"})


def is_external_relay_target(target: str) -> bool:
    return normalize_target(target) in EXTERNAL_RELAY_TARGETS


def should_run_odysseus_relay(target: str) -> bool:
    return normalize_target(target) == "odysseus"


def _relay_timeout_hours() -> int:
    raw = os.environ.get("HANDOFF_RELAY_TIMEOUT_HOURS", "4").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 4


def set_session_manager(sm):
    global _session_manager
    _session_manager = sm


def set_task_scheduler(scheduler):
    global _task_scheduler
    _task_scheduler = scheduler


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _inbox_dir(target: str) -> Path:
    path = Path(DATA_DIR) / "handoff-inbox" / normalize_target(target)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    text = content or ""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    block = text[4:end]
    body = text[end + 5 :]
    meta: dict[str, str] = {}
    for line in block.split("\n"):
        idx = line.find(":")
        if idx == -1:
            continue
        meta[line[:idx].strip()] = line[idx + 1 :].strip()
    return meta, body


def _replace_frontmatter_field(content: str, key: str, value: str) -> str:
    meta, body = _parse_frontmatter(content)
    meta[key] = value
    lines = ["---"]
    for k, v in meta.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body.lstrip("\n")


def build_relay_agent_prompt(doc_content: str, target: str) -> str:
    target = normalize_target(target)
    return (
        "You are executing an Odysseus handoff relay. The user queued this from Notes — "
        "do NOT ask them to paste an ID or wait for manual pickup.\n\n"
        "Read the Goal, Context, Notes, Done so far, and Next steps in the packet below. "
        "Decompose into concrete steps, execute them with tools, and ship working changes.\n\n"
        "When finished, end your reply with:\n"
        "## Outcome\n"
        "- **Done:** (bullets of what you completed)\n"
        "- **Remaining:** (bullets, or \"none\")\n\n"
        f"Target agent: {target}\n\n"
        "--- HANDOFF PACKET ---\n\n"
        f"{doc_content.strip()}\n"
    )


def _extract_outcome(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"## Outcome\s*(.*)", text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()[:4000]
    return text.strip()[:4000]


def write_external_inbox(doc_id: str, target: str, doc_title: str, doc_content: str, note_id: str) -> str:
    """Drop a markdown inbox file external CLIs can watch (no ID paste needed)."""
    target = normalize_target(target)
    path = _inbox_dir(target) / f"{doc_id}.md"
    prompt = build_relay_agent_prompt(doc_content, target)
    path.write_text(
        "\n".join(
            [
                f"# {doc_title}",
                "",
                f"- note_id: `{note_id}`",
                f"- doc_id: `{doc_id}`",
                f"- target: `{target}`",
                f"- queued_at: `{_utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}`",
                "",
                prompt,
            ]
        ),
        encoding="utf-8",
    )
    return str(path)


def _resolve_handoff_target(doc: Document, explicit: Optional[str] = None) -> str:
    if explicit:
        return normalize_target(explicit)
    from_title = parse_handoff_target_from_title(doc.title or "")
    if from_title:
        return from_title
    meta, _ = _parse_frontmatter(doc.current_content or "")
    return normalize_target(meta.get("target") or "")


def queue_handoff_relay_for_document(
    doc_id: str,
    *,
    owner: Optional[str] = None,
    target: Optional[str] = None,
    note_id: Optional[str] = None,
    relay: bool = True,
) -> dict[str, Any]:
    """Ensure a handoff document has a note row + relay queue for the watcher."""
    if not relay:
        return {"ok": False, "reason": "relay_disabled"}

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return {"ok": False, "reason": "document_not_found"}

        resolved_target = _resolve_handoff_target(doc, target)
        if resolved_target not in VALID_TARGETS:
            return {"ok": False, "reason": "not_a_handoff_document", "target": resolved_target}

        doc_owner = owner or doc.owner
        now = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        note = db.query(Note).filter(Note.handoff_doc_id == doc_id).first()
        if note is None:
            note = Note(
                id=note_id or str(uuid.uuid4()),
                owner=doc_owner,
                title=handoff_subject_from_doc_title(doc.title or "")[:200] or "Handoff",
                content="",
                source="handoff_relay",
            )
            db.add(note)

        if owner and note.owner and note.owner != owner:
            return {"ok": False, "reason": "forbidden"}
        if doc_owner and not note.owner:
            note.owner = doc_owner

        note.handoff_doc_id = doc_id
        note.handoff_target = resolved_target
        note.handoff_at = now
        note.handoff_relay_status = "queued"
        note.handoff_outcome = None
        note.handoff_relay_started_at = None
        note.handoff_relay_completed_at = None
        note.handoff_relay_session_id = None
        db.commit()

        inbox_path = write_external_inbox(
            doc_id,
            resolved_target,
            doc.title or "",
            doc.current_content or "",
            note.id,
        )
        if should_run_odysseus_relay(resolved_target):
            schedule_relay(note.id, doc_id, note.owner or doc_owner)

        return {
            "ok": True,
            "note_id": note.id,
            "doc_id": doc_id,
            "target": resolved_target,
            "status": "queued",
            "inbox_path": inbox_path,
            "relay_executor": "odysseus" if should_run_odysseus_relay(resolved_target) else "external",
        }
    finally:
        db.close()


def _repair_orphan_handoff_documents(owner: Optional[str], limit: int = 25) -> int:
    """Queue relay for handoff docs missing a pending/running note (legacy creates)."""
    db = SessionLocal()
    repaired = 0
    try:
        cutoff = _utcnow() - timedelta(days=7)
        q = db.query(Document).filter(
            Document.title.like(f"{HANDOFF_TITLE_PREFIX}%"),
            Document.created_at >= cutoff,
        )
        if owner:
            q = q.filter(Document.owner == owner)
        docs = q.order_by(Document.created_at.desc()).limit(limit).all()
        for doc in docs:
            note = db.query(Note).filter(Note.handoff_doc_id == doc.id).first()
            status = (note.handoff_relay_status or "").strip().lower() if note else ""
            if status in ("queued", "running", "complete", "failed"):
                continue
            target = _resolve_handoff_target(doc)
            if target not in EXTERNAL_RELAY_TARGETS and not should_run_odysseus_relay(target):
                continue
            queue_handoff_relay_for_document(
                doc.id,
                owner=owner or doc.owner,
                target=target,
                relay=True,
            )
            repaired += 1
        return repaired
    finally:
        db.close()


def list_pending_external(owner: Optional[str], target: Optional[str] = None) -> list[dict[str, Any]]:
    _repair_orphan_handoff_documents(owner)
    db = SessionLocal()
    try:
        q = db.query(Note).filter(
            Note.handoff_doc_id.isnot(None),
            Note.handoff_relay_status.in_(("queued", "running")),
        )
        if owner:
            q = q.filter(Note.owner == owner)
        rows = q.order_by(Note.handoff_at.desc()).limit(50).all()
        out: list[dict[str, Any]] = []
        for note in rows:
            t = normalize_target(note.handoff_target or "")
            if target and t != normalize_target(target):
                continue
            if t not in EXTERNAL_RELAY_TARGETS:
                continue
            doc = db.query(Document).filter(Document.id == note.handoff_doc_id).first()
            if not doc:
                continue
            inbox_name = f"{doc.id}.md"
            out.append(
                {
                    "note_id": note.id,
                    "doc_id": doc.id,
                    "target": t,
                    "title": doc.title,
                    "status": note.handoff_relay_status,
                    "inbox_path": str(_inbox_dir(t) / inbox_name),
                    "host_inbox_rel": f"handoff-inbox/{t}/{inbox_name}",
                    "pickup_hint": pickup_hint(t, doc.id),
                    "content": doc.current_content or "",
                }
            )
        return out
    finally:
        db.close()


def _resolve_endpoint(owner: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if _task_scheduler:
        db = SessionLocal()
        try:
            url, model = _task_scheduler._resolve_defaults(db, owner)
            if url and model:
                return url, model
        finally:
            db.close()
    db = SessionLocal()
    try:
        recent = (
            db.query(DbSession)
            .filter(DbSession.endpoint_url.isnot(None), DbSession.model.isnot(None))
            .order_by(DbSession.created_at.desc())
            .first()
        )
        if recent:
            return recent.endpoint_url, recent.model
    finally:
        db.close()
    return None, None


def _outcome_looks_failed(text: str) -> bool:
    """Heuristic: CLI stderr / DB errors masquerading as agent output."""
    if not (text or "").strip():
        return True
    low = text.lower()
    if "unique constraint" in low or "integrityerror" in low:
        return True
    if "traceback (most recent call last)" in low:
        return True
    if ".ps1:" in low and " char:" in low:
        return True
    if "node.exe" in low and ":" in low:
        return True
    return False


def _ensure_relay_session(
    db,
    *,
    note: Note,
    endpoint_url: str,
    model: str,
    title: str,
) -> str:
    """Return a relay session id, creating the DB row once (no duplicate insert)."""
    sid = note.handoff_relay_session_id or note.agent_session_id
    if sid:
        existing = db.query(DbSession).filter(DbSession.id == sid).first()
        if existing:
            note.handoff_relay_session_id = sid
            note.agent_session_id = sid
            return sid

    sid = str(uuid.uuid4())
    name = title[:80]

    created_via_manager = False
    if _session_manager:
        try:
            _session_manager.ensure_task_session(
                sid, name, endpoint_url, model, owner=note.owner, task=None
            )
            created_via_manager = True
        except Exception:
            logger.warning("ensure_task_session failed for handoff relay", exc_info=True)

    # ensure_task_session commits in its own SessionLocal — refresh visibility here.
    db.expire_all()
    existing = db.query(DbSession).filter(DbSession.id == sid).first()
    if not existing and not created_via_manager:
        try:
            db.add(
                DbSession(
                    id=sid,
                    name=name,
                    endpoint_url=endpoint_url,
                    model=model,
                    owner=note.owner,
                    folder="Handoffs",
                    mode="agent",
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
            )
            db.flush()
            existing = db.query(DbSession).filter(DbSession.id == sid).first()
        except IntegrityError:
            db.rollback()
            existing = db.query(DbSession).filter(DbSession.id == sid).first()
            if not existing:
                raise

    if existing:
        if not existing.folder:
            existing.folder = "Handoffs"
        if not getattr(existing, "mode", None):
            existing.mode = "agent"

    note.handoff_relay_session_id = sid
    note.agent_session_id = sid
    return sid


async def _run_odysseus_relay(note_id: str, doc_id: str, owner: Optional[str]) -> None:
    db = SessionLocal()
    try:
        note = db.query(Note).filter(Note.id == note_id).first()
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not note or not doc:
            return

        endpoint_url, model = _resolve_endpoint(owner or note.owner)
        if not endpoint_url or not model:
            await _finalize_relay(
                note_id,
                doc_id,
                status="failed",
                outcome="No chat model configured for relay.",
                owner=owner or note.owner,
            )
            return

        target = normalize_target(note.handoff_target or "odysseus")
        prompt = build_relay_agent_prompt(doc.current_content or "", target)
        title = f"Relay: {(note.title or doc.title or 'handoff')[:48]}"
        session_id = _ensure_relay_session(
            db, note=note, endpoint_url=endpoint_url, model=model, title=title
        )
        note.handoff_relay_status = "running"
        note.handoff_relay_started_at = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        db.commit()

        write_external_inbox(doc_id, target, doc.title or "", doc.current_content or "", note_id)

        relay_task = SimpleNamespace(
            name=title,
            prompt=prompt,
            owner=owner or note.owner,
            max_steps=30,
        )

        if not _task_scheduler:
            await _finalize_relay(
                note_id,
                doc_id,
                status="failed",
                outcome="Task scheduler unavailable.",
                owner=owner or note.owner,
            )
            return

        result = await _task_scheduler._run_agent_loop(
            endpoint_url,
            model,
            relay_task,
            session_id,
            system_prompt=(
                "You are Odysseus executing a queued handoff relay. Use tools to complete "
                "the work described in the user message. Finish with a ## Outcome section."
            ),
            override_user_message=prompt,
        )
        outcome = _extract_outcome(result or "")
        raw = outcome or (result or "Relay finished.")[:4000]
        relay_status = "failed" if _outcome_looks_failed(raw) else "complete"
        await _finalize_relay(
            note_id,
            doc_id,
            status=relay_status,
            outcome=raw,
            owner=owner or note.owner,
        )
    except Exception as exc:
        logger.error("Handoff relay failed for note %s: %s", note_id, exc, exc_info=True)
        await _finalize_relay(
            note_id,
            doc_id,
            status="failed",
            outcome=str(exc)[:500],
            owner=owner,
        )
    finally:
        db.close()


async def _finalize_relay(
    note_id: str,
    doc_id: str,
    *,
    status: str,
    outcome: str,
    owner: Optional[str],
) -> None:
    status = status if status in RELAY_STATUSES else "failed"
    db = SessionLocal()
    try:
        note = db.query(Note).filter(Note.id == note_id).first()
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if note:
            note.handoff_relay_status = status
            note.handoff_outcome = (outcome or "")[:4000]
            if status == "complete":
                note.handoff_relay_completed_at = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        if doc:
            content = doc.current_content or ""
            content = _replace_frontmatter_field(content, "status", status)
            stamp = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            content = _replace_frontmatter_field(content, "relay_completed_at", stamp)
            block = f"\n\n## Outcome\n\n{(outcome or '').strip()}\n"
            if "## Outcome" not in content:
                content = content.rstrip() + block
            doc.current_content = content
            flag_modified(doc, "current_content")
        db.commit()

        target = normalize_target(getattr(note, "handoff_target", "") or "")
        label = f"Handoff relay {status} → {target}"
        body = (outcome or "")[:500]
        if _task_scheduler:
            _task_scheduler.add_notification(
                task_name=label,
                status="success" if status == "complete" else "error",
                task_id=f"handoff-relay-{doc_id}",
                owner=owner,
                body=body,
            )

        if status == "complete" and doc:
            _maybe_trigger_job_validation(doc_id, doc, owner)
    finally:
        db.close()


def _maybe_trigger_job_validation(doc_id: str, doc, owner: Optional[str]) -> None:
    """When a job-application handoff completes, validate tailored artifacts."""
    try:
        from src.handoff_materialize import is_handoff_document
        from src.job_pipeline.store import find_by_handoff_doc_id
        from src.job_pipeline.orchestrator import validate_and_route

        content = doc.current_content or ""
        meta, _ = _parse_frontmatter(content)
        project = (meta.get("project") or "").replace("\\", "/").lower()
        title = doc.title or ""
        is_job_project = "job-application-ops" in project
        is_job_handoff = is_handoff_document(title) and " — " in title.replace("–", "—")

        job = find_by_handoff_doc_id(doc_id)
        if not job and not (is_job_project or is_job_handoff):
            return
        if job is None:
            return

        validate_and_route(job.id)
        logger.info("Job validation triggered for handoff doc_id=%s job_id=%s", doc_id, job.id)
    except Exception as exc:
        logger.warning("Job handoff validation hook failed for doc_id=%s: %s", doc_id, exc)


def schedule_relay(note_id: str, doc_id: str, owner: Optional[str]) -> None:
    """Fire-and-forget relay dispatch on the running event loop."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run_odysseus_relay(note_id, doc_id, owner))
    except RuntimeError:
        logger.warning("No event loop — handoff relay queued for scanner")


async def scan_stuck_relays() -> None:
    """Recover queued Odysseus relays; time out stuck external + internal runs."""
    db = SessionLocal()
    try:
        now = _utcnow()
        timeout = timedelta(hours=_relay_timeout_hours())
        notes = (
            db.query(Note)
            .filter(
                Note.handoff_doc_id.isnot(None),
                Note.handoff_relay_status.in_(("queued", "running")),
            )
            .limit(100)
            .all()
        )
        for note in notes:
            target = normalize_target(note.handoff_target or "")
            if note.handoff_relay_status == "queued":
                if is_external_relay_target(target):
                    started_raw = note.handoff_at
                    if started_raw:
                        try:
                            started = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
                            if now - started > timeout:
                                await _finalize_relay(
                                    note.id,
                                    note.handoff_doc_id,
                                    status="failed",
                                    outcome=(
                                        f"External relay timed out after {_relay_timeout_hours()} hours. "
                                        "Start scripts/handoff-relay-watcher.ps1 -RunAgent on your machine."
                                    ),
                                    owner=note.owner,
                                )
                        except ValueError:
                            pass
                    continue
                schedule_relay(note.id, note.handoff_doc_id, note.owner)
                continue
            started_raw = getattr(note, "handoff_relay_started_at", None) or note.handoff_at
            if not started_raw:
                continue
            try:
                started = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if now - started > timeout:
                label = "External" if is_external_relay_target(target) else "Relay"
                await _finalize_relay(
                    note.id,
                    note.handoff_doc_id,
                    status="failed",
                    outcome=f"{label} timed out after {_relay_timeout_hours()} hours.",
                    owner=note.owner,
                )
    finally:
        db.close()


def claim_external_relay(doc_id: str, owner: Optional[str]) -> bool:
    """Mark a queued cursor/claude handoff as running (CLI watcher picked it up)."""
    db = SessionLocal()
    try:
        note = db.query(Note).filter(Note.handoff_doc_id == doc_id).first()
        if not note or note.handoff_relay_status != "queued":
            return False
        if not is_external_relay_target(note.handoff_target or ""):
            return False
        if owner and note.owner != owner:
            return False
        note.handoff_relay_status = "running"
        note.handoff_relay_started_at = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        db.commit()
        return True
    finally:
        db.close()


async def complete_external_relay(
    doc_id: str,
    owner: Optional[str],
    *,
    outcome: str,
    status: str = "complete",
) -> bool:
    if status == "complete" and _outcome_looks_failed(outcome):
        status = "failed"
    db = SessionLocal()
    try:
        note = db.query(Note).filter(Note.handoff_doc_id == doc_id).first()
        if not note:
            return False
        if owner and note.owner != owner:
            return False
        note_id = note.id
        note_owner = note.owner
    finally:
        db.close()
    await _finalize_relay(
        note_id,
        doc_id,
        status=status,
        outcome=outcome,
        owner=owner or note_owner,
    )
    return True


def retry_handoff_relay(note_id: str, owner: Optional[str] = None) -> dict[str, Any]:
    """Re-queue a failed/stuck handoff for another relay attempt."""
    db = SessionLocal()
    try:
        note = db.query(Note).filter(Note.id == note_id).first()
        if not note or not note.handoff_doc_id:
            raise ValueError("not a handoff note")
        if owner is not None and note.owner != owner:
            raise ValueError("forbidden")
        doc = db.query(Document).filter(Document.id == note.handoff_doc_id).first()
        if not doc:
            raise ValueError("handoff document missing")

        target = normalize_target(note.handoff_target or "")
        now = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        note.handoff_relay_status = "queued"
        note.handoff_outcome = None
        note.handoff_relay_started_at = None
        note.handoff_relay_completed_at = None
        note.handoff_relay_session_id = None
        note.handoff_at = now
        db.commit()

        inbox_path = write_external_inbox(
            note.handoff_doc_id,
            target,
            doc.title or "",
            doc.current_content or "",
            note_id,
        )
        if should_run_odysseus_relay(target):
            schedule_relay(note_id, note.handoff_doc_id, note.owner or owner)

        return {
            "ok": True,
            "note_id": note_id,
            "doc_id": note.handoff_doc_id,
            "target": target,
            "status": "queued",
            "inbox_path": inbox_path,
        }
    finally:
        db.close()
