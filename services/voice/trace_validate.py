# services/voice/trace_validate.py
"""Golden voice turn trace validation for CI and soak checks."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


def event_names(events: Sequence[Dict[str, Any]]) -> List[str]:
    return [str(e["event"]) for e in events if e.get("event")]


def validate_ordered_steps(
    events: Sequence[Dict[str, Any]],
    steps: Sequence[Sequence[str]],
) -> List[str]:
    """Each step must match one of its alias events, in order (gaps allowed)."""
    names = event_names(events)
    cursor = 0
    errors: List[str] = []

    for i, aliases in enumerate(steps):
        group = tuple(aliases)
        matched = False
        while cursor < len(names):
            if names[cursor] in group:
                matched = True
                cursor += 1
                break
            cursor += 1
        if not matched:
            errors.append(
                f"step {i + 1}: expected one of {list(group)} "
                f"(seen so far: {names[:cursor]})"
            )

    return errors


def validate_forbidden_after(
    events: Sequence[Dict[str, Any]],
    rules: Dict[str, Sequence[str]],
) -> List[str]:
    """After anchor event appears, none of forbidden events may follow."""
    names = event_names(events)
    errors: List[str] = []

    for anchor, forbidden in rules.items():
        if anchor not in names:
            continue
        anchor_idx = names.index(anchor)
        tail = set(names[anchor_idx + 1 :])
        for bad in forbidden:
            if bad in tail:
                errors.append(f"forbidden '{bad}' after '{anchor}'")

    return errors
