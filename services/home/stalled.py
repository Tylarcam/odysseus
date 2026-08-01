"""Read-time stalled-item detection for Command Center objects.

Pure functions only — no DB writes. Thresholds live in ``STALLED_SLA``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Conservative defaults (tunable in one place). Spec: job needs_review > 3 days;
# handoff/task thresholds are starting guesses per design D2.
STALLED_SLA: Dict[str, Any] = {
    "job_needs_review_days": 3,
    "handoff_claimed_stuck_hours": 24,
    "task_in_progress_days": 3,
    "note_stale_min_open_items": 3,
    "email_unread_urgent_hours": 48,
    "urgency_boost": 5,
}

_TITLE_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_BRIEFISH_TOKENS = ("brief", "digest", "daily", "plan today", "morning report", "morning")


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
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _ensure_aware(now: datetime) -> datetime:
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _title(obj: Dict[str, Any]) -> str:
    return str(obj.get("title") or obj.get("name") or "").strip()


def _note_open_items(note: Dict[str, Any]) -> int:
    items = note.get("items")
    if not isinstance(items, list):
        return 0
    return sum(
        1
        for it in items
        if isinstance(it, dict) and not it.get("done") and not it.get("checked")
    )


def _extract_title_date(title: str) -> Optional[datetime]:
    m = _TITLE_DATE_RE.search(title or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_briefish(note: Dict[str, Any]) -> bool:
    blob = (_title(note) + " " + str(note.get("label") or "")).lower()
    return any(tok in blob for tok in _BRIEFISH_TOKENS)


def stale_missed_days(note: Dict[str, Any], now: datetime) -> Optional[int]:
    """Days since the brief's title date (or last update) if it's in the past."""
    now = _ensure_aware(now)
    title_dt = _extract_title_date(_title(note))
    if title_dt and title_dt.date() < now.date():
        return max(1, (now.date() - title_dt.date()).days)
    updated = _parse_dt(note.get("updated_at"))
    if updated and updated.date() < now.date():
        return max(1, (now.date() - updated.date()).days)
    return None


def is_stale_brief(note: Dict[str, Any], now: datetime) -> bool:
    """Brief/digest whose title date (or update day) is before today and still open."""
    return compute_stalled("note", note, now) is not None


def _job_attention(obj: Dict[str, Any]) -> str:
    for key in ("attention", "terminal_status", "status"):
        val = str(obj.get(key) or "").strip().lower()
        if val:
            return val
    return ""


def _compute_job(obj: Dict[str, Any], now: datetime) -> Optional[Dict[str, str]]:
    if _job_attention(obj) != "needs_review":
        return None
    since_dt = _parse_dt(obj.get("updated_at")) or _parse_dt(obj.get("created_at"))
    if since_dt is None:
        return None
    threshold_days = float(STALLED_SLA["job_needs_review_days"])
    age_days = (now - since_dt).total_seconds() / 86400.0
    if age_days > threshold_days:
        return {"since": _iso(since_dt), "reason": "needs_review_sla"}
    return None


def _compute_handoff(obj: Dict[str, Any], now: datetime) -> Optional[Dict[str, str]]:
    status = str(obj.get("handoff_relay_status") or "").strip().lower()
    # Claimed = running; terminal complete/failed are never stalled here.
    if status != "running":
        return None
    since_dt = (
        _parse_dt(obj.get("handoff_relay_started_at"))
        or _parse_dt(obj.get("handoff_at"))
        or _parse_dt(obj.get("updated_at"))
    )
    if since_dt is None:
        return None
    threshold_hours = float(STALLED_SLA["handoff_claimed_stuck_hours"])
    age_hours = (now - since_dt).total_seconds() / 3600.0
    if age_hours > threshold_hours:
        return {"since": _iso(since_dt), "reason": "claimed_stuck"}
    return None


def _compute_task(obj: Dict[str, Any], now: datetime) -> Optional[Dict[str, str]]:
    status = str(obj.get("task_status") or "").strip().lower()
    if status != "in_progress":
        return None
    since_dt = _parse_dt(obj.get("task_status_at")) or _parse_dt(obj.get("updated_at"))
    if since_dt is None:
        return None
    threshold_days = float(STALLED_SLA["task_in_progress_days"])
    age_days = (now - since_dt).total_seconds() / 86400.0
    if age_days > threshold_days:
        return {"since": _iso(since_dt), "reason": "in_progress_sla"}
    return None


def _compute_note(obj: Dict[str, Any], now: datetime) -> Optional[Dict[str, str]]:
    if obj.get("archived") or not is_briefish(obj):
        return None
    open_items = _note_open_items(obj)
    title_dt = _extract_title_date(_title(obj))
    if title_dt and title_dt.date() < now.date():
        return {"since": _iso(title_dt), "reason": "stale_brief"}
    updated = _parse_dt(obj.get("updated_at"))
    min_open = int(STALLED_SLA["note_stale_min_open_items"])
    if open_items >= min_open and updated and updated.date() < now.date():
        return {"since": _iso(updated), "reason": "stale_brief"}
    return None


def _email_is_urgent(obj: Dict[str, Any]) -> bool:
    if obj.get("urgent") is True:
        return True
    try:
        return int(obj.get("score") or 0) >= 2
    except (TypeError, ValueError):
        return False


def _email_since_dt(obj: Dict[str, Any]) -> Optional[datetime]:
    """Clock for unread-urgent SLA: triage ``ts`` first, then message date."""
    for key in ("urgent_at", "ts", "flagged_at"):
        raw = obj.get(key)
        if raw is None or raw == "":
            continue
        if isinstance(raw, (int, float)):
            try:
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                continue
        parsed = _parse_dt(raw)
        if parsed is not None:
            return parsed
    epoch = obj.get("date_epoch")
    if epoch is not None:
        try:
            val = float(epoch)
            if val > 0:
                return datetime.fromtimestamp(val, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    return _parse_dt(obj.get("updated_at")) or _parse_dt(obj.get("created_at"))


def _compute_email(obj: Dict[str, Any], now: datetime) -> Optional[Dict[str, str]]:
    """Unread urgent email past the configured hours threshold."""
    if obj.get("is_read"):
        return None
    if not _email_is_urgent(obj):
        return None
    since_dt = _email_since_dt(obj)
    if since_dt is None:
        return None
    threshold_hours = float(STALLED_SLA["email_unread_urgent_hours"])
    age_hours = (now - since_dt).total_seconds() / 3600.0
    if age_hours > threshold_hours:
        return {"since": _iso(since_dt), "reason": "unread_urgent_sla"}
    return None


def compute_stalled(
    kind: str,
    obj: Dict[str, Any],
    now: datetime,
) -> Optional[Dict[str, str]]:
    """Return ``None`` or ``{since, reason}`` for a stalled object.

    Computed at read time only — never persists a stalled flag.
    """
    if not isinstance(obj, dict):
        return None
    now = _ensure_aware(now)
    kind_key = (kind or "").strip().lower()
    if kind_key == "job":
        return _compute_job(obj, now)
    if kind_key == "handoff":
        return _compute_handoff(obj, now)
    if kind_key == "task":
        return _compute_task(obj, now)
    if kind_key == "note":
        return _compute_note(obj, now)
    if kind_key == "email":
        return _compute_email(obj, now)
    return None


def apply_stalled_urgency(
    item: Dict[str, Any],
    stalled: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    """Attach ``stalled`` and boost urgency when present. Mutates and returns ``item``."""
    if not stalled:
        return item
    item["stalled"] = stalled
    boost = int(STALLED_SLA.get("urgency_boost") or 0)
    item["urgency"] = int(item.get("urgency") or 0) + boost
    return item
