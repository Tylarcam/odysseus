"""CEO brief must not race the morning swarm harvest (P0#3 / eb3d2499).

Invariant: default cron is after Rhizo (08:30); scheduled runs defer when
today's Swarm Plan / Research Brief are still missing before the soft deadline.
"""

from datetime import datetime

from src.builtin_actions import (
    CEO_BRIEF_HARVEST_SOFT_DEADLINE_HOUR,
    ceo_brief_morning_harvest_ready,
)
from src.task_scheduler import HOUSEKEEPING_DEFAULTS
from services.documents.ceo_brief_store import select_ceo_brief
from services.home.cmd_center import build_cmd_center


def test_ceo_brief_cron_after_morning_harvest_wave():
    defs = HOUSEKEEPING_DEFAULTS["ceo_brief"]
    assert defs["cron_expression"] == "0 9 * * *"
    assert "30 7 * * *" in (defs.get("old_cron_expressions") or [])


def test_harvest_gate_defers_when_empty_before_deadline():
    ready, reason = ceo_brief_morning_harvest_ready(
        has_swarm_plan_today=False,
        has_research_brief_today=False,
        local_hour=CEO_BRIEF_HARVEST_SOFT_DEADLINE_HOUR - 1,
    )
    assert ready is False
    assert "not ready" in reason


def test_harvest_gate_ready_when_plan_present():
    ready, reason = ceo_brief_morning_harvest_ready(
        has_swarm_plan_today=True,
        has_research_brief_today=False,
        local_hour=9,
    )
    assert ready is True
    assert "present" in reason


def test_harvest_gate_ready_at_soft_deadline_even_if_empty():
    ready, reason = ceo_brief_morning_harvest_ready(
        has_swarm_plan_today=False,
        has_research_brief_today=False,
        local_hour=CEO_BRIEF_HARVEST_SOFT_DEADLINE_HOUR,
    )
    assert ready is True
    assert "soft deadline" in reason


def test_select_ceo_brief_prefers_today_uuid_title_over_legacy_id():
    now = datetime(2026, 8, 15, 12, 0, 0)
    uuid_id = "50410d5b-2dab-4341-95af-c97d5a639572"
    docs = [
        {
            "id": "ceo-brief-2026-08-09",
            "title": "CEO Brief — 2026-08-09",
            "content": "old",
            "updated_at": "2026-08-09T09:00:00",
        },
        {
            "id": uuid_id,
            "title": "CEO Brief — 2026-08-15",
            "content": "# Today\nNeedle.",
            "updated_at": "2026-08-15T08:00:00",
        },
    ]
    snap = select_ceo_brief(docs, now=now)
    assert snap["id"] == uuid_id
    assert snap["status"] == "ready"
    assert snap["is_today"] is True
    assert snap["stale"] is False
    assert "Needle" in snap["content"]


def test_select_ceo_brief_marks_yesterday_stale():
    now = datetime(2026, 8, 15, 12, 0, 0)
    snap = select_ceo_brief(
        [{
            "id": "ceo-brief-2026-08-14",
            "title": "CEO Brief — 2026-08-14",
            "content": "yesterday",
            "updated_at": "2026-08-14T09:00:00",
        }],
        now=now,
    )
    assert snap["status"] == "stale"
    assert snap["is_today"] is False
    assert snap["stale"] is True


def test_cmd_center_payload_includes_uuid_ceo_brief():
    from services.documents.ceo_brief_store import date_label
    today = date_label()
    uuid_id = "50410d5b-2dab-4341-95af-c97d5a639572"
    data = build_cmd_center(
        notes=[],
        documents=[{
            "id": uuid_id,
            "title": f"CEO Brief — {today}",
            "content": "# CEO Brief\nToday.",
            "language": "markdown",
            "archived": False,
            "updated_at": datetime.now().isoformat(),
        }],
        tasks=[],
        sessions=[],
        include_globe=False,
    )
    brief = data["ceo_brief"]
    assert brief["id"] == uuid_id
    assert brief["status"] == "ready"
    card = next(c for c in data["stage_cards"] if c["id"] == "ceo_brief")
    assert card["target_id"] == uuid_id
