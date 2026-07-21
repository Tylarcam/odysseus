"""Morning brief / dashboard hooks for job pipeline attention items."""

from __future__ import annotations

from typing import Any, Optional

from src.job_pipeline.store import job_record_to_dict, list_job_records


def get_jobs_for_brief(*, owner: Optional[str] = None, limit: int = 5) -> dict[str, Any]:
    """Jobs needing human attention for Ras Morning Brief / home dashboard."""
    # Match terminal_status or legacy status so cmd-center sees all attention jobs.
    ready = list_job_records(attention="ready_to_apply", owner=owner, limit=limit)
    review = list_job_records(attention="needs_review", owner=owner, limit=limit)

    def _summarize(records):
        return [job_record_to_dict(r) for r in records]

    top_ready = _summarize(ready)
    top_review = _summarize(review)

    lines = []
    if top_ready:
        lines.append(f"{len(top_ready)} job(s) ready to apply")
        for job in top_ready[:3]:
            lines.append(f"- {job.get('company')} — {job.get('role')} (mark applied after submit)")
    if top_review:
        lines.append(f"{len(top_review)} job(s) need review")

    return {
        "ready_to_apply_count": len(ready),
        "needs_review_count": len(review),
        "ready_to_apply": top_ready,
        "needs_review": top_review,
        "summary_lines": lines,
        "headline": lines[0] if lines else "No job applications need attention",
    }
