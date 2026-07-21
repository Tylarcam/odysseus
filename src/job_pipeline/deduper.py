"""Duplicate detection for job records."""

from __future__ import annotations

import csv
import logging
import os
from typing import Any, Optional

from src.handoff_materialize import default_job_app_root
from src.job_pipeline.parser import compute_dedup_key, normalize_field
from src.job_pipeline.store import find_by_dedup_key, find_jd_overlap

logger = logging.getLogger(__name__)


def _scan_history_path() -> Optional[str]:
    root = default_job_app_root()
    path = os.path.join(root, "scan-history.tsv")
    return path if os.path.isfile(path) else None


def _load_scan_history() -> list[dict[str, str]]:
    path = _scan_history_path()
    if not path:
        return []
    rows: list[dict[str, str]] = []
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                rows.append({k: (v or "").strip() for k, v in row.items()})
    except OSError as exc:
        logger.warning("Failed to read scan-history.tsv: %s", exc)
    return rows


def _match_scan_history(
    company: Optional[str],
    role: Optional[str],
    apply_url: Optional[str],
) -> Optional[str]:
    company_n = normalize_field(company)
    role_n = normalize_field(role)
    url_n = (apply_url or "").strip().lower().rstrip("/")
    for row in _load_scan_history():
        row_company = normalize_field(row.get("company") or row.get("Company"))
        row_role = normalize_field(row.get("role") or row.get("Role") or row.get("title"))
        row_url = (row.get("apply_url") or row.get("url") or "").strip().lower().rstrip("/")
        if company_n and role_n and company_n == row_company and role_n == row_role:
            return row.get("id") or row.get("folder") or "scan-history"
        if url_n and row_url and url_n == row_url:
            return row.get("id") or row.get("folder") or "scan-history"
    return None


def check_duplicate(
    *,
    job_id: str,
    company: Optional[str],
    role: Optional[str],
    apply_url: Optional[str],
    jd_text: Optional[str],
) -> dict[str, Any]:
    """Return duplicate info: {is_duplicate, reason, duplicate_of_id}."""
    dedup_key = compute_dedup_key(company, role, apply_url)
    existing = find_by_dedup_key(dedup_key, exclude_id=job_id)
    if existing:
        return {
            "is_duplicate": True,
            "reason": "dedup_key",
            "duplicate_of_id": existing.id,
            "dedup_key": dedup_key,
        }

    overlap = find_jd_overlap(jd_text or "", exclude_id=job_id)
    if overlap:
        return {
            "is_duplicate": True,
            "reason": "jd_overlap",
            "duplicate_of_id": overlap.id,
            "dedup_key": dedup_key,
        }

    history_hit = _match_scan_history(company, role, apply_url)
    if history_hit:
        return {
            "is_duplicate": True,
            "reason": "scan_history",
            "duplicate_of_id": history_hit,
            "dedup_key": dedup_key,
        }

    return {
        "is_duplicate": False,
        "reason": None,
        "duplicate_of_id": None,
        "dedup_key": dedup_key,
    }
