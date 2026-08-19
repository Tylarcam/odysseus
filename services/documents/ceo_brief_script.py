"""CEO Brief spoken-script contract (09:00 cron + vault BRIEF ME).

Sections, in order:
  Headline (one breath, Green/Amber/Red)
  What changed
  Needs you (P0–P3)
  Can wait

Cron TaskRuns appear only on fail / miss / timeout. Successful jobs collapse
to silence or one line. No verbatim swarm blackboard or doctrine paste.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

_TIMEOUT_MARKERS = ("timeout", "timed out", "timed-out")
_MISS_MARKERS = ("not ready", "missed", "harvest not ready")
_FAIL_STATUSES = {"error", "failed"}


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


def brief_traffic_light(
    *,
    overdue: Iterable[Any] = (),
    handoff_attention: int = 0,
    jobs_review: int = 0,
    exception_runs: Iterable[Any] = (),
    unfinished_research: bool = False,
) -> str:
    if list(overdue) or handoff_attention or list(exception_runs):
        return "Red"
    if jobs_review or unfinished_research:
        return "Amber"
    return "Green"


def _title_of(item: Any, fallback: str = "Untitled") -> str:
    if isinstance(item, dict):
        t = str(item.get("title") or item.get("name") or "").strip()
        if t:
            return t
    return fallback


def _clip(text: str, n: int = 160) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


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
) -> str:
    """Compose the CEO brief document in the spoken-script contract."""
    events = list(events or [])
    due_soon = list(due_soon or [])
    overdue = list(overdue or [])
    jobs = jobs or {}
    handoffs = handoffs or {}
    research = list(research or [])
    runs = list(runs or [])
    missed_tasks = list(missed_tasks or [])
    harvest_flags = harvest_flags or {}

    na = list(handoffs.get("needs_attention") or [])
    ip = list(handoffs.get("in_progress") or [])
    jobs_review = list(jobs.get("needs_review") or [])
    jobs_ready = list(jobs.get("ready_to_apply") or [])

    classified = [(r, classify_task_run(r)) for r in runs]
    exceptions = [(r, kind) for r, kind in classified if kind in ("failed", "timeout", "missed")]
    for task in missed_tasks:
        exceptions.append((task, "missed"))
    success_n = sum(1 for _, kind in classified if kind == "success")

    latest = research[0] if research else None
    unfinished = bool(latest and str(latest.get("status") or "done") != "done")
    fresh_done = bool(latest and str(latest.get("status") or "done") == "done")

    color = brief_traffic_light(
        overdue=overdue,
        handoff_attention=len(na),
        jobs_review=len(jobs_review),
        exception_runs=exceptions,
        unfinished_research=unfinished,
    )

    headline_bits: List[str] = []
    if overdue:
        headline_bits.append(
            f"{len(overdue)} overdue" if len(overdue) != 1 else "1 overdue"
        )
    if na:
        headline_bits.append(
            f"{len(na)} handoff{'s' if len(na) != 1 else ''} waiting"
        )
    if jobs_review:
        headline_bits.append(
            f"{len(jobs_review)} job{'s' if len(jobs_review) != 1 else ''} to review"
        )
    if exceptions:
        headline_bits.append(
            f"{len(exceptions)} cron exception{'s' if len(exceptions) != 1 else ''}"
        )
    if latest:
        headline_bits.append(f"latest research: {_clip(_title_of(latest, 'report'), 80)}")
    if not headline_bits:
        headline_bits.append("nothing needs you")
    headline = f"{color}. {'; '.join(headline_bits)}."

    md: List[str] = [f"# {title}", ""]
    if generated_at:
        md += [f"_Generated {generated_at}._", ""]
    md += ["## Headline", headline, ""]

    # --- What changed --------------------------------------------------------
    md.append("## What changed")
    changed: List[str] = []
    if latest:
        changed.append(f"- Research: **{_title_of(latest, 'Report')}**")
        for bullet in (latest.get("bullets") or [])[:3]:
            changed.append(f"  - {_clip(str(bullet), 180)}")
        if latest.get("url"):
            changed.append(f"  - Open: {latest['url']}")
    if events:
        changed.append("Calendar (next 48h):")
        for event in events[:6]:
            changed.append(
                f"- {event.get('start') or ''} — {_title_of(event, 'Event')}"
            )
    flags = []
    if harvest_flags.get("has_swarm_plan"):
        flags.append("swarm plan")
    if harvest_flags.get("has_research_brief_doc"):
        flags.append("Rhizo brief doc")
    if harvest_flags.get("has_ledger"):
        flags.append("fruit ledger")
    if flags:
        changed.append(f"- Mycelia harvest on file ({', '.join(flags)}) — not pasted.")
    if not changed:
        changed.append("- Quiet overnight — no new research or calendar items.")
    md.extend(changed)
    md.append("")

    # --- Needs you -----------------------------------------------------------
    md.append("## Needs you")
    needs: List[str] = []
    for item in overdue[:5]:
        needs.append(f"- **P0 / Red** — overdue: {_title_of(item)}")
    for h in na[:3]:
        target = h.get("handoff_target") or "?"
        needs.append(f"- **P0 / Red** — handoff: {_title_of(h)} → {target}")
    for r, kind in exceptions[:6]:
        name = _title_of(r, str(r.get("name") or "cron"))
        needs.append(f"- **P0 / Red** — cron {kind}: {name}")
    for j in jobs_review[:3]:
        needs.append(
            f"- **P1 / Amber** — review: {j.get('company') or '?'} — {j.get('role') or '?'}"
        )
    if unfinished and latest:
        needs.append(
            f"- **P1 / Amber** — unfinished research: {_title_of(latest, 'report')}"
        )
    elif fresh_done and latest:
        needs.append(
            f"- **P1 / Amber** — read latest research: {_title_of(latest, 'report')}"
        )
    for j in jobs_ready[:3]:
        needs.append(
            f"- **P2** — ready to apply: {j.get('company') or '?'} — {j.get('role') or '?'}"
        )
    if not needs:
        needs.append("- Nothing blocking. Deck is clear.")
    md.extend(needs)
    md.append("")

    # --- Can wait ------------------------------------------------------------
    md.append("## Can wait")
    waiting: List[str] = []
    for item in due_soon[:5]:
        waiting.append(
            f"- Due soon: {_title_of(item)}"
            + (f" ({item.get('due_date')})" if item.get("due_date") else "")
        )
    for h in ip[:3]:
        waiting.append(
            f"- Handoff in flight: {_title_of(h)} → {h.get('handoff_target') or '?'}"
        )
    if exceptions:
        pass
    elif success_n:
        waiting.append("- Chron jobs ran green — not listed.")
    if not waiting:
        waiting.append("- Nothing parked.")
    md.extend(waiting)
    md.append("")
    return "\n".join(md)
