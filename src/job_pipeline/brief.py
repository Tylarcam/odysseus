"""Morning brief / dashboard hooks for job pipeline attention items."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from src.job_pipeline.store import (
    count_job_funnel_stages,
    count_job_records,
    job_record_to_dict,
    list_job_records,
)

WATCH_WINDOW_DAYS = 30
EXPIRING_WITHIN_DAYS = 7
_APPLY_MODES = frozenset({"apply", "submit", "queue"})
_WATCH_MODES = frozenset({"watch", "watch_archive", "archive"})
_EMAIL_DATE_KEYS = ("last_email_at", "received_at", "email_date", "date")


def get_job_mode(*, jobs: Optional[dict[str, Any]] = None) -> str:
    """Agency lane: ``watch`` (default) or ``apply`` (legacy submit queue).

    Resolution: jobs payload ``job_mode`` → ``ODYSSEUS_JOB_MODE`` / ``JOB_MODE``
    → settings.json ``job_mode`` → ``watch``.
    """
    if jobs:
        raw = str(jobs.get("job_mode") or "").strip().lower()
        if raw in _APPLY_MODES:
            return "apply"
        if raw in _WATCH_MODES:
            return "watch"
    env = (os.environ.get("ODYSSEUS_JOB_MODE") or os.environ.get("JOB_MODE") or "").strip().lower()
    if env in _APPLY_MODES:
        return "apply"
    if env in _WATCH_MODES:
        return "watch"
    try:
        from src.settings import get_setting

        val = str(get_setting("job_mode", "watch") or "watch").strip().lower()
        if val in _APPLY_MODES:
            return "apply"
        if val in _WATCH_MODES:
            return "watch"
    except Exception:
        pass
    return "watch"


def get_job_watch_days() -> int:
    env = (os.environ.get("ODYSSEUS_JOB_WATCH_DAYS") or "").strip()
    if env.isdigit():
        return max(1, int(env))
    try:
        from src.settings import get_setting

        return max(1, int(get_setting("job_watch_days", WATCH_WINDOW_DAYS) or WATCH_WINDOW_DAYS))
    except Exception:
        return WATCH_WINDOW_DAYS


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
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _raw_email_dt(job: dict[str, Any]) -> Optional[datetime]:
    blobs: list[Any] = [job]
    raw = job.get("raw_input")
    if isinstance(raw, dict):
        blobs.append(raw)
        for nest in ("email", "job"):
            inner = raw.get(nest)
            if isinstance(inner, dict):
                blobs.append(inner)
    for blob in blobs:
        if not isinstance(blob, dict):
            continue
        for key in _EMAIL_DATE_KEYS:
            dt = _parse_dt(blob.get(key))
            if dt:
                return dt
    return None


def job_last_touch(job: dict[str, Any]) -> Optional[datetime]:
    """Most recent email or record update used as the 30-day watch clock."""
    candidates = [
        _raw_email_dt(job),
        _parse_dt(job.get("last_email_at")),
        _parse_dt(job.get("updated_at")),
        _parse_dt(job.get("ready_to_apply_at")),
        _parse_dt(job.get("created_at")),
    ]
    present = [dt for dt in candidates if dt is not None]
    return max(present) if present else None


def classify_job_watch(
    job: dict[str, Any],
    *,
    now: Optional[datetime] = None,
    window_days: int = WATCH_WINDOW_DAYS,
) -> str:
    """Return ``watched``, ``expiring``, or ``archive_candidate``."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    window_days = max(1, int(window_days))
    touch = job_last_touch(job)
    if touch is None:
        return "watched"
    age_days = (now - touch).total_seconds() / 86400.0
    if age_days > window_days:
        return "archive_candidate"
    remaining = window_days - age_days
    if remaining <= EXPIRING_WITHIN_DAYS:
        return "expiring"
    return "watched"


def annotate_watch(
    job: dict[str, Any],
    *,
    now: Optional[datetime] = None,
    window_days: int = WATCH_WINDOW_DAYS,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    out = dict(job)
    state = classify_job_watch(out, now=now, window_days=window_days)
    out["watch_state"] = state
    touch = job_last_touch(out)
    if touch is not None:
        age = (now - touch).total_seconds() / 86400.0
        out["watch_age_days"] = round(age, 1)
        out["watch_days_left"] = round(window_days - age, 1)
        out["last_touch_at"] = touch.isoformat()
    return out


def partition_jobs_for_watch(
    jobs: list[dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    window_days: int = WATCH_WINDOW_DAYS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split attention jobs into watched / expiring / archive-candidate lists."""
    watched: list[dict[str, Any]] = []
    expiring: list[dict[str, Any]] = []
    archive: list[dict[str, Any]] = []
    for job in jobs:
        tagged = annotate_watch(job, now=now, window_days=window_days)
        state = tagged.get("watch_state")
        if state == "archive_candidate":
            archive.append(tagged)
        elif state == "expiring":
            expiring.append(tagged)
        else:
            watched.append(tagged)
    return watched, expiring, archive


def get_jobs_for_brief(*, owner: Optional[str] = None, limit: int = 5) -> dict[str, Any]:
    """Jobs needing human attention for Ras Morning Brief / home dashboard."""
    # Match terminal_status or legacy status so cmd-center sees all attention jobs.
    # Counts are uncapped; row lists stay capped at ``limit`` for display.
    mode = get_job_mode()
    window_days = get_job_watch_days()
    funnel = count_job_funnel_stages(owner=owner)
    display_limit = max(1, int(limit))

    ready_records = list_job_records(attention="ready_to_apply", owner=owner, limit=200)
    review_records = list_job_records(attention="needs_review", owner=owner, limit=200)
    ready_jobs = [job_record_to_dict(r) for r in ready_records]
    review_jobs = [job_record_to_dict(r) for r in review_records]

    if mode != "watch":
        ready_count = count_job_records(attention="ready_to_apply", owner=owner)
        review_count = count_job_records(attention="needs_review", owner=owner)
        top_ready = ready_jobs[:display_limit]
        top_review = review_jobs[:display_limit]
        lines = []
        if ready_count:
            lines.append(f"{ready_count} job(s) ready to apply")
            for job in top_ready[:3]:
                lines.append(f"- {job.get('company')} — {job.get('role')} (mark applied after submit)")
        if review_count:
            lines.append(f"{review_count} job(s) need review")
        return {
            "job_mode": mode,
            "watch_window_days": window_days,
            "ready_to_apply_count": ready_count,
            "needs_review_count": review_count,
            "ready_to_apply": top_ready,
            "needs_review": top_review,
            "archive_candidates": [],
            "archive_candidate_count": 0,
            "watched_count": 0,
            "expiring_count": 0,
            "funnel": funnel,
            "summary_lines": lines,
            "headline": lines[0] if lines else "No job applications need attention",
        }

    now = datetime.now(timezone.utc)
    r_watch, r_exp, r_arch = partition_jobs_for_watch(ready_jobs, now=now, window_days=window_days)
    v_watch, v_exp, v_arch = partition_jobs_for_watch(review_jobs, now=now, window_days=window_days)
    in_window_ready = r_watch + r_exp
    in_window_review = v_watch + v_exp
    archives = r_arch + v_arch
    watched_count = len(r_watch) + len(v_watch)
    expiring_count = len(r_exp) + len(v_exp)
    archive_count = len(archives)
    ready_count = len(in_window_ready)
    review_count = len(in_window_review)
    top_ready = in_window_ready[:display_limit]
    top_review = in_window_review[:display_limit]

    lines = []
    if watched_count or expiring_count:
        lines.append(f"{watched_count} watched · {expiring_count} expiring")
        for job in (r_watch + r_exp)[:3]:
            company = job.get("company") or "?"
            role = job.get("role") or "?"
            state = job.get("watch_state") or "watched"
            lines.append(f"- {company} — {role} ({state}, not apply-now)")
    if archive_count:
        lines.append(f"{archive_count} archive candidate(s) past {window_days}-day watch")
    if review_count:
        lines.append(f"{review_count} job(s) still in the watch window need a look")

    if watched_count or expiring_count:
        headline = f"{watched_count} watched · {expiring_count} expiring"
    elif archive_count:
        headline = f"{archive_count} archive candidate(s) past {window_days}-day watch"
    else:
        headline = "No jobs on the 30-day watch"

    return {
        "job_mode": mode,
        "watch_window_days": window_days,
        "ready_to_apply_count": ready_count,
        "needs_review_count": review_count,
        "ready_to_apply": top_ready,
        "needs_review": top_review,
        "archive_candidates": archives[:display_limit],
        "archive_candidate_count": archive_count,
        "watched_count": watched_count,
        "expiring_count": expiring_count,
        "funnel": funnel,
        "summary_lines": lines,
        "headline": headline,
    }
