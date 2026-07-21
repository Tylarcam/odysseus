"""Optional company research enrichment for job pipeline (Phase 4)."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

from src.job_pipeline.store import add_job_event, get_job_record, update_job_record

logger = logging.getLogger(__name__)


def is_job_research_enabled() -> bool:
    env = os.environ.get("ENABLE_JOB_RESEARCH", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    try:
        from src.settings import get_setting

        return bool(get_setting("enable_job_research", False))
    except Exception:
        return False


def research_topic_for_job(record) -> str:
    company = (record.company or "Company").strip()
    role = (record.role or "Role").strip()
    return f"{company} {role} culture compensation"


def maybe_start_job_research(
    job_id: str,
    *,
    research_handler: Any = None,
    owner: Optional[str] = None,
    llm_endpoint: str = "",
    llm_model: str = "",
) -> dict[str, Any]:
    """Fire background research when enabled; never blocks pipeline on failure."""
    if not is_job_research_enabled():
        return {"skipped": True, "reason": "disabled"}

    record = get_job_record(job_id)
    if not record:
        return {"skipped": True, "reason": "job_not_found"}
    if record.research_session_id:
        return {"skipped": True, "reason": "already_started", "research_session_id": record.research_session_id}

    if research_handler is None:
        try:
            from src.research_handler import ResearchHandler

            research_handler = ResearchHandler()
        except Exception:
            research_handler = None

    if research_handler is None:
        return {"skipped": True, "reason": "research_handler_unavailable"}

    session_id = f"job-{job_id[:8]}-{uuid.uuid4().hex[:8]}"
    topic = research_topic_for_job(record)
    try:
        research_handler.start_research(
            session_id=session_id,
            query=topic,
            llm_endpoint=llm_endpoint,
            llm_model=llm_model,
            owner=owner or record.owner or "",
            category="job_pipeline",
        )
        update_job_record(job_id, research_session_id=session_id)
        add_job_event(
            job_id=job_id,
            from_status=record.status,
            to_status=record.status,
            stage="research",
            message="Started optional company research",
            detail={"research_session_id": session_id, "topic": topic},
        )
        return {"ok": True, "research_session_id": session_id, "topic": topic}
    except Exception as exc:
        logger.warning("Job research enrichment failed for %s: %s", job_id, exc)
        add_job_event(
            job_id=job_id,
            from_status=record.status,
            to_status=record.status,
            stage="research",
            message="Research enrichment failed (non-blocking)",
            detail={"error": str(exc)},
        )
        return {"ok": False, "error": str(exc)}


def research_link_for_handoff(record) -> str:
    sid = (record.research_session_id or "").strip()
    if not sid:
        return ""
    return f"[Company research](#research-{sid})"
