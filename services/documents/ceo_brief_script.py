"""CEO Brief full-picture harvest (09:00 cron + vault BRIEF ME / CMD Center card).

Sections, in order:
  Top 3 actions that move the needle (ranked items + Swarm Plan excerpt)
  What's upcoming
  Job pipeline
  Handoffs in flight
  Research findings (Rhizo)
  Fruit ledger (Herald)
  Recent chron outputs

Matches Library gold-standard ``CEO Brief — 2026-08-17`` (id 16a63f76).
Top 3 lives *inside* this complete brief — never instead of it.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

_TIMEOUT_MARKERS = ("timeout", "timed out", "timed-out")
_MISS_MARKERS = ("not ready", "missed", "harvest not ready")
_FAIL_STATUSES = {"error", "failed"}

_TOP3_SECTION = re.compile(
    r"(?:^|\n)#*\s*(?:today['']?s?\s+)?top\s+3[^\n]*\n(.*?)(?=\n##|\n###|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_TOP3_ITEM = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$", re.MULTILINE)

# 08-17 gold-standard harvest. Slim spoken scripts (Headline / Needs you) fail this.
FULL_PICTURE_HEADINGS = (
    "Top 3",
    "Inbound opportunity",
    "What's upcoming",
    "Job pipeline",
    "Handoffs",
    "Research findings",
    "Fruit ledger",
    "Recent chron",
)


def is_full_picture_brief(text: str) -> bool:
    """True when the Library brief has the 08-17 harvest section set."""
    blob = (text or "").lower()
    return all(heading.lower() in blob for heading in FULL_PICTURE_HEADINGS)


def classify_task_run(run: Dict[str, Any]) -> str:
    """Return failed | timeout | missed | success | silence."""
    st = str((run or {}).get("status") or "").strip().lower()
    blob = f"{(run or {}).get('result') or ''} {(run or {}).get('error') or ''}".lower()
    if st == "aborted":
        return "silence"
    if st == "timeout" or any(m in blob for m in _TIMEOUT_MARKERS):
        return "timeout"
    if st in _FAIL_STATUSES:
        return "failed"
    if st == "skipped" and any(m in blob for m in _MISS_MARKERS):
        return "missed"
    if st in ("success", "completed", "ok"):
        return "success"
    return "silence"


def excerpt(text: str, n: int = 1500) -> str:
    t = (text or "").strip()
    if len(t) <= n:
        return t
    return t[:n] + "…"


def _live_fruit_body(text: str) -> str:
    """Return ledger text only when it has live ``- FRUIT:`` lines, never a how-to."""
    from services.home.mycelia_feed import is_fruit_howto_text, live_fruit_count

    body = (text or "").strip()
    if not body or is_fruit_howto_text(body) or live_fruit_count(body) <= 0:
        return ""
    return body


def harvest_fruit_ledger_text(
    documents: Optional[List[Dict[str, Any]]] = None,
    notes: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Same source Mycelia / BRIEF ME uses via ``find_fruit_ledger``.

    Live ``FRUIT:`` lines beat an empty titled Library doc. How-to / template
    / Culler-remediation fruit docs (no ``- FRUIT:`` lines) are skipped.
    Tie-break: Library fruit+ledger doc with live fruit, then note ``506a37f1``,
    then other fruit+ledger notes. No live fruit → empty string (honest stub).
    """
    from services.home.mycelia_feed import find_fruit_ledger

    found = find_fruit_ledger(documents, notes)
    rec = (found or {}).get("record") or {}
    return _live_fruit_body(
        str(rec.get("content") or rec.get("current_content") or rec.get("body") or "")
    )


def _title_of(item: Any, fallback: str = "Untitled") -> str:
    if isinstance(item, dict):
        t = str(item.get("title") or item.get("name") or "").strip()
        if t:
            return t
    return fallback


def _parse_numbered_top3(text: str) -> List[str]:
    match = _TOP3_SECTION.search(text or "")
    if not match:
        return []
    items: List[str] = []
    for line in _TOP3_ITEM.finditer(match.group(1)):
        raw = line.group(1).strip()
        if not raw or raw.startswith("```"):
            continue
        items.append(raw)
        if len(items) >= 3:
            break
    return items


def _fallback_top3(
    *,
    jobs: Dict[str, Any],
    handoffs: Dict[str, Any],
    overdue: Iterable[Any],
) -> List[str]:
    lines: List[str] = []
    for j in list(jobs.get("ready_to_apply") or []):
        if len(lines) >= 3:
            break
        lines.append(
            f"Submit {j.get('company') or '?'} — {j.get('role') or '?'}"
        )
    for j in list(jobs.get("needs_review") or []):
        if len(lines) >= 3:
            break
        lines.append(
            f"Decide {j.get('company') or '?'} — {j.get('role') or '?'}"
        )
    for h in list(handoffs.get("needs_attention") or []):
        if len(lines) >= 3:
            break
        target = h.get("handoff_target") or "?"
        lines.append(f"Unblock {_title_of(h)} → {target}")
    for item in list(overdue or []):
        if len(lines) >= 3:
            break
        lines.append(f"Clear overdue: {_title_of(item)}")
    return lines[:3]


# --- Objectives charter (ranking law for Money Move / BRIEF ME) ---------------
# Writable note titled `Objectives — {quarter}`. Empty stub ≠ law; filled
# D/W/M/Y outranks Swarm Plan job-submit hygiene when they conflict.

_OBJECTIVES_TITLE = re.compile(r"^objectives\s*[—–-]\s*", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"^[.…\s_\-–—]+$|^unknown$|^tbd$|^n/?a$", re.IGNORECASE)
_JOB_HYGIENE = re.compile(
    r"(submit\s+prelim|prelim\s+[—–-]\s*swe|handshake|job\s*queue|"
    r"ready\s+to\s+apply|ft\s+app|job\s+pipeline|"
    r"submit\s+\S+\s+[—–-]\s*(pm|engineer|swe|pack|product))",
    re.IGNORECASE,
)
_PROSPERITY = re.compile(
    r"\b(grant|proposal|inbound|upwork|side[- ]hustle|kanban|"
    r"fruit|residue|onboard|over-deliver|fred hutch)\b",
    re.IGNORECASE,
)
_JOB_LEAD = re.compile(
    r"job applications\s*[—–-]|handshake|indeed\.com|ready to apply|"
    r"job\s*queue|job pipeline|ft\s+app",
    re.IGNORECASE,
)
_INBOUND_SLOGAN = re.compile(
    r"close money residue|capture inbound|staged proposals|"
    r"not job-queue|kanban revenue|protect focus|do not invent",
    re.IGNORECASE,
)
_INBOUND_CONCRETE = re.compile(
    r"\b((?:grant|grants)\s+(?:rfp|rfps|proposal|application|deadline)|rfp|rfps|"
    r"invoice|invoices|unpaid|"
    r"npr|retainer|paid inbound|honorarium|"
    r"thank-you email|thank you email|send pack|proposal pack|"
    r"human gate)\b",
    re.IGNORECASE,
)
_EMAIL_MONEY = re.compile(
    r"\b(grant|rfp|request for proposals?|invoice|unpaid|past due|"
    r"payment due|upwork|contract award|retainer|honorarium)\b",
    re.IGNORECASE,
)
_SKIP_INBOUND_DOC = re.compile(
    r"ceo brief|swarm (plan|substrate)|fruit ledger|research brief|grant grafter",
    re.IGNORECASE,
)
_SKIP_GRANT_PARSE = re.compile(
    r"ceo brief|swarm (plan|substrate)|fruit ledger|grant grafter",
    re.IGNORECASE,
)
_GRANT_GRAFTER = re.compile(r"grant grafter", re.IGNORECASE)
_GRANT_CATALOG_TITLE = re.compile(
    r"grant scout|grant catalog",
    re.IGNORECASE,
)
_GRANT_CALL_TITLE = re.compile(
    r"\b(rfp|rfps|request for proposals?|insight grants?|"
    r"grant (?:call|competition|catalog|scout|deadline|program))\b",
    re.IGNORECASE,
)
_GRANT_CITE = re.compile(r"\[(?:page|web):[^\]]+\]")
_GRANT_ISO = re.compile(r"\b(\d{4})-(\d{2})(?:-(\d{2}))?\b")
_GRANT_ROLLING = re.compile(r"\brolling\b", re.IGNORECASE)
_GRANT_HARD_GATE = re.compile(
    r"\b(noi|loi|n\.o\.i\.|l\.o\.i\.|letter of intent|"
    r"notice of intent|registration|intent to apply)\b",
    re.IGNORECASE,
)
_GRANT_REMAINING = re.compile(r"\b(replacement|nomination)\b", re.IGNORECASE)
_TRAINEE_CALL = re.compile(
    r"\b(trainee|doctoral|student|research[\s-]?training)\b",
    re.IGNORECASE,
)
_IMPACT_PLUS = re.compile(r"impact\+", re.IGNORECASE)
_NOMINATION_GATE = re.compile(r"nomination\s+gate", re.IGNORECASE)
_FACULTY_PI_CALL = re.compile(
    r"\bfaculty(?:[\s-]*(?:led|pi|principal))?\b|\binsight grants?\b",
    re.IGNORECASE,
)
_CHARTER_FACULTY_PI = re.compile(
    r"\bfaculty[\s-]*(?:led|pi|principal(?:\s+investigator)?)\b",
    re.IGNORECASE,
)
GRANT_CATALOG_BODY_CHARS = 8000
_NO_GRANT_RFP_LINE = "_No grant/RFP on file._"
_INBOUND_EMAIL_TAGS = {"finance", "bills"}
_PROMO_TAGS = {"newsletter", "marketing"}
_JOB_GATE = ("gated", "deferred", "not the needle", "hygiene", "kanban revenue")
_CHARTER_H2 = re.compile(
    r"(?:^|\n)##\s+([^\n]+)\n(.*?)(?=\n##|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_CHARTER_BULLET = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$", re.MULTILINE)

Top3Candidate = Union[str, Dict[str, Any]]


def is_objectives_charter_title(title: str) -> bool:
    return bool(_OBJECTIVES_TITLE.match((title or "").strip()))


def find_objectives_charter(
    records: Optional[Iterable[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """Pinned `Objectives — {quarter}` note/doc. Prefer pinned, then newest."""
    hits: List[Dict[str, Any]] = []
    for rec in records or []:
        if rec.get("archived"):
            continue
        if is_objectives_charter_title(str(rec.get("title") or "")):
            hits.append(rec)
    if not hits:
        return None
    hits.sort(
        key=lambda r: (bool(r.get("pinned")), str(r.get("updated_at") or "")),
        reverse=True,
    )
    return hits[0]


def _horizon_key(heading: str) -> Optional[str]:
    h = (heading or "").strip().lower()
    if "daily" in h:
        return "daily"
    if "weekly" in h or "kpi" in h:
        return "weekly"
    if "monthly" in h or "portfolio" in h:
        return "monthly"
    if "yearly" in h or "mission" in h or "12–18" in h or "12-18" in h:
        return "yearly"
    if "quarter" in h or "key result" in h:
        return "quarter"
    if "kill" in h:
        return "kill"
    return None


def parse_charter_horizons(text: str) -> Dict[str, str]:
    """D/W/M/Y (plus quarter/kill) bodies from the Objectives note."""
    out: Dict[str, str] = {
        "daily": "",
        "weekly": "",
        "monthly": "",
        "yearly": "",
        "quarter": "",
        "kill": "",
    }
    for match in _CHARTER_H2.finditer(text or ""):
        key = _horizon_key(match.group(1))
        if not key:
            continue
        body = match.group(2).strip()
        if out.get(key):
            out[key] = (out[key] + "\n" + body).strip()
        else:
            out[key] = body
    return out


def _is_placeholder(text: str) -> bool:
    t = (text or "").strip().strip("*").strip()
    if not t:
        return True
    if _PLACEHOLDER.match(t):
        return True
    return t in {"…", "...", "—", "-"}


def charter_is_filled(text: str) -> bool:
    """True when at least one D/W/M/Y (or quarter KR) line is real, not a stub ellipsis."""
    horizons = parse_charter_horizons(text or "")
    for body in horizons.values():
        for line in _CHARTER_BULLET.finditer(body):
            if not _is_placeholder(line.group(1)):
                return True
        prose = " ".join(
            ln.strip()
            for ln in body.splitlines()
            if ln.strip() and not ln.strip().startswith("#") and not _CHARTER_BULLET.match(ln)
        )
        if prose and not _is_placeholder(prose[:80]):
            return True
    return False


def charter_elevates_jobs(text: str) -> bool:
    """Job-submit is #1 only if the charter itself says so (and not gated)."""
    low = (text or "").lower()
    if not low.strip() or not charter_is_filled(text):
        return False
    gated = any(marker in low for marker in _JOB_GATE)
    wants = bool(
        re.search(
            r"(submit\s+prelim|apply\s+this\s+week|ft\s+app|job\s+application|"
            r"handshake\s+apply)",
            low,
        )
    )
    return bool(wants and not gated)


def charter_needles(text: str) -> List[str]:
    """Daily / weekly / quarter bullets the charter already named."""
    if not charter_is_filled(text):
        return []
    out: List[str] = []
    horizons = parse_charter_horizons(text)
    for key in ("daily", "weekly", "quarter"):
        body = horizons.get(key) or ""
        for line in _CHARTER_BULLET.finditer(body):
            raw = line.group(1).strip()
            if _is_placeholder(raw):
                continue
            if raw.lower().startswith("pinned"):
                continue
            out.append(raw)
    return out[:5]


def _item_raw(item: Top3Candidate) -> str:
    if isinstance(item, dict):
        return str(item.get("raw") or item.get("title") or "").strip()
    return str(item).strip()


def _item_title(item: Top3Candidate) -> str:
    if isinstance(item, dict):
        title = str(item.get("title") or "").strip()
        if title:
            return title.strip("*").strip()
    raw = _item_raw(item)
    title = raw.split("—")[0].split(" - ")[0].strip()
    return title.strip("*").strip() or raw


def _open_item_count(rec: Dict[str, Any]) -> int:
    items = rec.get("items")
    if not isinstance(items, list):
        return 0
    return sum(
        1
        for it in items
        if isinstance(it, dict) and not it.get("done") and not it.get("checked")
    )


_GATE_CLEARED_MARK = re.compile(
    r"\((sent|cleared|done)\)|gate cleared|marked sent|all \d+ sent",
    re.IGNORECASE,
)


def is_upwork_send_gate(text: str) -> bool:
    """True for the Upwork HUMAN GATE pack / send-proposals checklist."""
    low = (text or "").lower()
    if "upwork" not in low:
        return False
    return "human gate" in low or "send pack" in low or "proposal" in low


def human_gate_cleared(
    *,
    notes: Optional[Iterable[Dict[str, Any]]] = None,
    documents: Optional[Iterable[Dict[str, Any]]] = None,
) -> bool:
    """True when the Upwork send checklist is done or the pack is marked sent."""
    for rec in notes or []:
        if not isinstance(rec, dict) or rec.get("archived"):
            continue
        title = str(rec.get("title") or "")
        if not is_upwork_send_gate(title):
            continue
        items = rec.get("items")
        if isinstance(items, list) and items and _open_item_count(rec) == 0:
            return True
        if _GATE_CLEARED_MARK.search(title):
            return True
    for rec in documents or []:
        if not isinstance(rec, dict):
            continue
        title = str(rec.get("title") or rec.get("name") or "")
        if is_upwork_send_gate(title) and (
            rec.get("archived") or _GATE_CLEARED_MARK.search(title)
        ):
            return True
    return False


def is_concrete_inbound_text(text: str) -> bool:
    """True for a named pack/email/NPR/grant — not charter slogans or job leads."""
    blob = text or ""
    if _JOB_LEAD.search(blob) or _JOB_HYGIENE.search(blob):
        return False
    if _INBOUND_SLOGAN.search(blob):
        return False
    return bool(_INBOUND_CONCRETE.search(blob))


def is_inbound_item(cand: Top3Candidate) -> bool:
    if isinstance(cand, dict) and cand.get("source") in ("email", "note", "doc", "inbound"):
        return True
    if isinstance(cand, dict) and cand.get("kind") == "grant":
        return True
    return is_concrete_inbound_text(_item_raw(cand))


def is_grant_catalog_title(title: str) -> bool:
    """Library Grant Scout / catalog docs — not Grant Grafter."""
    t = title or ""
    if _GRANT_GRAFTER.search(t):
        return False
    return bool(_GRANT_CATALOG_TITLE.search(t))


def is_grant_call_title(title: str) -> bool:
    """Named RFP / grant competition — not prosperity slogans or Grafter."""
    t = title or ""
    if _GRANT_GRAFTER.search(t) or _INBOUND_SLOGAN.search(t):
        return False
    if _JOB_LEAD.search(t) or _JOB_HYGIENE.search(t):
        return False
    return bool(_GRANT_CALL_TITLE.search(t))


def _rec_body(rec: Dict[str, Any]) -> str:
    return str(rec.get("content") or rec.get("current_content") or rec.get("body") or "")


def _clean_grant_cell(text: str) -> str:
    return re.sub(r"\s+", " ", _GRANT_CITE.sub("", text or "")).strip()


def _split_md_row(line: str) -> List[str]:
    s = (line or "").strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _grant_header_map(cells: Sequence[str]) -> Optional[Dict[str, int]]:
    names = [re.sub(r"[^a-z0-9]+", "_", (c or "").strip().lower()).strip("_") for c in cells]
    if "reason_rejected" in names:
        return None
    idx: Dict[str, int] = {}
    for i, name in enumerate(names):
        if name in ("name", "program", "title"):
            idx.setdefault("name", i)
        elif name in ("funder", "source", "agency"):
            idx.setdefault("funder", i)
        elif name in ("deadline", "due", "close"):
            idx.setdefault("deadline", i)
        elif name in ("official_url", "url", "link"):
            idx.setdefault("url", i)
        elif name == "fit":
            idx.setdefault("fit", i)
        elif name == "stage":
            idx.setdefault("stage", i)
        elif name == "citizenship":
            idx.setdefault("citizenship", i)
        elif name == "notes":
            idx.setdefault("notes", i)
    if "name" not in idx:
        return None
    if "deadline" not in idx and "url" not in idx and "funder" not in idx:
        return None
    return idx


def _parse_grant_dates(text: str) -> List[date]:
    out: List[date] = []
    for match in _GRANT_ISO.finditer(text or ""):
        year, month, day = int(match.group(1)), int(match.group(2)), match.group(3)
        try:
            out.append(date(year, month, int(day) if day else 1))
        except ValueError:
            continue
    return out


def _deadline_clauses(text: str) -> List[str]:
    parts = [c.strip() for c in re.split(r"[;|/]", text or "") if c.strip()]
    return parts or [text or ""]


def _format_grant_due(due: date, cleaned: str) -> str:
    if due.day == 1 and not re.search(r"\d{4}-\d{2}-\d{2}", cleaned):
        return due.strftime("%Y-%m")
    return due.isoformat()


def _grant_window(row: Dict[str, Any], today: date) -> tuple:
    """(is_open, soonest future executable date or None).

    A past NOI/LOI/registration closes the call. 'Full application later in
    2026' is not executable after that gate. A future replacement nomination
    (or any other future ISO date with no past hard gate) stays open.
    """
    deadline = str(row.get("deadline") or "")
    past_hard = False
    future_exec: List[date] = []
    all_dates: List[date] = []
    remaining_future: List[date] = []
    for clause in _deadline_clauses(deadline):
        dates = _parse_grant_dates(clause)
        all_dates.extend(dates)
        hard = bool(_GRANT_HARD_GATE.search(clause))
        remaining = bool(_GRANT_REMAINING.search(clause))
        for d in dates:
            if d >= today:
                future_exec.append(d)
                if remaining:
                    remaining_future.append(d)
            elif hard:
                past_hard = True
        if hard and not dates:
            past_hard = True
    if past_hard:
        if remaining_future:
            return True, min(remaining_future)
        return False, None
    if future_exec:
        return True, min(future_exec)
    if _GRANT_ROLLING.search(deadline) and not all_dates:
        return True, None
    return False, None


def _grant_deadline_label(text: str, today: Optional[date] = None) -> str:
    cleaned = _clean_grant_cell(text)
    _open, due = _grant_window({"deadline": cleaned}, today or date.today())
    if due:
        return _format_grant_due(due, cleaned)
    dates = _parse_grant_dates(cleaned)
    if dates:
        return _format_grant_due(max(dates), cleaned)
    return cleaned[:48]


def charter_wants_faculty_pi(text: str) -> bool:
    """True only when the charter names a faculty PI / faculty-led needle."""
    return bool(_CHARTER_FACULTY_PI.search(text or ""))


def _grant_evidence(row: Dict[str, Any]) -> str:
    """Title + catalog cells only. Never infers eligibility beyond the row."""
    return " ".join(
        str(row.get(k) or "")
        for k in ("name", "stage", "citizenship", "notes")
    )


def _grant_exec_lane(text: str, *, charter_txt: str = "") -> int:
    """0 trainee/doctoral, 1 other, 2 faculty PI — unless charter names faculty PI."""
    blob = text or ""
    trainee = bool(_TRAINEE_CALL.search(blob))
    faculty = bool(_FACULTY_PI_CALL.search(blob))
    if charter_wants_faculty_pi(charter_txt):
        if faculty:
            return 0
        return 1
    if trainee:
        return 0
    if faculty:
        return 2
    return 1


def _is_nomination_packet(cand: Top3Candidate) -> bool:
    """True for a trainee nomination-gate note — executable, not a catalog row."""
    if not isinstance(cand, dict):
        return False
    if str(cand.get("source") or "").strip().lower() != "note":
        return False
    blob = " ".join(
        str(cand.get(k) or "")
        for k in ("title", "raw", "grant_evidence")
    )
    return bool(_IMPACT_PLUS.search(blob) or _NOMINATION_GATE.search(blob))


def _grant_sort_key(row: Dict[str, Any], today: date) -> tuple:
    open_slot, due = _grant_window(row, today)
    try:
        fit = int(row.get("fit") or 0)
    except (TypeError, ValueError):
        fit = 0
    lane = _grant_exec_lane(_grant_evidence(row))
    if open_slot:
        due_ord = due.toordinal() if due else 999999
        return (0, lane, due_ord, -fit)
    dates = _parse_grant_dates(str(row.get("deadline") or ""))
    past_ord = -max(dates).toordinal() if dates else 0
    return (1, lane, past_ord, -fit)


def extract_grant_calls_from_text(
    text: str,
    *,
    source_id: str,
    source_kind: str,
    source_title: str = "",
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Named grant/RFP rows already on file. Never invents programs or dollars."""
    _ = source_title
    if not text or not source_id:
        return []
    today = today or date.today()
    found: List[Dict[str, Any]] = []
    lines = (text or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if "|" not in line:
            i += 1
            continue
        header = _grant_header_map(_split_md_row(line))
        if not header:
            i += 1
            continue
        i += 1
        if i < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i].strip()):
            i += 1
        while i < len(lines) and "|" in lines[i]:
            cells = _split_md_row(lines[i])
            i += 1
            if not cells or all(re.match(r"^:?-{2,}:?$", c or "") for c in cells):
                continue
            name_i = header["name"]
            if name_i >= len(cells):
                continue
            name = _clean_grant_cell(cells[name_i])
            if not name or name.lower() in ("name", "program", "title"):
                continue
            funder = ""
            if "funder" in header and header["funder"] < len(cells):
                funder = _clean_grant_cell(cells[header["funder"]])
            deadline = ""
            if "deadline" in header and header["deadline"] < len(cells):
                deadline = _clean_grant_cell(cells[header["deadline"]])
            url = ""
            if "url" in header and header["url"] < len(cells):
                url_cell = _clean_grant_cell(cells[header["url"]])
                match = re.search(r"https?://\S+", url_cell)
                url = match.group(0).rstrip(").,]") if match else ""
            fit = 0
            if "fit" in header and header["fit"] < len(cells):
                fit_m = re.match(r"(\d+)", _clean_grant_cell(cells[header["fit"]]))
                if fit_m:
                    fit = int(fit_m.group(1))
            extra: Dict[str, str] = {}
            for key in ("stage", "citizenship", "notes"):
                if key in header and header[key] < len(cells):
                    extra[key] = _clean_grant_cell(cells[header[key]])
            if not (funder or deadline or url):
                continue
            found.append({
                "name": name,
                "funder": funder,
                "deadline": deadline,
                "url": url,
                "fit": fit,
                "source_id": source_id,
                "source_kind": source_kind,
                **extra,
            })
        continue
    found.sort(key=lambda row: _grant_sort_key(row, today))
    return found


def find_grant_packet(
    grant_title: str,
    notes: Optional[Iterable[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Trainee nomination-gate checklist for a named grant. Notes only — not the catalog."""
    name = str(grant_title or "").strip()
    if not name:
        return None
    hits: List[Dict[str, Any]] = []
    for rec in notes or []:
        if not isinstance(rec, dict) or rec.get("archived"):
            continue
        title = str(rec.get("title") or "").strip()
        if not title or is_objectives_charter_title(title) or is_upwork_send_gate(title):
            continue
        items = rec.get("items")
        has_items = isinstance(items, list) and bool(items)
        packetish = bool(_NOMINATION_GATE.search(title)) or has_items
        if not packetish:
            continue
        if _IMPACT_PLUS.search(name) and _IMPACT_PLUS.search(title):
            hits.append(rec)
    if not hits:
        return None
    hits.sort(
        key=lambda r: (bool(r.get("pinned")), str(r.get("updated_at") or "")),
        reverse=True,
    )
    return hits[0]


def _grant_candidate(row: Dict[str, Any], today: Optional[date] = None) -> Dict[str, Any]:
    sid = str(row.get("source_id") or "").strip()
    kind = str(row.get("source_kind") or "doc")
    action = "open_note" if kind == "note" else "open_doc"
    name = str(row.get("name") or "").strip()
    funder = str(row.get("funder") or "").strip()
    today = today or date.today()
    open_slot, due_d = _grant_window(row, today)
    due = _grant_deadline_label(str(row.get("deadline") or ""), today)
    id8 = sid[:8]
    detail: List[str] = []
    if funder:
        detail.append(funder)
    if due:
        detail.append(f"due {due}")
    raw = name
    if detail:
        raw = f"{name} — {' · '.join(detail)}"
    if id8:
        raw = f"{raw} (`{id8}`)"
    return {
        "title": name,
        "raw": raw,
        "rationale": "Grant/RFP already on file — not invented.",
        "source": kind,
        "kind": "grant",
        "grant_open": open_slot,
        "grant_due": due_d.isoformat() if due_d else "",
        "grant_evidence": _grant_evidence(row),
        "action": action,
        "target_id": sid,
        "id": sid,
    }


def collect_grant_calls(
    *,
    notes: Optional[Iterable[Dict[str, Any]]] = None,
    documents: Optional[Iterable[Dict[str, Any]]] = None,
    today: Optional[date] = None,
    limit: int = 2,
) -> List[Dict[str, Any]]:
    """1–2 real grant/RFP calls from notes + Library. No invented RFPs or dollars."""
    today = today or date.today()
    rows: List[Dict[str, Any]] = []
    seen_names: set[str] = set()

    def _absorb(rec: Dict[str, Any], source_kind: str) -> None:
        if rec.get("archived"):
            return
        title = str(rec.get("title") or rec.get("name") or "").strip()
        if not title or is_objectives_charter_title(title) or _SKIP_GRANT_PARSE.search(title):
            return
        rid = str(rec.get("id") or "").strip()
        if not rid:
            return
        body = _rec_body(rec)
        extracted = extract_grant_calls_from_text(
            body,
            source_id=rid,
            source_kind=source_kind,
            source_title=title,
            today=today,
        )
        if extracted:
            for row in extracted:
                key = re.sub(r"\s+", " ", row["name"].lower())
                if key in seen_names:
                    continue
                seen_names.add(key)
                rows.append(row)
            return
        if is_grant_call_title(title):
            key = re.sub(r"\s+", " ", title.lower())
            if key in seen_names:
                return
            seen_names.add(key)
            rows.append({
                "name": title,
                "funder": "",
                "deadline": "",
                "url": "",
                "fit": 0,
                "source_id": rid,
                "source_kind": source_kind,
            })

    for rec in documents or []:
        if isinstance(rec, dict):
            _absorb(rec, "doc")
    for rec in notes or []:
        if isinstance(rec, dict):
            _absorb(rec, "note")
    rows.sort(key=lambda row: _grant_sort_key(row, today))
    open_rows = [row for row in rows if _grant_window(row, today)[0]]
    picked = (open_rows or rows)[:limit]
    for row in picked:
        packet = find_grant_packet(str(row.get("name") or ""), notes)
        if not packet:
            continue
        pid = str(packet.get("id") or "").strip()
        if not pid:
            continue
        row["source_id"] = pid
        row["source_kind"] = "note"
    return [_grant_candidate(row, today) for row in picked]


def collect_inbound_candidates(
    *,
    comms_preview: Optional[Iterable[Dict[str, Any]]] = None,
    notes: Optional[Iterable[Dict[str, Any]]] = None,
    documents: Optional[Iterable[Dict[str, Any]]] = None,
    today: Optional[date] = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """1–3 real inbound money items. Never invents grants or job-queue leads."""
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    notes_list = [n for n in (notes or []) if isinstance(n, dict)]
    docs_list = [d for d in (documents or []) if isinstance(d, dict)]
    upwork_cleared = human_gate_cleared(notes=notes_list, documents=docs_list)
    grant_items = collect_grant_calls(notes=notes_list, documents=docs_list, today=today)

    def _add(item: Dict[str, Any]) -> None:
        if len(out) >= limit:
            return
        raw = _item_raw(item)
        key = re.sub(r"[*_`]", "", raw.lower())
        key = re.sub(r"\s+", " ", key).strip()
        if not key or key in seen:
            return
        seen.add(key)
        out.append(item)

    for em in comms_preview or []:
        if not isinstance(em, dict):
            continue
        tags = [str(t).strip().lower().replace("_", "-") for t in (em.get("tags") or [])]
        subj = str(em.get("subject") or "").strip()
        reason = str(em.get("reason") or "").strip()
        frm = str(em.get("from") or "").strip()
        blob = f"{subj} {reason} {frm} {' '.join(tags)}"
        if _JOB_LEAD.search(blob) or _JOB_HYGIENE.search(blob):
            continue
        if any(t in _PROMO_TAGS for t in tags):
            continue
        money = bool(_EMAIL_MONEY.search(blob))
        tagged = bool(set(tags) & _INBOUND_EMAIL_TAGS) and money
        if not (money or tagged):
            continue
        uid = str(em.get("uid") or em.get("id") or "").strip()
        uid_short = uid.split(":")[-1][:12]
        raw = f"Reply: {subj or '(no subject)'}"
        if frm:
            raw += f" — {frm}"
        if uid_short:
            raw += f" (`{uid_short}`)"
        _add({
            "title": subj or "Inbound email",
            "raw": raw,
            "rationale": reason or "Tagged inbox opportunity",
            "source": "email",
            "action": "email",
            "target_id": str(em.get("id") or uid),
            "id": str(em.get("id") or uid),
        })

    for grant in grant_items:
        _add(grant)

    for rec in notes_list:
        if rec.get("archived"):
            continue
        title = str(rec.get("title") or "").strip()
        if not title or is_objectives_charter_title(title):
            continue
        if not is_concrete_inbound_text(title):
            continue
        gate = is_upwork_send_gate(title)
        items = rec.get("items")
        if gate and isinstance(items, list) and items and _open_item_count(rec) == 0:
            continue
        if gate and upwork_cleared:
            continue
        nid = str(rec.get("id") or "").strip()
        id8 = nid[:8]
        open_n = _open_item_count(rec)
        suffix = f" — {open_n} open" if open_n else ""
        raw = f"{title}{suffix}" + (f" (`{id8}`)" if id8 else "")
        _add({
            "title": title,
            "raw": raw,
            "rationale": "Residue already on file — not an invented grant.",
            "source": "note",
            "action": "open_note",
            "target_id": nid,
            "id": nid,
        })

    for rec in docs_list:
        if rec.get("archived"):
            continue
        title = str(rec.get("title") or rec.get("name") or "").strip()
        if not title or _SKIP_INBOUND_DOC.search(title):
            continue
        if not is_concrete_inbound_text(title):
            continue
        if is_upwork_send_gate(title) and (upwork_cleared or _GATE_CLEARED_MARK.search(title)):
            continue
        did = str(rec.get("id") or "").strip()
        id8 = did[:8]
        raw = f"{title}" + (f" (`{id8}`)" if id8 else "")
        _add({
            "title": title,
            "raw": raw,
            "rationale": "Proposal/send pack already in the Library.",
            "source": "doc",
            "action": "open_doc",
            "target_id": did,
            "id": did,
        })

    return out[:limit]


def as_top3_items(candidates: Sequence[Top3Candidate]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for idx, cand in enumerate(candidates, start=1):
        if isinstance(cand, dict):
            raw = _item_raw(cand)
            title = _item_title(cand)
            rationale = str(cand.get("rationale") or "")
        else:
            raw = _item_raw(cand)
            title = _item_title(cand)
            rationale = raw.split("—", 1)[1].strip() if "—" in raw else ""
        row: Dict[str, Any] = {"rank": idx, "title": title, "rationale": rationale, "raw": raw}
        if isinstance(cand, dict):
            for key in (
                "source", "target_id", "action", "id", "kind",
                "grant_open", "grant_due", "grant_evidence",
            ):
                val = cand.get(key)
                if val or key == "grant_open":
                    if val is not None and val != "":
                        row[key] = val
        items.append(row)
    return items


def rank_money_candidates(
    candidates: Sequence[Top3Candidate],
    charter_txt: str = "",
    *,
    limit: int = 3,
) -> List[Dict[str, str]]:
    """Charter-aligned prosperity outranks Swarm Plan job-submit hygiene."""
    filled = charter_is_filled(charter_txt)
    elevate_jobs = charter_elevates_jobs(charter_txt)
    tokens = set(re.findall(r"[a-z]{4,}", (charter_txt or "").lower()))
    seen: set[str] = set()
    uniq: List[Top3Candidate] = []
    for cand in candidates:
        key = re.sub(r"[*_`]", "", _item_raw(cand).lower())
        key = re.sub(r"\s+", " ", key).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(cand)

    def _inbound_weight(cand: Top3Candidate) -> int:
        if isinstance(cand, dict):
            if str(cand.get("kind") or "") == "grant":
                return 4 if cand.get("grant_open", True) else 2
            src = str(cand.get("source") or "")
            if src == "email":
                return 3
            if src == "doc":
                # Library send pack outranks the sibling checklist note.
                blob = _item_raw(cand)
                return 3 if is_upwork_send_gate(blob) or "send pack" in blob.lower() else 2
            if src == "note":
                return 2
            if src == "inbound":
                return 1 if filled else 0
        if filled and is_inbound_item(cand):
            return 1
        return 0

    def _calendar_key(cand: Top3Candidate) -> tuple:
        """Soonest future grant date beats charter-token overlap ('grants')."""
        if not isinstance(cand, dict) or str(cand.get("kind") or "") != "grant":
            return (1, 10**9)
        open_n = 0 if cand.get("grant_open", True) else 1
        due_s = str(cand.get("grant_due") or "")[:10]
        if due_s:
            try:
                return (open_n, date.fromisoformat(due_s).toordinal())
            except ValueError:
                pass
        return (open_n, 10**9)

    def _exec_lane(cand: Top3Candidate) -> int:
        if isinstance(cand, dict):
            blob = " ".join(
                str(cand.get(k) or "")
                for k in ("grant_evidence", "title", "raw")
            )
        else:
            blob = _item_raw(cand)
        return _grant_exec_lane(blob, charter_txt=charter_txt)

    def _score(cand: Top3Candidate) -> tuple:
        low = _item_raw(cand).lower()
        hygiene = 1 if filled and not elevate_jobs and _JOB_HYGIENE.search(low) else 0
        inbound = _inbound_weight(cand)
        prosp = 1 if filled and _PROSPERITY.search(low) else 0
        overlap = len(set(re.findall(r"[a-z]{4,}", low)) & tokens) if filled else 0
        cal_open, cal_due = _calendar_key(cand)
        packet = 0 if _is_nomination_packet(cand) else 1
        return (
            hygiene,
            -inbound,
            cal_open,
            packet,
            _exec_lane(cand),
            cal_due,
            -prosp,
            -overlap,
        )

    uniq.sort(key=_score)
    ranked = as_top3_items(uniq[:limit])
    for idx, item in enumerate(ranked, start=1):
        item["rank"] = idx
    return ranked


def _prosperity_overdue(overdue: Iterable[Any]) -> List[str]:
    lines: List[str] = []
    for item in overdue or []:
        title = _title_of(item)
        if _PROSPERITY.search(title):
            lines.append(f"Close: {title}")
    return lines


def compose_ceo_brief_markdown(
    *,
    title: str,
    generated_at: str = "",
    events: Optional[List[Dict[str, Any]]] = None,
    due_soon: Optional[List[Dict[str, Any]]] = None,
    overdue: Optional[List[Dict[str, Any]]] = None,
    jobs: Optional[Dict[str, Any]] = None,
    handoffs: Optional[Dict[str, Any]] = None,
    research: Optional[List[Dict[str, Any]]] = None,
    runs: Optional[List[Dict[str, Any]]] = None,
    missed_tasks: Optional[List[Dict[str, Any]]] = None,
    harvest_flags: Optional[Dict[str, Any]] = None,
    next_run: Optional[Dict[str, Any]] = None,
    substrate_txt: str = "",
    research_txt: str = "",
    ledger_txt: str = "",
    notes: Optional[List[Dict[str, Any]]] = None,
    documents: Optional[List[Dict[str, Any]]] = None,
    charter_txt: str = "",
    inbound: Optional[Sequence[Top3Candidate]] = None,
    comms_preview: Optional[List[Dict[str, Any]]] = None,
    inbound_notes: Optional[List[Dict[str, Any]]] = None,
    inbound_docs: Optional[List[Dict[str, Any]]] = None,
    today: Optional[date] = None,
) -> str:
    """Compose the full-picture CEO brief (harvest dump + ranked Top 3)."""
    events = list(events or [])
    due_soon = list(due_soon or [])
    overdue = list(overdue or [])
    jobs = jobs or {}
    handoffs = handoffs or {}
    runs = list(runs or [])
    harvest_flags = harvest_flags or {}
    missed_tasks = list(missed_tasks or [])  # accepted, not a section of its own
    _ = research  # Rhizo dump comes from the Research Brief document excerpt

    substrate = (
        substrate_txt
        or str(harvest_flags.get("swarm_excerpt") or harvest_flags.get("substrate_txt") or "")
    ).strip()
    research_body = (
        research_txt
        or str(harvest_flags.get("research_excerpt") or harvest_flags.get("research_txt") or "")
    ).strip()
    ledger = _live_fruit_body(
        ledger_txt
        or str(harvest_flags.get("ledger_excerpt") or harvest_flags.get("ledger_txt") or "")
        or harvest_fruit_ledger_text(documents=documents, notes=notes)
    )
    charter = (
        charter_txt
        or str(harvest_flags.get("charter_txt") or harvest_flags.get("charter") or "")
    ).strip()

    na = list(handoffs.get("needs_attention") or [])
    ip = list(handoffs.get("in_progress") or [])

    when = (generated_at or "").strip()
    if when and "from the morning" in when.lower():
        gen_line = when if when.startswith("_") else f"_{when}_"
    elif when:
        gen_line = f"_Generated {when} from the morning chron wave._"
    else:
        gen_line = "_Generated from the morning chron wave._"

    md: List[str] = [f"# {title}", "", gen_line, "", "## Top 3 actions that move the needle"]
    swarm_top3 = _parse_numbered_top3(substrate)
    inbound_items: List[Top3Candidate] = list(inbound or [])
    if not inbound_items:
        inbound_items = collect_inbound_candidates(
            comms_preview=comms_preview,
            notes=inbound_notes,
            documents=inbound_docs,
            today=today,
        )
    for line in swarm_top3:
        if is_concrete_inbound_text(line):
            inbound_items.append({"title": _item_title(line), "raw": line, "source": "inbound"})
    filled = charter_is_filled(charter)
    use_job_fallback = (not filled) or charter_elevates_jobs(charter)
    fallback = (
        _fallback_top3(jobs=jobs, handoffs=handoffs, overdue=overdue)
        if use_job_fallback
        else []
    )
    candidates: List[Top3Candidate] = list(inbound_items)
    candidates.extend(swarm_top3)
    candidates.extend(charter_needles(charter))
    candidates.extend(_prosperity_overdue(overdue))
    candidates.extend(fallback)
    if not candidates:
        candidates = _fallback_top3(jobs=jobs, handoffs=handoffs, overdue=overdue)
    ranked_items = rank_money_candidates(candidates, charter)
    if ranked_items:
        for i, item in enumerate(ranked_items, start=1):
            md.append(f"{i}. {item.get('raw') or item.get('title')}")
    elif not substrate:
        md.append("_No Swarm Plan on the blackboard yet — Sporangium may not have run._")
    if substrate:
        md += ["From the Swarm Plan / blackboard (Sporangium):", "```", substrate, "```"]

    md += ["", "## Inbound opportunity"]
    email_n = sum(
        1
        for item in inbound_items
        if isinstance(item, dict) and item.get("source") == "email"
    )
    shown = 0
    seen_inbound: set[str] = set()
    for item in inbound_items:
        raw = _item_raw(item)
        key = re.sub(r"\s+", " ", raw.lower()).strip()
        if not raw or key in seen_inbound:
            continue
        seen_inbound.add(key)
        md.append(f"- {raw}")
        shown += 1
        if shown >= 3:
            break
    if email_n == 0:
        md.append(
            "_No tagged grant, proposal, invoice, or paid inbound in the inbox this scan._"
        )
    grant_n = sum(
        1
        for item in inbound_items
        if isinstance(item, dict) and item.get("kind") == "grant"
    )
    if grant_n == 0:
        md.append(_NO_GRANT_RFP_LINE)
    if shown == 0:
        md.append(
            "_No Upwork/NPR/proposal residue on file. Do not invent grants._"
        )

    md += ["", "## What's upcoming"]
    if events:
        md.append("Calendar (next 48h):")
        md.extend(f"- {e.get('start') or ''} — {_title_of(e, 'Event')}" for e in events)
    else:
        md.append("_Clear day._")
    if due_soon:
        md.append("Due soon:")
        md.extend(
            f"- {_title_of(d)}" + (f" ({d.get('due_date')})" if d.get("due_date") else "")
            for d in due_soon[:5]
        )
    if overdue:
        md.append("Overdue:")
        md.extend(
            f"- {_title_of(d)}" + (f" ({d.get('due_date')})" if d.get("due_date") else "")
            for d in overdue[:5]
        )
    if next_run:
        md.append(f"Next chron run: {next_run.get('name')} @ {next_run.get('next_run')}")

    md += ["", "## Job pipeline", jobs.get("headline") or "No job applications need attention."]
    for j in (jobs.get("ready_to_apply") or [])[:3]:
        md.append(f"- ready: {j.get('company') or '?'} — {j.get('role') or '?'}")
    for j in (jobs.get("needs_review") or [])[:3]:
        md.append(f"- review: {j.get('company') or '?'} — {j.get('role') or '?'}")

    md += ["", "## Handoffs in flight"]
    if not na and not ip:
        md.append("_None._")
    for h in na[:3]:
        md.append(f"- needs attention: {_title_of(h)} → {h.get('handoff_target') or '?'}")
    for h in ip[:3]:
        md.append(f"- in progress: {_title_of(h)} → {h.get('handoff_target') or '?'}")

    md += ["", "## Research findings (Rhizo)"]
    if research_body:
        md += ["```", research_body, "```"]
    else:
        md.append("_Rhizo hasn't filed a research brief today._")

    md += ["", "## Fruit ledger (Herald)"]
    if ledger:
        md += ["```", ledger, "```"]
    else:
        md.append("_No fruit ledger entry yet._")

    md += ["", "## Recent chron outputs"]
    listed = False
    for r in runs:
        if r.get("status") and classify_task_run(r) != "success":
            continue
        result = str(r.get("result") or "").strip()
        md.append(
            f"- **{_title_of(r, str(r.get('name') or 'cron'))}** ({r.get('at') or ''}) — {result}"
        )
        listed = True
    if not listed:
        md.append("_No successful chron runs in the recent window._")

    md.append("")
    return "\n".join(md)
