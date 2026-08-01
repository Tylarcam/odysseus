"""Morning brief / dashboard hooks for job pipeline attention items."""

from __future__ import annotations

from typing import Any, Optional

from src.job_pipeline.store import (
    count_job_funnel_stages,
    count_job_records,
    job_record_to_dict,
    list_job_records,
)


def get_jobs_for_brief(*, owner: Optional[str] = None, limit: int = 5) -> dict[str, Any]:
    """Jobs needing human attention for Ras Morning Brief / home dashboard."""
    # Match terminal_status or legacy status so cmd-center sees all attention jobs.
    # Counts are uncapped; row lists stay capped at ``limit`` for display.
    ready_count = count_job_records(attention="ready_to_apply", owner=owner)
    review_count = count_job_records(attention="needs_review", owner=owner)
    ready = list_job_records(attention="ready_to_apply", owner=owner, limit=limit)
    review = list_job_records(attention="needs_review", owner=owner, limit=limit)
    funnel = count_job_funnel_stages(owner=owner)

    def _summarize(records):
        return [job_record_to_dict(r) for r in records]

    top_ready = _summarize(ready)
    top_review = _summarize(review)

    lines = []
    if ready_count:
        lines.append(f"{ready_count} job(s) ready to apply")
        for job in top_ready[:3]:
            lines.append(f"- {job.get('company')} — {job.get('role')} (mark applied after submit)")
    if review_count:
        lines.append(f"{review_count} job(s) need review")

    return {
        "ready_to_apply_count": ready_count,
        "needs_review_count": review_count,
        "ready_to_apply": top_ready,
        "needs_review": top_review,
        "funnel": funnel,
        "summary_lines": lines,
        "headline": lines[0] if lines else "No job applications need attention",
    }
