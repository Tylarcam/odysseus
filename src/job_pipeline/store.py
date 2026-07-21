"""CRUD for job_records and job_events."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import or_

from core.database import JobEvent, JobRecord, SessionLocal


def _new_id() -> str:
    return str(uuid.uuid4())


def job_record_to_dict(record: JobRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "owner": record.owner,
        "status": record.status,
        "company": record.company,
        "role": record.role,
        "location": record.location,
        "compensation": record.compensation,
        "source": record.source,
        "apply_url": record.apply_url,
        "handshake_job_id": record.handshake_job_id,
        "jd_text": record.jd_text,
        "confidence": record.confidence,
        "dedup_key": record.dedup_key,
        "folder_slug": record.folder_slug,
        "jd_path": record.jd_path,
        "raw_input": record.raw_input,
        "duplicate_of_id": record.duplicate_of_id,
        "error_message": record.error_message,
        "retry_count": record.retry_count or 0,
        "match_score": record.match_score,
        "gate_score": record.gate_score,
        "profile": record.profile,
        "evaluation_path": record.evaluation_path,
        "validation_report_path": record.validation_report_path,
        "handoff_doc_id": record.handoff_doc_id,
        "terminal_status": record.terminal_status,
        "notion_page_id": record.notion_page_id,
        "apply_package_json": record.apply_package_json,
        "followup_task_id": record.followup_task_id,
        "research_session_id": record.research_session_id,
        "applied_at": record.applied_at.isoformat() if record.applied_at else None,
        "ready_to_apply_at": record.ready_to_apply_at.isoformat() if record.ready_to_apply_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def job_event_to_dict(event: JobEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "job_id": event.job_id,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "stage": event.stage,
        "message": event.message,
        "detail": event.detail,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def create_job_record(
    *,
    owner: Optional[str] = None,
    status: str = "email_received",
    source: str = "manual",
    raw_input: Optional[dict[str, Any]] = None,
    **fields: Any,
) -> JobRecord:
    db = SessionLocal()
    try:
        record = JobRecord(
            id=_new_id(),
            owner=owner,
            status=status,
            source=source,
            raw_input=raw_input,
            **{k: v for k, v in fields.items() if k in JobRecord.__table__.columns.keys()},
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    finally:
        db.close()


def get_job_record(job_id: str) -> Optional[JobRecord]:
    db = SessionLocal()
    try:
        return db.query(JobRecord).filter(JobRecord.id == job_id).first()
    finally:
        db.close()


def list_job_records(
    *,
    limit: int = 50,
    status: Optional[str] = None,
    terminal_status: Optional[str] = None,
    attention: Optional[str] = None,
    owner: Optional[str] = None,
) -> list[JobRecord]:
    """List job records. ``attention`` matches ready_to_apply / needs_review via status OR terminal_status."""
    db = SessionLocal()
    try:
        q = db.query(JobRecord).order_by(JobRecord.created_at.desc())
        if attention == "ready_to_apply":
            q = q.filter(
                or_(
                    JobRecord.terminal_status == "ready_to_apply",
                    JobRecord.status == "ready_to_apply",
                )
            )
        elif attention == "needs_review":
            q = q.filter(
                or_(
                    JobRecord.terminal_status == "needs_review",
                    JobRecord.status == "needs_review",
                )
            )
        if status:
            q = q.filter(JobRecord.status == status)
        if terminal_status:
            q = q.filter(JobRecord.terminal_status == terminal_status)
        if owner:
            q = q.filter(JobRecord.owner == owner)
        return q.limit(max(1, min(limit, 200))).all()
    finally:
        db.close()


def find_by_dedup_key(dedup_key: str, *, exclude_id: Optional[str] = None) -> Optional[JobRecord]:
    if not dedup_key:
        return None
    db = SessionLocal()
    try:
        q = db.query(JobRecord).filter(
            JobRecord.dedup_key == dedup_key,
            JobRecord.status.in_(("deduped", "normalized")),
        )
        if exclude_id:
            q = q.filter(JobRecord.id != exclude_id)
        return q.order_by(JobRecord.created_at.desc()).first()
    finally:
        db.close()


def find_jd_overlap(jd_text: str, *, exclude_id: Optional[str] = None) -> Optional[JobRecord]:
    snippet = (jd_text or "").strip().lower()[:500]
    if len(snippet) < 80:
        return None
    db = SessionLocal()
    try:
        q = db.query(JobRecord).filter(
            JobRecord.status.in_(("deduped", "normalized")),
            JobRecord.jd_text.isnot(None),
        )
        if exclude_id:
            q = q.filter(JobRecord.id != exclude_id)
        for record in q.order_by(JobRecord.created_at.desc()).limit(100).all():
            other = (record.jd_text or "").strip().lower()[:500]
            if len(other) < 80:
                continue
            shorter = min(len(snippet), len(other))
            overlap = sum(1 for a, b in zip(snippet[:shorter], other[:shorter]) if a == b)
            if shorter and overlap / shorter >= 0.85:
                return record
        return None
    finally:
        db.close()


def add_job_event(
    *,
    job_id: str,
    from_status: Optional[str],
    to_status: str,
    stage: str,
    message: str = "",
    detail: Optional[dict[str, Any]] = None,
) -> JobEvent:
    db = SessionLocal()
    try:
        event = JobEvent(
            id=_new_id(),
            job_id=job_id,
            from_status=from_status,
            to_status=to_status,
            stage=stage,
            message=message,
            detail=detail,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event
    finally:
        db.close()


def update_job_record(job_id: str, **fields: Any) -> Optional[JobRecord]:
    db = SessionLocal()
    try:
        record = db.query(JobRecord).filter(JobRecord.id == job_id).first()
        if not record:
            return None
        allowed = JobRecord.__table__.columns.keys()
        for key, value in fields.items():
            if key in allowed:
                setattr(record, key, value)
        db.commit()
        db.refresh(record)
        return record
    finally:
        db.close()


def find_by_handoff_doc_id(handoff_doc_id: str) -> Optional[JobRecord]:
    if not handoff_doc_id:
        return None
    db = SessionLocal()
    try:
        return (
            db.query(JobRecord)
            .filter(JobRecord.handoff_doc_id == handoff_doc_id)
            .order_by(JobRecord.created_at.desc())
            .first()
        )
    finally:
        db.close()


def get_job_events(job_id: str) -> list[JobEvent]:
    db = SessionLocal()
    try:
        return (
            db.query(JobEvent)
            .filter(JobEvent.job_id == job_id)
            .order_by(JobEvent.created_at.asc())
            .all()
        )
    finally:
        db.close()
