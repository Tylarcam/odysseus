"""Route validated jobs to terminal outcomes."""

from __future__ import annotations

from typing import Any

MAX_VALIDATION_RETRIES = 2
MATCH_THRESHOLD = 70


def route_job(job_record, validation_report: dict[str, Any]) -> str:
    """Return terminal_status: ready_to_apply | needs_review | error."""
    retry_count = getattr(job_record, "retry_count", None) or 0
    if retry_count >= MAX_VALIDATION_RETRIES and not validation_report.get("passed"):
        return "error"

    if validation_report.get("passed"):
        return "ready_to_apply"

    match_percent = validation_report.get("match_percent")
    failed = [c for c in validation_report.get("checks", []) if not c.get("passed")]
    optional_fail = any(c.get("name") == "fabrication_guard" and not c.get("passed") for c in failed)

    if match_percent is None or match_percent < MATCH_THRESHOLD or failed:
        if retry_count >= MAX_VALIDATION_RETRIES:
            return "error"
        return "needs_review"

    if optional_fail:
        return "needs_review"

    return "needs_review"


def routing_reasons(job_record, validation_report: dict[str, Any], terminal_status: str) -> list[str]:
    """Human-readable reasons for needs_review or error."""
    reasons: list[str] = []
    retry_count = getattr(job_record, "retry_count", None) or 0

    if terminal_status == "error" and retry_count >= MAX_VALIDATION_RETRIES:
        reasons.append(f"validation retries exhausted ({retry_count})")

    match_percent = validation_report.get("match_percent")
    if match_percent is None:
        reasons.append("match percent not parseable from notes.md")
    elif match_percent < MATCH_THRESHOLD:
        reasons.append(f"match {match_percent}% below {MATCH_THRESHOLD}% threshold")

    for check in validation_report.get("checks", []):
        if not check.get("passed"):
            reasons.append(f"{check.get('name')}: {check.get('detail')}")

    if terminal_status == "ready_to_apply" and not reasons:
        return []

    return reasons
