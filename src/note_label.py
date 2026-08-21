"""Normalize Odysseus note labels (tags) to lowercase kebab tokens."""

from __future__ import annotations

from typing import Optional


def normalize_note_label(raw: Optional[str]) -> Optional[str]:
    """Lowercase, strip #, split on commas/whitespace, dedupe, rejoin.

    ``None`` stays ``None`` so omitted update fields are not cleared.
    Empty / whitespace-only input becomes ``""``.
    """
    if raw is None:
        return None
    seen: list[str] = []
    seen_set: set[str] = set()
    for part in str(raw).replace(",", " ").split():
        token = part.strip().lstrip("#").lower()
        if not token or token in seen_set:
            continue
        seen_set.add(token)
        seen.append(token)
    return " ".join(seen)
