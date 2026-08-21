"""Bucket note-backed handoffs for the Agent Bin inbox."""

from __future__ import annotations

from typing import Any

from src.handoff_packet import normalize_target

_EXTERNAL = frozenset({"cursor", "claude"})

# Agent Bin rows — metadata only. Full note content made /api/notes/handoffs
# too heavy to render while Command Center already had the compact handoff.
_BIN_ROW_KEYS = (
    "id",
    "title",
    "archived",
    "handoff_doc_id",
    "handoff_target",
    "handoff_at",
    "handoff_relay_status",
    "handoff_outcome",
    "handoff_relay_session_id",
    "agent_session_id",
    "handoff_relay_started_at",
    "handoff_relay_completed_at",
    "updated_at",
)


def classify_handoff_bucket(note: dict[str, Any]) -> str:
    """Return ``needs_attention``, ``in_progress``, or ``done``."""
    if not note.get("handoff_doc_id"):
        raise ValueError("not a handoff note")
    if note.get("archived"):
        return "done"
    status = (note.get("handoff_relay_status") or "").strip().lower()
    if status == "running":
        return "in_progress"
    if status == "complete":
        return "done"
    return "needs_attention"


def attention_rank(note: dict[str, Any]) -> tuple[int, str]:
    """Lower rank = higher priority within needs_attention."""
    status = (note.get("handoff_relay_status") or "").strip().lower()
    target = normalize_target(note.get("handoff_target") or "")
    if status == "failed":
        rank = 0
    elif status == "complete":
        rank = 1
    elif status == "queued" and target in _EXTERNAL:
        rank = 2
    elif status == "queued":
        rank = 3
    elif not status:
        rank = 4
    else:
        rank = 5
    at = note.get("handoff_at") or note.get("updated_at") or ""
    return (rank, at)


def _sort_key_desc(note: dict[str, Any]) -> str:
    return note.get("handoff_at") or note.get("updated_at") or ""


def bucket_handoff_notes(notes: list[dict[str, Any]]) -> dict[str, Any]:
    needs: list[dict[str, Any]] = []
    progress: list[dict[str, Any]] = []
    done: list[dict[str, Any]] = []

    for note in notes:
        if not note.get("handoff_doc_id"):
            continue
        bucket = classify_handoff_bucket(note)
        if bucket == "in_progress":
            progress.append(note)
        elif bucket == "done":
            done.append(note)
        else:
            needs.append(note)

    needs.sort(key=attention_rank)
    progress.sort(key=_sort_key_desc, reverse=True)
    done.sort(key=_sort_key_desc, reverse=True)

    return compact_handoff_payload(
        {
            "needs_attention": needs,
            "in_progress": progress,
            "done": done,
            "counts": {
                "needs_attention": len(needs),
                "in_progress": len(progress),
                "done": len(done),
                "total": len(needs) + len(progress) + len(done),
            },
        }
    )


def compact_handoff_note(note: dict[str, Any]) -> dict[str, Any]:
    """Drop body/items so Agent Bin can load without stalling the modal."""
    row = {key: note.get(key) for key in _BIN_ROW_KEYS}
    row["archived"] = bool(note.get("archived"))
    return row


def compact_handoff_payload(bucketed: dict[str, Any]) -> dict[str, Any]:
    return {
        "needs_attention": [compact_handoff_note(n) for n in bucketed.get("needs_attention") or []],
        "in_progress": [compact_handoff_note(n) for n in bucketed.get("in_progress") or []],
        "done": [compact_handoff_note(n) for n in bucketed.get("done") or []],
        "counts": bucketed.get("counts") or {
            "needs_attention": 0,
            "in_progress": 0,
            "done": 0,
            "total": 0,
        },
    }
