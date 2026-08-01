"""Parse Mycelia blackboard / chron harvest into structured CMD Center feed."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Live canonical board (see scripts/seed_swarm.py / Culler health notes).
CANONICAL_BLACKBOARD_ID = "30abbc6f-756d-4a00-a9f6-3ef69e806f34"

_ENTRY_HEADING = re.compile(
    r"^###\s+(?P<date>\d{4}-\d{2}-\d{2})\s*[·•\-]\s*(?P<agent>.+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_FIELD_LINE = re.compile(
    r"^-\s+(?P<key>SENSED|DID|SIGNAL)\s*(?:->\s*(?P<target>[^:]+))?\s*:\s*(?P<value>.+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_TOP3_SECTION = re.compile(
    r"(?:today['']?s?\s+top\s+3|top\s+3\s+(?:priorities|actions))[^\n]*\n(.*?)(?=\n##|\n###|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_TOP3_ITEM = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$", re.MULTILINE)
_FRUIT_LINE = re.compile(r"^-\s+FRUIT:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_PENDING_SECTION = re.compile(
    r"pending\s+at\s+sporulation\s+gate[^\n]*\n(.*?)(?=\n##|\n###|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_PENDING_ROW = re.compile(r"^\|([^|]+)\|([^|]+)\|?", re.MULTILINE)


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


def _doc_text(doc: Dict[str, Any]) -> str:
    return str(doc.get("content") or doc.get("current_content") or "").strip()


def _note_text(note: Dict[str, Any]) -> str:
    return str(note.get("content") or note.get("body") or "").strip()


def is_blackboard_spill_title(title: str) -> bool:
    """True when a note title looks like a blackboard spill (not a normal todo)."""
    t = str(title or "").strip().lower()
    if not t:
        return False
    if t.startswith("⬛ blackboard"):
        return True
    if "blackboard entry" in t:
        return True
    if t.startswith("blackboard —") or t.startswith("blackboard -"):
        return True
    if t.startswith("blackboard entry") or t.startswith("blackboard append"):
        return True
    if re.match(r"^blackboard\s+\d{4}-\d{2}-\d{2}", t):
        return True
    if t.startswith("[swarm · todo]") and "blackboard" in t:
        return True
    return False


def is_swarm_health_note_title(title: str) -> bool:
    t = str(title or "").strip().lower()
    return "swarm health report" in t or (
        "culler" in t and "health" in t and "blackboard" not in t
    )


def is_blackboard_clone_doc(doc: Dict[str, Any], *, canonical_id: str = CANONICAL_BLACKBOARD_ID) -> bool:
    """Non-canonical documents that duplicate blackboard log content."""
    if str(doc.get("id") or "") == canonical_id:
        return False
    title = str(doc.get("title") or "").lower()
    if "canonical" in title and "blackboard" in title:
        return False
    if title.startswith("substrate —") or title.startswith("substrate -"):
        return False
    if "swarm plan" in title:
        return False
    if "blackboard entry" in title or "blackboard append" in title:
        return True
    if title.startswith("handoff →") and "blackboard entry" in title:
        return True
    return False


def _is_blackboard_spill(note: Dict[str, Any]) -> bool:
    return is_blackboard_spill_title(str(note.get("title") or ""))


def _is_blackboard_doc(doc: Dict[str, Any]) -> bool:
    title = str(doc.get("title") or "").lower()
    return "blackboard" in title or "substrate" in title or "swarm plan" in title


def format_blackboard_entry(entry: Dict[str, Any]) -> str:
    """Render one parsed entry as canonical blackboard markdown."""
    lines = [f"### {entry.get('date')} · {entry.get('agent')}"]
    if entry.get("sensed"):
        lines.append(f"- SENSED: {entry['sensed']}")
    if entry.get("did"):
        lines.append(f"- DID: {entry['did']}")
    if entry.get("signal"):
        target = str(entry.get("signal_target") or "").strip()
        if target:
            lines.append(f"- SIGNAL -> {target}: {entry['signal']}")
        else:
            lines.append(f"- SIGNAL: {entry['signal']}")
    return "\n".join(lines)


def merge_entries_into_board(board_text: str, entries: Iterable[Dict[str, Any]]) -> Tuple[str, int]:
    """Append entries whose hash is not already on the board. Returns (text, count)."""
    existing = parse_blackboard_entries(board_text or "")
    seen = {e.get("hash") for e in existing if e.get("hash")}
    appended = 0
    blocks: List[str] = []
    for entry in entries:
        h = entry.get("hash")
        if h and h in seen:
            continue
        if h:
            seen.add(h)
        blocks.append(format_blackboard_entry(entry))
        appended += 1
    if not blocks:
        return board_text or "", 0
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    footer = f"\n\n## Migrated spill — {stamp}\n\n" + "\n\n".join(blocks)
    return (board_text or "").rstrip() + footer, appended


def _entry_hash(date: str, agent: str, sensed: str, did: str, signal: str) -> str:
    blob = f"{date}|{agent}|{sensed}|{did}|{signal}".lower()
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def parse_blackboard_entries(
    text: str,
    *,
    source_id: str = "",
    source_kind: str = "doc",
) -> List[Dict[str, Any]]:
    """Extract dated SENSED/DID/SIGNAL blocks from markdown."""
    if not text:
        return []
    entries: List[Dict[str, Any]] = []
    headings = list(_ENTRY_HEADING.finditer(text))
    for idx, match in enumerate(headings):
        start = match.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(text)
        block = text[start:end]
        date = match.group("date").strip()
        agent = match.group("agent").strip()
        sensed = did = signal = signal_target = ""
        for field in _FIELD_LINE.finditer(block):
            key = field.group("key").upper()
            val = (field.group("value") or "").strip()
            if key == "SENSED":
                sensed = val
            elif key == "DID":
                did = val
            elif key == "SIGNAL":
                signal = val
                signal_target = (field.group("target") or "").strip()
        if not (sensed or did or signal):
            continue
        entries.append(
            {
                "date": date,
                "agent": agent,
                "sensed": sensed,
                "did": did,
                "signal": signal,
                "signal_target": signal_target,
                "source_id": source_id,
                "source_kind": source_kind,
                "hash": _entry_hash(date, agent, sensed, did, signal),
            }
        )
    return entries


def parse_top3(text: str) -> List[Dict[str, str]]:
    """Parse Today's Top 3 section into ranked items."""
    match = _TOP3_SECTION.search(text)
    if not match:
        return []
    section = match.group(1)
    items: List[Dict[str, str]] = []
    for idx, line in enumerate(_TOP3_ITEM.finditer(section), start=1):
        raw = line.group(1).strip()
        if not raw or raw.startswith("```"):
            continue
        title = raw.split("—")[0].split(" - ")[0].strip()
        rationale = ""
        if "—" in raw:
            rationale = raw.split("—", 1)[1].strip()
        elif " - " in raw and not raw.startswith("-"):
            parts = raw.split(" - ", 1)
            if len(parts) == 2:
                title, rationale = parts[0].strip(), parts[1].strip()
        items.append({"rank": idx, "title": title, "rationale": rationale, "raw": raw})
    return items[:3]


def parse_fruit_ledger(text: str) -> Dict[str, Any]:
    """Extract fruit entries and pending-at-gate rows."""
    fruits: List[Dict[str, str]] = []
    for match in _FRUIT_LINE.finditer(text):
        fruits.append({"fruit": match.group(1).strip()})
    pending: List[Dict[str, str]] = []
    sec = _PENDING_SECTION.search(text)
    if sec:
        for row in _PENDING_ROW.finditer(sec.group(1)):
            cols = [c.strip() for c in row.groups() if c and c.strip()]
            if len(cols) >= 2 and not cols[0].lower().startswith("---"):
                if cols[0].lower() in ("item", "name", "fruit"):
                    continue
                pending.append({"item": cols[0], "status": cols[1] if len(cols) > 1 else ""})
    return {"fruits": fruits[:5], "pending": pending[:5], "fruit_count": len(fruits)}


def _merge_entries(sources: Iterable[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    merged: List[Dict[str, Any]] = []
    for batch in sources:
        for entry in batch:
            key = entry.get("hash") or ""
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            merged.append(entry)
    merged.sort(key=lambda e: (e.get("date") or "", e.get("agent") or ""), reverse=True)
    return merged


def _board_health(
    *,
    board_doc: Optional[Dict[str, Any]],
    documents: List[Dict[str, Any]],
    spill_notes: List[Dict[str, Any]],
    now: datetime,
) -> Dict[str, Any]:
    stale_hours: Optional[float] = None
    board_stale = False
    if board_doc:
        updated = _parse_dt(board_doc.get("updated_at"))
        if updated:
            stale_hours = round((now - updated).total_seconds() / 3600, 1)
            board_stale = stale_hours > 48
    clone_count = sum(
        1
        for d in documents
        if _is_blackboard_doc(d)
        and str(d.get("id") or "") != CANONICAL_BLACKBOARD_ID
        and "canonical" not in str(d.get("title") or "").lower()
    )
    spill_count = len(spill_notes)
    fragmented = spill_count >= 3 or clone_count >= 2 or board_stale
    summary_bits = []
    if board_stale and stale_hours is not None:
        summary_bits.append(f"board stale {int(stale_hours)}h")
    if spill_count:
        summary_bits.append(f"{spill_count} spill notes")
    if clone_count:
        summary_bits.append(f"{clone_count} clone docs")
    return {
        "board_id": board_doc.get("id") if board_doc else None,
        "board_title": board_doc.get("title") if board_doc else None,
        "board_stale": board_stale,
        "board_stale_hours": stale_hours,
        "clone_count": clone_count,
        "spill_note_count": spill_count,
        "fragmented": fragmented,
        "summary": " · ".join(summary_bits) if summary_bits else "substrate healthy",
    }


def _build_pulse(
    entries: List[Dict[str, Any]],
    agent_activity: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Last SENSED/DID per agent, merged with recent run timestamps."""
    by_agent: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        agent = str(entry.get("agent") or "Agent").strip()
        key = agent.lower()
        existing = by_agent.get(key)
        if existing and (entry.get("date") or "") <= (existing.get("date") or ""):
            continue
        excerpt = entry.get("did") or entry.get("sensed") or entry.get("signal") or ""
        by_agent[key] = {
            "agent": agent,
            "date": entry.get("date"),
            "sensed": entry.get("sensed") or "",
            "did": entry.get("did") or "",
            "excerpt": excerpt[:160],
            "source_id": entry.get("source_id"),
            "source_kind": entry.get("source_kind"),
        }
    for act in agent_activity:
        if not act.get("swarm"):
            continue
        label = str(act.get("agent") or act.get("label") or "").strip()
        if not label:
            continue
        key = label.lower()
        row = by_agent.setdefault(
            key,
            {"agent": label, "date": "", "sensed": "", "did": "", "excerpt": "", "source_id": "", "source_kind": ""},
        )
        if act.get("raw") and not row.get("excerpt"):
            row["excerpt"] = str(act.get("raw") or "")[:160]
        row["last_run_at"] = act.get("ts")
        row["run_status"] = act.get("status")
    pulse = list(by_agent.values())
    pulse.sort(key=lambda p: p.get("date") or "", reverse=True)
    return pulse[:12]


def _build_signals(entries: List[Dict[str, Any]], *, now: datetime, hours: int = 48) -> List[Dict[str, Any]]:
    cutoff = (now - timedelta(hours=hours)).date()
    signals: List[Dict[str, Any]] = []
    for entry in entries:
        if not entry.get("signal"):
            continue
        try:
            entry_date = datetime.strptime(entry.get("date") or "", "%Y-%m-%d").date()
        except ValueError:
            continue
        if entry_date < cutoff:
            continue
        target = str(entry.get("signal_target") or "").strip()
        signals.append(
            {
                "date": entry.get("date"),
                "agent": entry.get("agent"),
                "target": target or "guild",
                "text": entry.get("signal"),
                "for_human": target.lower() in ("human", "operator", "tylar", "tcam"),
                "source_id": entry.get("source_id"),
                "source_kind": entry.get("source_kind"),
                "action": "open_note" if entry.get("source_kind") == "note" else "open_doc",
            }
        )
    signals.sort(key=lambda s: s.get("date") or "", reverse=True)
    return signals[:12]


def _build_quick_read(
    *,
    top3: List[Dict[str, str]],
    signals: List[Dict[str, Any]],
    health: Dict[str, Any],
    fruit: Dict[str, Any],
    research_excerpt: str,
) -> List[Dict[str, str]]:
    lines: List[Dict[str, str]] = []
    if top3:
        first = top3[0]
        lines.append({"kind": "priority", "text": f"Do today: {first.get('title') or first.get('raw')}"})
    human_signals = [s for s in signals if s.get("for_human")]
    if human_signals:
        lines.append({"kind": "signal", "text": f"Signal: {human_signals[0].get('text')}"})
    elif signals:
        lines.append({"kind": "signal", "text": f"Swarm signal: {signals[0].get('text')}"})
    if research_excerpt:
        lines.append({"kind": "research", "text": research_excerpt[:120]})
    pending = fruit.get("pending") or []
    if pending:
        lines.append({"kind": "fruit", "text": f"Pending fruit: {pending[0].get('item') or 'see ledger'}"})
    elif (fruit.get("fruit_count") or 0) > 0:
        lines.append({"kind": "fruit", "text": f"{fruit['fruit_count']} fruit logged today"})
    if health.get("fragmented"):
        lines.append({"kind": "health", "text": f"Board hygiene: {health.get('summary')}"})
    return lines[:5]


def _find_board_doc(documents: List[Dict[str, Any]], pinned_id: str) -> Optional[Dict[str, Any]]:
    for doc in documents:
        if str(doc.get("id") or "") == pinned_id:
            return doc
    for doc in documents:
        title = str(doc.get("title") or "").lower()
        if "canonical" in title and "blackboard" in title:
            return doc
    for doc in documents:
        if _is_blackboard_doc(doc):
            return doc
    return None


def _latest_doc_like(documents: List[Dict[str, Any]], phrases: Tuple[str, ...]) -> Optional[Dict[str, Any]]:
    matches = [
        d
        for d in documents
        if all(p in str(d.get("title") or "").lower() for p in phrases)
    ]
    if not matches:
        return None
    matches.sort(
        key=lambda d: _parse_dt(d.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return matches[0]


def build_mycelia_feed(
    *,
    documents: List[Dict[str, Any]],
    notes: List[Dict[str, Any]],
    agent_activity: Optional[List[Dict[str, Any]]] = None,
    pinned_board_id: str = CANONICAL_BLACKBOARD_ID,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build structured Mycelia harvest for CMD Center."""
    now = now or datetime.now(timezone.utc)
    agent_activity = agent_activity or []

    board_doc = _find_board_doc(documents, pinned_board_id)
    spill_notes = [n for n in notes if _is_blackboard_spill(n) and not n.get("archived")]

    entry_sources: List[List[Dict[str, Any]]] = []
    if board_doc:
        entry_sources.append(
            parse_blackboard_entries(
                _doc_text(board_doc),
                source_id=str(board_doc.get("id") or ""),
                source_kind="doc",
            )
        )
    for note in spill_notes:
        entry_sources.append(
            parse_blackboard_entries(
                _note_text(note),
                source_id=str(note.get("id") or ""),
                source_kind="note",
            )
        )

    entries = _merge_entries(entry_sources)

    top3_text = _doc_text(board_doc) if board_doc else ""
    plan_doc = _latest_doc_like(documents, ("swarm", "plan"))
    if plan_doc:
        top3_text = top3_text + "\n\n" + _doc_text(plan_doc)
    top3 = parse_top3(top3_text)

    ledger_doc = _latest_doc_like(documents, ("fruit", "ledger"))
    fruit = parse_fruit_ledger(_doc_text(ledger_doc) if ledger_doc else "")

    research_doc = _latest_doc_like(documents, ("research", "brief"))
    research_excerpt = ""
    if research_doc:
        body = _doc_text(research_doc).replace("\n", " ").strip()
        research_excerpt = body[:200]

    health = _board_health(board_doc=board_doc, documents=documents, spill_notes=spill_notes, now=now)
    signals = _build_signals(entries, now=now)
    pulse = _build_pulse(entries, agent_activity)
    quick_read = _build_quick_read(
        top3=top3,
        signals=signals,
        health=health,
        fruit=fruit,
        research_excerpt=research_excerpt,
    )

    return {
        "board": {
            "id": board_doc.get("id") if board_doc else pinned_board_id,
            "title": board_doc.get("title") if board_doc else "Swarm Blackboard",
        },
        "top3": top3,
        "entries": entries[:20],
        "signals": signals,
        "pulse": pulse,
        "fruit": {
            **fruit,
            "ledger_id": ledger_doc.get("id") if ledger_doc else None,
            "ledger_title": ledger_doc.get("title") if ledger_doc else None,
        },
        "health": health,
        "quick_read": quick_read,
        "research_excerpt": research_excerpt,
    }


def mycelia_priority_queue_items(feed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map Top 3 into priority_queue rows."""
    board_id = (feed.get("board") or {}).get("id") or ""
    items: List[Dict[str, Any]] = []
    for row in feed.get("top3") or []:
        rank = int(row.get("rank") or 0)
        title = str(row.get("title") or row.get("raw") or "Mycelia priority").strip()
        rationale = str(row.get("rationale") or "").strip()
        items.append(
            {
                "id": f"mycelia-top3-{rank}",
                "kind": "mycelia_priority",
                "title": title,
                "subtitle": rationale or f"Mycelia · Top {rank} from blackboard",
                "branch": "mycelia",
                "urgency": max(82, 88 - rank),
                "status": "due",
                "due_label": f"TOP {rank}",
                "overdue_days": None,
                "due_at": None,
                "action": "open_doc" if board_id else "tasks",
                "target_id": board_id or None,
                "ts": None,
                "dedup_key": f"mycelia:top3:{rank}",
            }
        )
    return items
