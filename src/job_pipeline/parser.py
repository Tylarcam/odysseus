"""Normalize raw job input into canonical job_record fields."""

from __future__ import annotations

import re
from typing import Any, Optional


def normalize_field(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def compute_dedup_key(
    company: Optional[str],
    role: Optional[str],
    apply_url: Optional[str],
) -> str:
    company_n = normalize_field(company) or "unknown"
    role_n = normalize_field(role) or "role"
    url_n = (apply_url or "").strip().lower().rstrip("/")
    return f"{company_n}|{role_n}|{url_n}"


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_handshake_id(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"handshake\.com/(?:emp|jobs)/(?:[^/\s]+/)?(\d{5,})", text, re.I)
    if match:
        return match.group(1)
    match = re.search(r"Handshake\s+(\d{5,})", text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_apply_url(text: str) -> Optional[str]:
    if not text:
        return None
    for match in re.finditer(r"https?://[^\s<>\"']+", text):
        url = match.group(0).rstrip(".,)")
        if any(h in url.lower() for h in ("handshake.com", "apply", "jobs", "careers", "greenhouse", "lever")):
            return url
    return None


def parse_manual_ingest(payload: dict[str, Any]) -> dict[str, Any]:
    company = _coerce_str(payload.get("company"))
    role = _coerce_str(payload.get("role"))
    jd_text = _coerce_str(payload.get("jd_text"))
    apply_url = _coerce_str(payload.get("apply_url"))
    handshake_job_id = _coerce_str(payload.get("handshake_job_id"))
    if not handshake_job_id:
        handshake_job_id = _extract_handshake_id(jd_text or "") or _extract_handshake_id(apply_url or "")
    if not apply_url and jd_text:
        apply_url = _extract_apply_url(jd_text)
    confidence = payload.get("confidence")
    return {
        "company": company,
        "role": role,
        "location": _coerce_str(payload.get("location")),
        "compensation": _coerce_str(payload.get("compensation")),
        "source": _coerce_str(payload.get("source")) or "manual",
        "apply_url": apply_url,
        "handshake_job_id": handshake_job_id,
        "jd_text": jd_text,
        "confidence": str(confidence) if confidence is not None else None,
    }


def parse_email_job(payload: dict[str, Any]) -> dict[str, Any]:
    job = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    body = _coerce_str(payload.get("body")) or ""
    subject = _coerce_str(payload.get("subject")) or ""
    jd_snippet = _coerce_str(job.get("jd_snippet")) or body[:8000]
    company = _coerce_str(job.get("company"))
    role = _coerce_str(job.get("role"))
    if not company and subject:
        parts = re.split(r"\s*[—–-]\s*", subject, maxsplit=1)
        if len(parts) == 2:
            company, role = parts[0].strip(), parts[1].strip()
    apply_url = _coerce_str(job.get("apply_url")) or _extract_apply_url(body)
    handshake_job_id = _extract_handshake_id(body) or _extract_handshake_id(apply_url or "")
    confidence = job.get("confidence")
    return {
        "company": company,
        "role": role,
        "location": _coerce_str(job.get("location")),
        "compensation": _coerce_str(job.get("compensation")),
        "source": "email",
        "apply_url": apply_url,
        "handshake_job_id": handshake_job_id,
        "jd_text": jd_snippet,
        "confidence": str(confidence) if confidence is not None else None,
    }


def parse_raw(raw_input: dict[str, Any]) -> dict[str, Any]:
    source = (raw_input.get("source") or "manual").strip().lower()
    if source == "email" or raw_input.get("job") or raw_input.get("is_job_alert"):
        return parse_email_job(raw_input)
    return parse_manual_ingest(raw_input)
