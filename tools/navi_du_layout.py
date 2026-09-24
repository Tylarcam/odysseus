r"""navi-du: squarified treemap layout (Python port of the JS squarify used
by the HTML renderer). Pure geometry — no rendering, no filesystem access.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Placed:
    item: dict
    x: float
    y: float
    w: float
    h: float


@dataclass
class _Candidate:
    item: dict
    area: float


def _worst_ratio(row: list[_Candidate], length: float) -> float:
    s = sum(c.area for c in row)
    if s <= 0 or length <= 0:
        return float("inf")
    rmax = max(c.area for c in row)
    rmin = min(c.area for c in row)
    if rmin <= 0:
        return float("inf")
    return max((length * length * rmax) / (s * s), (s * s) / (length * length * rmin))


def _layout_row(row, x, y, w, h, vertical, results: list[Placed]):
    s = sum(c.area for c in row)
    if vertical:
        rw = s / h if h > 0 else 0
        cy = y
        for c in row:
            rh = c.area / rw if rw > 0 else 0
            results.append(Placed(c.item, x, cy, rw, rh))
            cy += rh
        return x + rw, y, w - rw, h
    else:
        rh = s / w if w > 0 else 0
        cx = x
        for c in row:
            rw = c.area / rh if rh > 0 else 0
            results.append(Placed(c.item, cx, y, rw, rh))
            cx += rw
        return x, y + rh, w, h - rh


def _squarify(candidates: list[_Candidate], x, y, w, h) -> list[Placed]:
    results: list[Placed] = []
    lst = list(candidates)
    rx, ry, rw, rh = x, y, w, h
    row: list[_Candidate] = []
    while lst:
        vertical = rw < rh
        length = rh if vertical else rw
        candidate = lst[0]
        new_row = row + [candidate]
        if not row or _worst_ratio(row, length) >= _worst_ratio(new_row, length):
            row = new_row
            lst.pop(0)
        else:
            rx, ry, rw, rh = _layout_row(row, rx, ry, rw, rh, vertical, results)
            row = []
    if row:
        vertical = rw < rh
        _layout_row(row, rx, ry, rw, rh, vertical, results)
    return results


def layout_items(items: list[dict], w: float, h: float) -> list[Placed]:
    """Squarify `items` (each needs a "bytes" key) into a w x h rectangle.
    Zero-byte items are dropped. Larger items are laid out first, matching
    the JS renderer so both tools produce the same visual ordering."""
    with_bytes = [i for i in items if i.get("bytes", 0) > 0]
    total = sum(i["bytes"] for i in with_bytes) or 1
    candidates = [_Candidate(i, (i["bytes"] / total) * (w * h)) for i in with_bytes]
    candidates.sort(key=lambda c: -c.area)
    return _squarify(candidates, 0, 0, w, h)
