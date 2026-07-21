"""Ingest job pipeline events from email messages."""

from __future__ import annotations

from typing import Any, Optional

from src.job_pipeline.orchestrator import inbound_job_event
from src.job_pipeline.parser import parse_email_job
from src.job_pipeline.title_parse import heuristic_company_role


def build_email_job_payload(
    *,
    subject: str = "",
    body: str = "",
    message_id: Optional[str] = None,
    uid: Optional[str] = None,
) -> dict[str, Any]:
    body = (body or "").strip()
    subject = (subject or "").strip()
    payload: dict[str, Any] = {
        "source": "email",
        "subject": subject,
        "body": body,
        "job": {
            "is_job_alert": True,
            "jd_snippet": body,
            "confidence": 1.0,
        },
    }
    if message_id:
        payload["message_id"] = message_id
    if uid:
        payload["uid"] = uid

    parsed = parse_email_job(payload)
    company = parsed.get("company")
    role = parsed.get("role")
    if not company or not role:
        guess_company, guess_role = heuristic_company_role(subject, body)
        company = company or guess_company
        role = role or guess_role

    job = payload["job"]
    if company:
        job["company"] = company
    if role:
        job["role"] = role
    for key in ("apply_url", "location", "compensation", "handshake_job_id"):
        if parsed.get(key):
            job[key] = parsed[key]
    return payload


def ingest_email_to_job_pipeline(
    *,
    subject: str = "",
    body: str = "",
    message_id: Optional[str] = None,
    uid: Optional[str] = None,
    owner: Optional[str] = None,
    auto_process: bool = True,
) -> dict[str, Any]:
    if not (body or "").strip() and not (subject or "").strip():
        raise ValueError("Email subject or body required")
    payload = build_email_job_payload(
        subject=subject,
        body=body,
        message_id=message_id,
        uid=uid,
    )
    return inbound_job_event(
        payload,
        owner=owner,
        source="email",
        auto_process=auto_process,
    )
