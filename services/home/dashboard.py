"""Recent-projects dashboard aggregation for the Odysseus home view."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

_FRONTMATTER_PROJECT = re.compile(
    r"^---\s*\r?\n(?:.*\r?\n)*?project:\s*(?P<val>.+?)\s*\r?\n(?:.*\r?\n)*?---",
    re.MULTILINE,
)


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def note_project_tags(label: Optional[str]) -> List[str]:
    """Split a note label field into distinct project tags."""
    raw = (label or "").strip()
    if not raw:
        return []
    seen: set[str] = set()
    out: List[str] = []
    for part in raw.split():
        tag = part.strip().lstrip("#")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def project_name_from_value(value: Optional[str]) -> Optional[str]:
    """Normalize a project string (path, slug, or plain name)."""
    text = (value or "").strip()
    if not text:
        return None
    # Session folders and note tags are usually short; handoff frontmatter may be a path.
    if "\\" in text or "/" in text:
        base = os.path.basename(text.rstrip("\\/"))
        return base or text
    return text


def project_from_document_content(content: Optional[str]) -> Optional[str]:
    match = _FRONTMATTER_PROJECT.search(content or "")
    if not match:
        return None
    return project_name_from_value(match.group("val"))


def _item_sort_key(item: Dict[str, Any]) -> Tuple[datetime, str]:
    dt = _parse_dt(item.get("updated_at")) or datetime.min
    return (dt, str(item.get("id") or ""))


def build_recent_projects(
    notes: Iterable[Dict[str, Any]],
    documents: Iterable[Dict[str, Any]],
    *,
    project_limit: int = 5,
    items_per_project: int = 5,
) -> Dict[str, Any]:
    """Return top projects by recent note/doc activity with nested recent items."""
    projects: Dict[str, Dict[str, Any]] = {}

    def _touch(project: str) -> Dict[str, Any]:
        key = project_name_from_value(project) or project
        bucket = projects.get(key)
        if bucket is None:
            bucket = {
                "name": key,
                "last_activity_at": None,
                "items": [],
            }
            projects[key] = bucket
        return bucket

    def _add_item(project: str, item: Dict[str, Any]) -> None:
        bucket = _touch(project)
        bucket["items"].append(item)
        item_dt = _parse_dt(item.get("updated_at"))
        cur_dt = _parse_dt(bucket.get("last_activity_at"))
        if item_dt and (cur_dt is None or item_dt > cur_dt):
            bucket["last_activity_at"] = item_dt.isoformat()

    for note in notes:
        if note.get("archived"):
            continue
        tags = note_project_tags(note.get("label"))
        if not tags:
            continue
        updated = note.get("updated_at")
        title = (note.get("title") or "").strip()
        if not title:
            content = (note.get("content") or "").strip()
            title = content.split("\n", 1)[0][:80] if content else "Untitled note"
        payload = {
            "id": note.get("id"),
            "type": "note",
            "title": title,
            "note_type": note.get("note_type") or "note",
            "updated_at": updated,
        }
        for tag in tags:
            _add_item(tag, dict(payload))

    for doc in documents:
        if doc.get("archived"):
            continue
        project = (
            project_name_from_value(doc.get("session_folder"))
            or project_from_document_content(doc.get("content"))
        )
        if not project:
            continue
        title = (doc.get("title") or "").strip() or "Untitled document"
        _add_item(
            project,
            {
                "id": doc.get("id"),
                "type": "document",
                "title": title,
                "language": doc.get("language"),
                "updated_at": doc.get("updated_at"),
            },
        )

    ranked = sorted(
        projects.values(),
        key=lambda p: _item_sort_key({"updated_at": p.get("last_activity_at"), "id": p.get("name")}),
        reverse=True,
    )[: max(1, project_limit)]

    out_projects: List[Dict[str, Any]] = []
    for bucket in ranked:
        items = sorted(bucket["items"], key=_item_sort_key, reverse=True)
        deduped: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in items:
            key = f"{item.get('type')}:{item.get('id')}"
            if key in seen_ids:
                continue
            seen_ids.add(key)
            deduped.append(item)
        out_projects.append(
            {
                "name": bucket["name"],
                "last_activity_at": bucket.get("last_activity_at"),
                "items": deduped[: max(1, items_per_project)],
            }
        )

    return {
        "projects": out_projects,
        "project_count": len(out_projects),
    }
