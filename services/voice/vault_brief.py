#!/usr/bin/env python3
"""Compact vault briefing for Jarvis / Realtime voice sessions.

Injected as system context (≤2k chars) so voice knows Relay/Agency/hero
state without dumping the full CMD Center payload.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_BRIEF_CHARS = 2000
MAX_PRIORITY = 3
MAX_MEMORY = 5


def _clip(text: str, n: int = 120) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


# Branch ids → Domain labels for BRIEF ME highlight payloads (hq-openapi BriefLine).
_DOMAIN_BY_BRANCH = {
    "core": "CORE",
    "mem": "MEM",
    "prod": "PROD",
    "comms": "COMMS",
    "agency": "AGENCY",
    "relay": "RELAY",
    "mycelia": "MYCELIA",
    "intel": "COMMS",
    "chat": "CORE",
    "voice": "CORE",
}


def _domain_label(branch: Optional[str]) -> str:
    key = str(branch or "").strip().lower()
    if key in _DOMAIN_BY_BRANCH:
        return _DOMAIN_BY_BRANCH[key]
    upper = str(branch or "").strip().upper()
    if upper in ("CORE", "MEM", "PROD", "COMMS", "AGENCY", "RELAY", "MYCELIA"):
        return upper
    return "PROD"


def _hl_overdue() -> Dict[str, Any]:
    return {"type": "overdue"}


def _hl_domain(branch: Optional[str]) -> Dict[str, Any]:
    return {"type": "domain", "domain": _domain_label(branch)}


def _hl_all() -> Dict[str, Any]:
    return {"type": "all"}


def _speech_num(n: int, singular: str, plural: str) -> str:
    if n == 1:
        return f"1 {singular}"
    return f"{n} {plural}"


def _speech_overdue_age(days: Optional[int]) -> str:
    if days is None:
        return ""
    try:
        d = int(days)
    except (TypeError, ValueError):
        return ""
    if d <= 0:
        return "due earlier today"
    if d == 1:
        return "one day overdue"
    return f"{d} days overdue"


def _speech_when_future(iso_or_dt: Any) -> str:
    """Relative future phrase for speech — never an ISO timestamp."""
    from datetime import datetime, timezone

    if iso_or_dt is None:
        return ""
    if isinstance(iso_or_dt, datetime):
        dt = iso_or_dt
    else:
        raw = str(iso_or_dt).strip()
        if not raw:
            return ""
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    seconds = (dt - now).total_seconds()
    if seconds < 0:
        return "already started"
    if seconds < 60:
        return "in under a minute"
    if seconds < 3600:
        mins = max(1, int(seconds // 60))
        return f"in {mins} minute{'s' if mins != 1 else ''}"
    if seconds < 86400:
        hours = max(1, int(seconds // 3600))
        return f"in about {hours} hour{'s' if hours != 1 else ''}"
    days = max(1, int(seconds // 86400))
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


_ISO_BIT = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?"
)
_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_BULLET = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$")


def _speech_plain(text: str, n: int = 90) -> str:
    t = (text or "").strip().replace("\n", " ")
    t = t.replace("**", "").replace("__", "").replace("`", "")
    t = _ISO_BIT.sub("", t)
    t = re.sub(r"\s+", " ", t).strip(" \t-—,.")
    return _clip(t, n)


def _is_placeholder(text: str) -> bool:
    low = (text or "").strip().lower().strip("_* ")
    if not low:
        return True
    return any(
        p in low
        for p in (
            "clear day",
            "_none",
            "none.",
            "no job applications",
            "hasn't filed",
            "no fruit ledger",
            "no successful chron",
            "sporangium may not",
            "from the swarm plan",
        )
    )


def _h2_map(content: str) -> Dict[str, str]:
    text = content or ""
    matches = list(_H2.finditer(text))
    out: Dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[m.group(1).strip().lower()] = text[start:end].strip()
    return out


def _section_body(content: str, needle: str) -> str:
    key = (needle or "").lower()
    for heading, body in _h2_map(content).items():
        if key in heading:
            return body
    return ""


def _parse_top3_items(content: str) -> List[Dict[str, str]]:
    if not (content or "").strip():
        return []
    try:
        from services.home.mycelia_feed import parse_top3

        return list(parse_top3(content) or [])
    except Exception:  # pragma: no cover - parser is local and stable
        return []


def _ranked_top3(
    money_hero: Optional[Dict[str, Any]],
    content: str,
) -> List[Dict[str, str]]:
    mh = money_hero or {}
    ranked = mh.get("ranked_top3") or []
    if isinstance(ranked, list) and ranked:
        out: List[Dict[str, str]] = []
        for item in ranked[:3]:
            if isinstance(item, dict) and (item.get("title") or item.get("raw")):
                out.append(item)
            elif isinstance(item, str) and item.strip():
                out.append({"title": item.strip(), "raw": item.strip(), "rationale": ""})
        if out:
            return out
    return _parse_top3_items(content)


def _upcoming_need_and_wait(body: str) -> tuple[List[str], List[str]]:
    need: List[str] = []
    wait: List[str] = []
    bucket = "wait"
    cleaned = re.sub(r"```.*?```", " ", body or "", flags=re.DOTALL)
    for raw_line in cleaned.splitlines():
        low = raw_line.strip().lower()
        if low.startswith("overdue"):
            bucket = "need"
            continue
        if low.startswith("due soon") or low.startswith("calendar") or low.startswith("next chron"):
            bucket = "wait"
            continue
        m = _BULLET.match(raw_line)
        if not m:
            continue
        title = _speech_plain(m.group(1), 80)
        if not title or _is_placeholder(title):
            continue
        (need if bucket == "need" else wait).append(title)
    return need, wait


def _labeled_bullets(body: str, *, need_prefix: str, wait_prefix: str) -> tuple[List[str], List[str]]:
    need: List[str] = []
    wait: List[str] = []
    cleaned = re.sub(r"```.*?```", " ", body or "", flags=re.DOTALL)
    if _is_placeholder(cleaned[:80]):
        return need, wait
    for raw_line in cleaned.splitlines():
        m = _BULLET.match(raw_line)
        if not m:
            continue
        title = _speech_plain(m.group(1), 80)
        if not title or _is_placeholder(title):
            continue
        low = title.lower()
        if need_prefix and low.startswith(need_prefix):
            need.append(_speech_plain(title.split(":", 1)[-1], 80) or title)
        elif wait_prefix and low.startswith(wait_prefix):
            wait.append(_speech_plain(title.split(":", 1)[-1], 80) or title)
        else:
            need.append(title)
    return need, wait


def _dedupe(items: List[str], seen: Optional[set] = None) -> List[str]:
    out: List[str] = []
    have = seen if seen is not None else set()
    for item in items:
        key = item.lower()
        if not item or key in have:
            continue
        have.add(key)
        out.append(item)
    return out


def _fruit_ledger_empty(body: str) -> bool:
    blob = (body or "").strip()
    if not blob:
        return True
    return _is_placeholder(blob[:120])


def _fruit_speech_line(money_hero: Optional[Dict[str, Any]], fruit_body: str) -> str:
    """Count + last fruit when present; honest empty line when empty."""
    mh = money_hero or {}
    count_n = 0
    try:
        count_n = int(mh.get("fruit_count") or 0)
    except (TypeError, ValueError):
        count_n = 0
    last = _speech_plain(str(mh.get("last_fruit") or ""), 90)
    if "invent fruit" in last.lower():
        last = ""
    if count_n <= 0 or not last:
        try:
            from services.home.mycelia_feed import parse_fruit_ledger

            parsed = parse_fruit_ledger(fruit_body or "")
            count_n = int(parsed.get("fruit_count") or 0)
            last = _speech_plain(str(parsed.get("last_fruit") or ""), 90)
        except Exception:
            pass
    if count_n > 0 and last:
        noun = "fruit" if count_n == 1 else "fruits"
        return f"{count_n} {noun} on the ledger. Last: {last}."
    if _fruit_ledger_empty(fruit_body):
        return "Fruit ledger is empty — don't invent fruit."
    return ""


def _executable_target_line(money_hero: Optional[Dict[str, Any]]) -> str:
    """Name pack vs NPR draft id so BRIEF ME has a next executable, not just a slogan."""
    mh = money_hero or {}
    act = str(mh.get("action") or "").strip()
    tid = str(mh.get("target_id") or "").strip()
    title = str(mh.get("title") or "")
    low = title.lower()
    id8 = tid[:8]
    if not id8:
        return ""
    if act == "open_doc" or "send pack" in low or "upwork" in low:
        return f"Next executable: send pack {id8}."
    if act == "open_note" or "npr" in low:
        return f"Next executable: NPR draft {id8}."
    if act == "email":
        return f"Next executable: email {id8}."
    return f"Next executable: {id8}."


def _harvest_script(
    *,
    money_hero: Optional[Dict[str, Any]],
    ceo_brief: Optional[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    """BRIEF ME rundown from today's CEO Brief harvest — not the HUD if-chain."""
    brief = ceo_brief or {}
    content = str(brief.get("content") or "")
    top3 = _ranked_top3(money_hero, content)
    if not top3:
        return None

    mh = money_hero or {}
    first = top3[0]
    first_title = _speech_plain(str(first.get("title") or first.get("raw") or "Top money move"), 90)
    headline = _speech_plain(str(mh.get("spoken_needle") or mh.get("true_line") or ""), 140)
    if not headline:
        headline = f"Top money move: {first_title}."
    if headline[-1] not in ".!?":
        headline += "."

    titles = [
        _speech_plain(str(item.get("title") or item.get("raw") or ""), 70)
        for item in top3
    ]
    titles = [t for t in titles if t]

    upcoming_need, upcoming_wait = _upcoming_need_and_wait(_section_body(content, "upcoming"))
    jobs_body = _section_body(content, "job pipeline")
    jobs_need = _section_bullets_prefixed(jobs_body, "ready") + _section_bullets_prefixed(
        jobs_body, "review"
    )
    handoff_need, handoff_wait = _labeled_bullets(
        _section_body(content, "handoffs"),
        need_prefix="needs attention",
        wait_prefix="in progress",
    )

    need_bits = _dedupe([first_title] + upcoming_need + jobs_need + handoff_need)
    wait_bits = _dedupe(titles[1:] + upcoming_wait + handoff_wait, {b.lower() for b in need_bits})

    lines: List[Dict[str, Any]] = [
        {"text": headline, "highlight": _hl_domain("prod")},
    ]
    exec_line = _executable_target_line(mh)
    if exec_line:
        lines.append({"text": exec_line, "highlight": _hl_domain("prod")})
    if titles:
        numbered = "; ".join(f"{i}) {t}" for i, t in enumerate(titles, 1))
        lines.append(
            {
                "text": f"Top 3: {numbered}.",
                "highlight": _hl_domain("prod"),
            }
        )
    if need_bits:
        lines.append(
            {
                "text": "Needs you: " + "; ".join(need_bits[:3]) + ".",
                "highlight": _hl_overdue() if upcoming_need else _hl_domain("prod"),
            }
        )
    if wait_bits and len(lines) < 5:
        lines.append(
            {
                "text": "Can wait: " + "; ".join(wait_bits[:3]) + ".",
                "highlight": _hl_domain("comms"),
            }
        )
    fruit_body = _section_body(content, "fruit")
    fruit_line = _fruit_speech_line(mh, fruit_body)
    if fruit_line:
        if "don't invent fruit" in fruit_line.lower() or "do not invent fruit" in fruit_line.lower():
            if len(lines) < 6:
                lines.append({"text": fruit_line, "highlight": _hl_domain("mem")})
        else:
            # Prosperity scoreboard outranks "can wait" when fruit exists.
            if len(lines) >= 6:
                lines[-1] = {"text": fruit_line, "highlight": _hl_domain("mem")}
            else:
                lines.append({"text": fruit_line, "highlight": _hl_domain("mem")})
    if len(lines) < 6:
        lines.append({"text": "That's the state of the V.A.U.L.T.", "highlight": _hl_all()})
    while len(lines) < 3:
        lines.append({"text": "Vault standing by.", "highlight": _hl_all()})
    return lines[:6]


def _section_bullets_prefixed(body: str, prefix: str) -> List[str]:
    out: List[str] = []
    cleaned = re.sub(r"```.*?```", " ", body or "", flags=re.DOTALL)
    for raw_line in cleaned.splitlines():
        m = _BULLET.match(raw_line)
        if not m:
            continue
        title = _speech_plain(m.group(1), 80)
        if title and title.lower().startswith(prefix):
            out.append(_speech_plain(title.split(":", 1)[-1], 80) or title)
    return out


def build_brief_script(
    *,
    hero: Optional[Dict[str, Any]] = None,
    priority_queue: Optional[List[Dict[str, Any]]] = None,
    counts: Optional[Dict[str, Any]] = None,
    agenda: Optional[Dict[str, Any]] = None,
    overdue_count: Optional[int] = None,
    research: Optional[List[Dict[str, Any]]] = None,
    failed_runs: Optional[List[Dict[str, Any]]] = None,
    jobs: Optional[Dict[str, Any]] = None,
    handoffs: Optional[Dict[str, Any]] = None,
    money_hero: Optional[Dict[str, Any]] = None,
    ceo_brief: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Build a 3–6 line BRIEF ME script.

    When today's CEO Brief has a Top 3 harvest, narrate that ranking
    (headline · Top 3 · Needs you · Can wait). Otherwise keep the HUD
    if-chain (overdue / research / directives hero).
    Speech-friendly: no ISO dates.
    """
    harvest = _harvest_script(money_hero=money_hero, ceo_brief=ceo_brief)
    if harvest:
        return harvest

    hero = hero or {}
    priority_queue = list(priority_queue or [])
    counts = counts or {}
    agenda = agenda or {}
    research = list(research or [])
    failed_runs = list(failed_runs or [])
    jobs = jobs or {}
    handoffs = handoffs or {}

    queue_overdue = sum(1 for i in priority_queue if i.get("status") == "overdue")
    agenda_overdue = len(agenda.get("overdue") or [])
    if overdue_count is None:
        overdue_n = max(queue_overdue, agenda_overdue)
        hero_unit = str(hero.get("unit") or "").upper()
        if hero_unit == "OVERDUE":
            try:
                overdue_n = max(overdue_n, int(hero.get("value") or 0))
            except (TypeError, ValueError):
                pass
    else:
        try:
            overdue_n = max(0, int(overdue_count))
        except (TypeError, ValueError):
            overdue_n = max(queue_overdue, agenda_overdue)

    inflight = 0
    for key in ("handoffs_in_progress", "agents_inflight", "in_progress"):
        if counts.get(key) is not None:
            try:
                inflight = max(inflight, int(counts.get(key) or 0))
            except (TypeError, ValueError):
                pass

    jobs_review = 0
    try:
        jobs_review = int(counts.get("jobs_review") or jobs.get("needs_review_count") or 0)
    except (TypeError, ValueError):
        jobs_review = 0
    handoff_wait = 0
    try:
        handoff_wait = int(
            counts.get("handoffs_attention")
            or len(handoffs.get("needs_attention") or [])
            or 0
        )
    except (TypeError, ValueError):
        handoff_wait = 0

    latest = research[0] if research else None
    latest_title = _clip(str((latest or {}).get("title") or (latest or {}).get("query") or ""), 80)
    color = "Red" if (overdue_n or failed_runs or handoff_wait) else (
        "Amber" if jobs_review or (
            latest and str((latest or {}).get("status") or "done") != "done"
        ) else "Green"
    )

    lines: List[Dict[str, Any]] = []

    # 1 — Headline (one breath)
    if overdue_n > 0:
        extra = f" Latest research: {latest_title}." if latest_title else ""
        lines.append(
            {
                "text": (
                    f"{color}. {_speech_num(overdue_n, 'item needs', 'items need')} "
                    f"your attention — overdue.{extra}"
                ),
                "highlight": _hl_overdue(),
            }
        )
    elif failed_runs:
        fail_name = _clip(str(failed_runs[0].get("task_name") or failed_runs[0].get("name") or "a job"), 60)
        extra = f" Latest research: {latest_title}." if latest_title else ""
        lines.append(
            {
                "text": f"{color}. Chron exception: {fail_name} failed.{extra}",
                "highlight": _hl_domain("prod"),
            }
        )
    elif latest_title:
        lines.append(
            {
                "text": f"{color}. Latest research: {latest_title}.",
                "highlight": _hl_domain("mem"),
            }
        )
    else:
        lines.append(
            {
                "text": f"{color}. Nothing is overdue — the deck looks clear.",
                "highlight": _hl_all(),
            }
        )

    # 2 — What changed (research + inflight; collapse all-green cron)
    changed_bits: List[str] = []
    if latest_title:
        changed_bits.append(f"Research: {latest_title}")
    if inflight > 0:
        changed_bits.append(
            f"{_speech_num(inflight, 'agent is', 'agents are')} in flight on the relay"
        )
    if failed_runs and overdue_n > 0:
        fail_name = _clip(str(failed_runs[0].get("task_name") or failed_runs[0].get("name") or "a job"), 50)
        changed_bits.append(f"{fail_name} failed")
    if changed_bits:
        lines.append(
            {
                "text": "What changed: " + "; ".join(changed_bits) + ".",
                "highlight": _hl_domain("mem" if latest_title else ("relay" if inflight else "prod")),
            }
        )

    # 3 — Needs you
    top = priority_queue[0] if priority_queue else None
    need_bits: List[str] = []
    if top:
        title = _clip(str(top.get("title") or top.get("label") or "priority item"), 90)
        age = _speech_overdue_age(top.get("overdue_days"))
        if top.get("status") == "overdue" and age:
            need_bits.append(f"{title}, {age}")
        else:
            need_bits.append(title)
    elif hero.get("title"):
        need_bits.append(_clip(str(hero.get("title")), 90))
    if jobs_review:
        need_bits.append(_speech_num(jobs_review, "job to review", "jobs to review"))
    if latest_title and str((latest or {}).get("status") or "done") != "done":
        need_bits.append(f"unfinished research {latest_title}")
    if need_bits:
        hl = _hl_overdue() if (top and top.get("status") == "overdue") else _hl_domain(
            str((top or {}).get("branch") or hero.get("branch") or "prod")
        )
        lines.append(
            {
                "text": "Needs you: " + "; ".join(need_bits[:3]) + ".",
                "highlight": hl,
            }
        )

    # 4 — Can wait (calendar / due soon). Skip green-zero inflight noise.
    next_event = agenda.get("next_event") or {}
    if next_event.get("title"):
        when = _speech_when_future(next_event.get("start"))
        title = _clip(str(next_event.get("title")), 80)
        when_bit = f" {when}" if when else ""
        lines.append(
            {
                "text": f"Can wait: calendar — {title}{when_bit}.",
                "highlight": _hl_domain("comms"),
            }
        )
    else:
        due_soon = (agenda.get("due_soon") or [])[:1]
        if due_soon:
            item = due_soon[0]
            title = _clip(str(item.get("title") or "reminder"), 80)
            when = _speech_when_future(item.get("due_date"))
            when_bit = f" — {when}" if when else ""
            lines.append(
                {
                    "text": f"Can wait: {title}{when_bit}.",
                    "highlight": _hl_domain("prod"),
                }
            )

    # 5 — close (always, if room)
    if len(lines) < 6:
        lines.append(
            {
                "text": "That's the state of the V.A.U.L.T.",
                "highlight": _hl_all(),
            }
        )

    # Clamp 3–6 (pad if somehow short).
    while len(lines) < 3:
        lines.append(
            {
                "text": "Vault standing by.",
                "highlight": _hl_all(),
            }
        )
    return lines[:6]


def format_vault_brief(
    *,
    hero: Optional[Dict[str, Any]] = None,
    priority_queue: Optional[List[Dict[str, Any]]] = None,
    counts: Optional[Dict[str, Any]] = None,
    branch_health: Optional[List[Dict[str, Any]]] = None,
    pinned_facts: Optional[List[str]] = None,
    open_note_id: Optional[str] = None,
    money_hero: Optional[Dict[str, Any]] = None,
    ceo_brief: Optional[Dict[str, Any]] = None,
) -> str:
    """Render a speech-friendly markdown vault brief."""
    hero = hero or {}
    money_hero = money_hero or {}
    ceo_brief = ceo_brief or {}
    priority_queue = priority_queue or []
    counts = counts or {}
    branch_health = branch_health or []
    pinned_facts = pinned_facts or []

    lines: List[str] = [
        "# Vault brief (live CMD Center)",
        "",
        "You are Jarvis for Odysseus. Use this snapshot to answer "
        "'what's on fire' / status questions. Prefer tools or agent mode "
        "for actions. Keep spoken answers short. On Money Move, speak the "
        "money needle and Top 3 — not the HUD inventory hero.",
        "",
    ]

    title = _clip(str(hero.get("title") or "No primary directive"), 160)
    label = _clip(str(hero.get("label") or "Hero"), 80)
    explain = _clip(str(hero.get("explain") or ""), 160)
    lines.append(f"## Primary directive — {label}")
    lines.append(f"- {title}")
    if explain:
        lines.append(f"- {explain}")
    if hero.get("cta_label"):
        lines.append(f"- Suggested action: {_clip(str(hero.get('cta_label')), 80)}")
    lines.append("")

    mh_line = _speech_plain(
        str(money_hero.get("spoken_needle") or money_hero.get("true_line") or money_hero.get("title") or ""),
        160,
    )
    top3 = _ranked_top3(money_hero, str(ceo_brief.get("content") or ""))
    if mh_line:
        lines.append("## Money needle (Money Move)")
        lines.append(f"- {mh_line}")
        fruit_spoken = _fruit_speech_line(
            money_hero,
            _section_body(str(ceo_brief.get("content") or ""), "fruit"),
        )
        if fruit_spoken:
            lines.append(f"- {fruit_spoken}")
        lines.append("")
    if top3:
        lines.append("## Today's Top 3 (CEO Brief harvest)")
        for i, item in enumerate(top3, 1):
            item_title = _speech_plain(str(item.get("title") or item.get("raw") or "item"), 100)
            lines.append(f"{i}. {item_title}")
        lines.append("")

    # Branch snapshot (Relay / Agency / Voice matter most for Jarvis)
    interesting = {
        b.get("id"): b
        for b in branch_health
        if b.get("id") in ("relay", "agency", "voice", "prod", "mycelia", "mem")
    }
    if interesting:
        lines.append("## Branch health")
        for key in ("relay", "agency", "voice", "prod", "mycelia", "mem"):
            b = interesting.get(key)
            if not b:
                continue
            lines.append(
                f"- {b.get('label') or key}: {b.get('state')} — "
                f"{_clip(str(b.get('summary') or ''), 100)}"
            )
        lines.append("")

    if counts:
        lines.append("## Counts")
        lines.append(
            "- "
            + ", ".join(
                f"{k}={v}"
                for k, v in (
                    ("handoffs_waiting", counts.get("handoffs_attention")),
                    ("handoffs_inflight", counts.get("handoffs_in_progress")),
                    ("jobs_ready", counts.get("jobs_ready")),
                    ("jobs_review", counts.get("jobs_review")),
                    ("notes", counts.get("notes")),
                    ("tasks", counts.get("tasks")),
                )
                if v is not None
            )
        )
        lines.append("")

    top = priority_queue[:MAX_PRIORITY]
    if top:
        lines.append("## Top priority")
        for i, item in enumerate(top, 1):
            lines.append(
                f"{i}. {_clip(str(item.get('title') or item.get('label') or 'item'), 100)}"
                + (f" [{item.get('kind')}]" if item.get("kind") else "")
            )
        lines.append("")

    facts = [f for f in pinned_facts if (f or "").strip()][:MAX_MEMORY]
    if facts:
        lines.append("## Pinned memory (use naturally, don't recite)")
        for f in facts:
            lines.append(f"- {_clip(f, 140)}")
        lines.append("")

    if open_note_id:
        lines.append(f"Open note id: {open_note_id}")
        lines.append("")

    text = "\n".join(lines).strip() + "\n"
    if len(text) > MAX_BRIEF_CHARS:
        text = text[: MAX_BRIEF_CHARS - 1] + "…\n"
    return text


def build_vault_brief(owner: Optional[str] = None) -> Dict[str, Any]:
    """Assemble a live vault brief for the given owner (best-effort)."""
    from services.voice.realtime_gateway import _load_pinned_memory_facts

    pinned = _load_pinned_memory_facts(owner)
    hero: Dict[str, Any] = {}
    money_hero: Dict[str, Any] = {}
    ceo_brief: Dict[str, Any] = {}
    priority_queue: List[Dict[str, Any]] = []
    counts: Dict[str, Any] = {}
    branch_health: List[Dict[str, Any]] = []

    try:
        payload = _load_cmd_snapshot(owner)
        hero = payload.get("hero") or {}
        money_hero = payload.get("money_hero") or {}
        ceo_brief = payload.get("ceo_brief") or {}
        priority_queue = payload.get("priority_queue") or []
        counts = payload.get("counts") or {}
        branch_health = payload.get("branch_health") or []
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("vault_brief: cmd snapshot failed: %s", e)
        # Minimal fallback from jobs only
        try:
            from src.job_pipeline.brief import get_jobs_for_brief

            jobs = get_jobs_for_brief(owner=owner)
            counts = {
                "jobs_ready": jobs.get("ready_to_apply_count") or 0,
                "jobs_review": jobs.get("needs_review_count") or 0,
            }
            hero = {
                "label": "Agency",
                "title": jobs.get("headline") or "Job pipeline",
                "explain": f"{counts['jobs_ready']} ready · {counts['jobs_review']} review",
            }
        except Exception as e2:  # pragma: no cover
            logger.warning("vault_brief: jobs fallback failed: %s", e2)

    markdown = format_vault_brief(
        hero=hero,
        money_hero=money_hero,
        ceo_brief=ceo_brief,
        priority_queue=priority_queue,
        counts=counts,
        branch_health=branch_health,
        pinned_facts=pinned,
    )
    return {
        "markdown": markdown,
        "chars": len(markdown),
        "owner": owner or "anonymous",
        "hero_title": (hero.get("title") or "")[:160],
        "pinned_count": len(pinned[:MAX_MEMORY]),
    }


def _load_cmd_snapshot(owner: Optional[str]) -> Dict[str, Any]:
    """Reuse CMD Center builder with a trimmed DB fetch (same shape as HUD)."""
    from sqlalchemy import func

    from core.database import Document, Note, ScheduledTask, Session as DbSession, SessionLocal
    from core.database import get_upcoming_events
    from routes.document_helpers import _owner_session_filter
    from routes.home_routes import _note_row_to_cmd
    from services.home.cmd_center import build_cmd_center
    from src.auth_helpers import owner_filter
    from src.handoff_bin import bucket_handoff_notes
    from src.job_pipeline.brief import get_jobs_for_brief

    user = owner
    db = SessionLocal()
    try:
        note_q = db.query(Note).filter(Note.archived == False)  # noqa: E712
        if user:
            note_q = owner_filter(note_q, Note, user)
        notes = [_note_row_to_cmd(n) for n in note_q.order_by(Note.updated_at.desc()).limit(80).all()]

        doc_q = (
            db.query(Document)
            .outerjoin(DbSession, Document.session_id == DbSession.id)
            .filter(Document.is_active == True)  # noqa: E712
            .filter((Document.archived == False) | (Document.archived.is_(None)))  # noqa: E712
        )
        doc_q = _owner_session_filter(doc_q, user)
        documents = [
            {
                "id": doc.id,
                "title": doc.title,
                "content": (doc.current_content or "")[:4000],
                "language": doc.language,
                "archived": bool(doc.archived),
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
            for doc in doc_q.order_by(Document.updated_at.desc()).limit(40).all()
        ]

        task_q = db.query(ScheduledTask)
        if user:
            task_q = task_q.filter(ScheduledTask.owner == user)
        tasks = [
            {
                "id": t.id,
                "name": t.name,
                "prompt": (t.prompt or "")[:200],
                "status": t.status,
                "schedule": t.schedule,
                "next_run": t.next_run.isoformat() if t.next_run else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in task_q.order_by(ScheduledTask.updated_at.desc()).limit(40).all()
        ]

        sess_q = db.query(DbSession).filter(DbSession.archived == False)  # noqa: E712
        if user:
            sess_q = owner_filter(sess_q, DbSession, user)
        activity = func.coalesce(DbSession.last_message_at, DbSession.updated_at, DbSession.created_at)
        sessions = [
            {
                "id": s.id,
                "title": (s.name or "").strip() or "Untitled chat",
                "last_message_at": (
                    (s.last_message_at or s.updated_at or s.created_at).isoformat()
                    if (s.last_message_at or s.updated_at or s.created_at)
                    else None
                ),
            }
            for s in sess_q.filter(DbSession.message_count > 0).order_by(activity.desc()).limit(12).all()
        ]

        handoff_q = db.query(Note).filter(Note.handoff_doc_id.isnot(None))
        if user:
            handoff_q = owner_filter(handoff_q, Note, user)
        handoffs = bucket_handoff_notes(
            [_note_row_to_cmd(n) for n in handoff_q.order_by(Note.updated_at.desc()).limit(40).all()]
        )

        jobs = get_jobs_for_brief(owner=user)
        calendar_events = get_upcoming_events(owner=user, horizon_days=7, limit=10)

        return build_cmd_center(
            notes=notes,
            documents=documents,
            tasks=tasks,
            sessions=sessions,
            handoffs=handoffs,
            jobs=jobs,
            calendar_events=calendar_events,
        )
    finally:
        db.close()
