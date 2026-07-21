"""CEO brief must not race the morning swarm harvest (P0#3 / eb3d2499).

Invariant: default cron is after Rhizo (08:30); scheduled runs defer when
today's Swarm Plan / Research Brief are still missing before the soft deadline.
"""

from src.builtin_actions import (
    CEO_BRIEF_HARVEST_SOFT_DEADLINE_HOUR,
    ceo_brief_morning_harvest_ready,
)
from src.task_scheduler import HOUSEKEEPING_DEFAULTS


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
