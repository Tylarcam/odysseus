"""Locate CEO Brief documents for CMD Center MEM (title or legacy id).

Library-created briefs use UUID ids with titles like ``CEO Brief — YYYY-MM-DD``.
The chron action historically used ``ceo-brief-{date}``. Lookup must accept both
so MEM can open today's brief without a 404.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import or_


def date_label(now: Optional[datetime] = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d")


def canonical_title(now: Optional[datetime] = None) -> str:
    return f"CEO Brief — {date_label(now)}"


def legacy_id(now: Optional[datetime] = None) -> str:
    return f"ceo-brief-{date_label(now)}"


def _iso(val: Any) -> Optional[str]:
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def as_fields(doc: Any) -> Dict[str, Any]:
    if isinstance(doc, dict):
        return {
            "id": doc.get("id"),
            "title": doc.get("title") or "",
            "content": doc.get("content") or doc.get("current_content") or "",
            "updated_at": doc.get("updated_at"),
            "owner": doc.get("owner"),
        }
    return {
        "id": getattr(doc, "id", None),
        "title": getattr(doc, "title", None) or "",
        "content": getattr(doc, "current_content", None) or "",
        "updated_at": getattr(doc, "updated_at", None),
        "owner": getattr(doc, "owner", None),
    }


def is_ceo_brief(fields: Dict[str, Any]) -> bool:
    did = str(fields.get("id") or "")
    title = str(fields.get("title") or "").strip()
    if did.startswith("ceo-brief-"):
        return True
    return title.lower().startswith("ceo brief")


def is_today_brief(fields: Dict[str, Any], today: Optional[str] = None) -> bool:
    label = today or date_label()
    did = str(fields.get("id") or "")
    title = str(fields.get("title") or "")
    if did == f"ceo-brief-{label}":
        return True
    return is_ceo_brief(fields) and label in title


def _sort_key(fields: Dict[str, Any]) -> str:
    return _iso(fields.get("updated_at")) or ""


def empty_snapshot(now: Optional[datetime] = None) -> Dict[str, Any]:
    title = canonical_title(now)
    return {
        "id": None,
        "doc_id": None,
        "title": title,
        "content": "",
        "updated_at": None,
        "is_today": False,
        "stale": True,
        "status": "missing",
    }


def snapshot_from_fields(
    fields: Optional[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    today = date_label(now)
    if not fields or not fields.get("id"):
        return empty_snapshot(now)
    content = str(fields.get("content") or "")
    today_match = is_today_brief(fields, today)
    stale = (not today_match) or (not content.strip())
    if today_match and content.strip():
        status = "ready"
    elif fields.get("id"):
        status = "stale"
    else:
        status = "missing"
    doc_id = fields.get("id")
    return {
        "id": doc_id,
        "doc_id": doc_id,
        "title": fields.get("title") or canonical_title(now),
        "content": content,
        "updated_at": _iso(fields.get("updated_at")),
        "is_today": today_match,
        "stale": stale,
        "status": status,
    }


def select_ceo_brief(
    docs: List[Any],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Pick today's CEO brief if present, else the most recently updated one."""
    today = date_label(now)
    fields_list = [as_fields(d) for d in (docs or [])]
    briefs = [f for f in fields_list if is_ceo_brief(f)]
    today_docs = [f for f in briefs if is_today_brief(f, today)]
    pool = today_docs or briefs
    if not pool:
        return empty_snapshot(now)
    pool.sort(key=_sort_key, reverse=True)
    return snapshot_from_fields(pool[0], now=now)


def query_ceo_brief_rows(db, owner: Optional[str]):
    from core.database import Document
    from src.auth_helpers import owner_filter

    q = db.query(Document).filter(
        Document.is_active == True,  # noqa: E712
        (Document.archived == False) | (Document.archived.is_(None)),  # noqa: E712
        or_(
            Document.id.like("ceo-brief-%"),
            Document.title.ilike("CEO Brief%"),
        ),
    )
    if owner:
        q = owner_filter(q, Document, owner, include_shared=True)
    return q.order_by(Document.updated_at.desc()).all()


def load_ceo_brief_snapshot(db, owner: Optional[str], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    rows = query_ceo_brief_rows(db, owner)
    return select_ceo_brief(rows, now=now)


def find_today_row(db, owner: Optional[str], *, now: Optional[datetime] = None):
    """ORM row for today's brief, or None (do not reuse yesterday's row)."""
    from core.database import Document

    snap = load_ceo_brief_snapshot(db, owner, now=now)
    if not snap.get("is_today") or not snap.get("id"):
        return None
    return db.query(Document).filter(Document.id == snap["id"]).first()
