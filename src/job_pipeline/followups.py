"""Follow-up task scheduling for job applications (Phase 4)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.database import ScheduledTask, SessionLocal
from src.job_pipeline.store import add_job_event, get_job_record, update_job_record
from src.task_scheduler import compute_next_run

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _create_scheduled_task(
    *,
    name: str,
    prompt: str,
    owner: Optional[str],
    schedule: str,
    scheduled_date: Optional[datetime] = None,
    scheduled_time: str = "09:00",
    task_type: str = "llm",
) -> str:
    task_id = str(uuid.uuid4())
    next_run = None
    if schedule == "once":
        next_run = scheduled_date
    else:
        next_run = compute_next_run(schedule, scheduled_time)

    db = SessionLocal()
    try:
        task = ScheduledTask(
            id=task_id,
            owner=owner,
            name=name[:120],
            prompt=prompt,
            task_type=task_type,
            schedule=schedule,
            scheduled_time=scheduled_time,
            scheduled_date=scheduled_date,
            trigger_type="schedule",
            next_run=next_run,
            status="active",
            output_target="session",
        )
        db.add(task)
        db.commit()
        return task_id
    finally:
        db.close()


def schedule_followup(
    job_id: str,
    *,
    days: int = 7,
    owner: Optional[str] = None,
) -> dict[str, Any]:
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")
    if record.followup_task_id:
        return {"task_id": record.followup_task_id, "already_scheduled": True}

    company = record.company or "Company"
    role = record.role or "Role"
    run_at = _utcnow_naive() + timedelta(days=max(1, days))
    prompt = (
        f"Follow up on {company} {role} application (Odysseus job id: {job_id}). "
        "Check email for replies, Handshake status if applicable, and suggest next steps."
    )
    task_id = _create_scheduled_task(
        name=f"Follow up: {company} — {role}",
        prompt=prompt,
        owner=owner or record.owner,
        schedule="once",
        scheduled_date=run_at,
    )
    update_job_record(job_id, followup_task_id=task_id)
    add_job_event(
        job_id=job_id,
        from_status=record.status,
        to_status=record.status,
        stage="followup",
        message=f"Scheduled {days}-day follow-up",
        detail={"followup_task_id": task_id, "run_at": run_at.isoformat()},
    )
    return {"task_id": task_id, "run_at": run_at.isoformat()}


def schedule_ready_to_apply_reminder(
    job_id: str,
    *,
    days: int = 3,
    owner: Optional[str] = None,
) -> dict[str, Any]:
    """Remind user to apply when ready_to_apply sits idle."""
    record = get_job_record(job_id)
    if not record:
        raise ValueError(f"job record not found: {job_id}")

    company = record.company or "Company"
    role = record.role or "Role"
    run_at = _utcnow_naive() + timedelta(days=max(1, days))
    prompt = (
        f"Reminder: job application package ready for {company} — {role} "
        f"(job id {job_id}). User has not confirmed apply yet. "
        "Summarize the apply package paths and urge them to complete Handshake submit "
        "then mark applied via /api/jobs/{id}/mark-applied."
    )
    task_id = _create_scheduled_task(
        name=f"Apply reminder: {company} — {role}",
        prompt=prompt,
        owner=owner or record.owner,
        schedule="once",
        scheduled_date=run_at,
    )
    add_job_event(
        job_id=job_id,
        from_status=record.status,
        to_status=record.status,
        stage="apply_reminder",
        message=f"Scheduled {days}-day apply reminder",
        detail={"reminder_task_id": task_id, "run_at": run_at.isoformat()},
    )
    return {"task_id": task_id, "run_at": run_at.isoformat()}
