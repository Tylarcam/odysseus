"""Shared heuristics for extracting company/role from titles or subjects."""

from __future__ import annotations

import re
from typing import Optional

_TITLE_PATTERNS = (
    re.compile(r"^new\s+(?:job|opening|role)\s*:\s*(.+?)\s+at\s+(.+)$", re.I),
    re.compile(r"^(.+?)\s+at\s+(.+?)(?:\s+[-–—|]\s+|\s*$)", re.I),
    re.compile(r"^(.+?)\s+[-–—]\s+(.+)$"),
    re.compile(r"^(.+?)\s+:\s+(.+)$"),
)


def heuristic_company_role(title: str, body: str = "") -> tuple[Optional[str], Optional[str]]:
    title = (title or "").strip()
    for idx, pattern in enumerate(_TITLE_PATTERNS):
        match = pattern.match(title)
        if not match:
            continue
        left, right = match.group(1).strip(), match.group(2).strip()
        if not left or not right:
            continue
        if idx == 2:
            company, role = left, right
        elif " at " in left.lower():
            role, company = left, right
        elif " at " in right.lower():
            company, role = left, right
        elif len(left) <= len(right):
            role, company = left, right
        else:
            company, role = left, right
        return company, role

    if title:
        return None, title
    first_line = next((line.strip() for line in (body or "").splitlines() if line.strip()), "")
    return None, first_line or None
