"""Job pipeline notifications."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _push_notification(
    *,
    task_name: str,
    status: str,
    task_id: str,
    owner: Optional[str],
    body: str,
) -> None:
    try:
        from src.event_bus import get_task_scheduler

        scheduler = get_task_scheduler()
        if scheduler is None:
            logger.info("%s: %s", task_name, body)
            return
        scheduler.add_notification(
            task_name=task_name,
            status=status,
            task_id=task_id,
            owner=owner,
            body=body,
        )
    except Exception as exc:
        logger.debug("Notification hook skipped: %s", exc)


def notify_validation_terminal(
    record,
    terminal_status: str,
    validation_report: dict[str, Any],
    reasons: Optional[list[str]] = None,
) -> None:
    """Notify on Phase 3 terminal states: ready_to_apply, needs_review, error."""
    company = record.company or "Company"
    role = record.role or "Role"
    artifacts = validation_report.get("artifact_paths") or {}
    folder = artifacts.get("folder") or ""
    pdf = artifacts.get("pdf") or ""
    job_id = record.id
    reasons = reasons or []

    if terminal_status == "ready_to_apply":
        body = (
            f"{company} — {role}: validation passed. "
            f"Folder: {folder}. PDF: {pdf or 'n/a'}. "
            f"GET /api/jobs/{job_id}/apply-package when ready to submit."
        )
        _push_notification(
            task_name=f"Job ready: {company}",
            status="success",
            task_id=f"job-validate-{job_id}",
            owner=record.owner,
            body=body,
        )
        return

    if terminal_status == "needs_review":
        detail = "; ".join(reasons[:5]) if reasons else "validation checks incomplete"
        body = (
            f"{company} — {role}: needs review. Folder: {folder}. "
            f"Reasons: {detail}"
        )
        _push_notification(
            task_name=f"Job review: {company}",
            status="success",
            task_id=f"job-validate-{job_id}",
            owner=record.owner,
            body=body,
        )
        return

    detail = "; ".join(reasons[:5]) if reasons else (record.error_message or "validation failed")
    body = f"{company} — {role}: pipeline error. {detail}"
    _push_notification(
        task_name=f"Job error: {company}",
        status="error",
        task_id=f"job-validate-{job_id}",
        owner=record.owner,
        body=body,
    )


def notify_ready_to_apply(record, package: dict[str, Any]) -> None:
    """Log/notify when a job is ready to apply — includes apply-package CTA."""
    job_id = record.id
    company = record.company or "Company"
    role = record.role or "Role"
    apply_path = package.get("apply_package_path") or package.get("folder_path") or ""
    msg = (
        f"Job ready to apply: {company} — {role}. "
        f"Apply package: {apply_path}. "
        f"GET /api/jobs/{job_id}/apply-package for composed /apply workflow. "
        "Mark applied when done: POST /api/jobs/{id}/mark-applied after Handshake submit."
    )
    logger.info(msg)
    _push_notification(
        task_name=f"Ready to apply: {company}",
        status="success",
        task_id=f"job-ready-{job_id}",
        owner=record.owner,
        body=f"{role} — review package and submit on Handshake, then mark applied.",
    )


def notify_applied(record) -> None:
    company = record.company or "Company"
    role = record.role or "Role"
    logger.info("Job marked applied: %s — %s (id=%s)", company, role, record.id)
    _push_notification(
        task_name=f"Applied: {company}",
        status="success",
        task_id=f"job-applied-{record.id}",
        owner=record.owner,
        body=f"{role} — follow-up scheduled in 7 days.",
    )
