"""RELAY tab: relay_board buckets + relay_stats close-rate (phase 7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from services.home.cmd_center import (
    _build_relay_board,
    _build_relay_stats,
    build_cmd_center,
)
from services.home.stalled import STALLED_SLA

NOW = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)


def _h(**kwargs):
    base = {
        "id": "h1",
        "title": "Handoff",
        "handoff_doc_id": "d1",
        "handoff_target": "cursor",
        "handoff_at": NOW.isoformat(),
        "handoff_relay_status": "queued",
    }
    base.update(kwargs)
    return base


def test_relay_board_separates_claimed_stuck_from_needs_attention():
    hours = STALLED_SLA["handoff_claimed_stuck_hours"]
    waiting = _h(id="h-wait", handoff_relay_status="queued")
    fresh_run = _h(
        id="h-fresh",
        handoff_relay_status="running",
        handoff_relay_started_at=(NOW - timedelta(hours=1)).isoformat(),
    )
    stuck = _h(
        id="h-stuck",
        handoff_relay_status="running",
        handoff_relay_started_at=(NOW - timedelta(hours=hours + 2)).isoformat(),
    )
    board = _build_relay_board(
        {
            "needs_attention": [waiting],
            "in_progress": [fresh_run, stuck],
            "done": [],
            "counts": {},
        },
        now=NOW,
    )

    assert [r["id"] for r in board["needs_attention"]] == ["h-wait"]
    assert [r["id"] for r in board["claimed_stuck"]] == ["h-stuck"]
    assert [r["id"] for r in board["in_progress"]] == ["h-fresh"]
    assert board["counts"]["needs_attention"] == 1
    assert board["counts"]["claimed_stuck"] == 1
    assert board["counts"]["in_progress"] == 1

    stuck_row = board["claimed_stuck"][0]
    assert stuck_row["bucket"] == "claimed_stuck"
    assert stuck_row["stalled"]["reason"] == "claimed_stuck"
    assert stuck_row["due_label"] == "CLAIMED STUCK"

    wait_row = board["needs_attention"][0]
    assert wait_row["bucket"] == "needs_attention"
    assert "stalled" not in wait_row or wait_row.get("stalled") is None


def test_relay_board_attaches_related_to_job_origin():
    handoff = _h(id="ho-1", handoff_relay_status="queued")
    fake_lineage = {
        ("handoff", "ho-1"): [
            {"kind": "job", "id": "job-9", "relation": "materialized"},
            {"kind": "handoff", "id": "other", "relation": "sibling"},
        ]
    }
    with patch("services.home.cmd_center.lineage_for", return_value=fake_lineage):
        board = _build_relay_board(
            {"needs_attention": [handoff], "in_progress": [], "done": []},
            now=NOW,
        )
    row = board["needs_attention"][0]
    assert row["related_to"] == [{"kind": "job", "id": "job-9"}]


def test_relay_stats_close_rate_math():
    # Spec scenario: 10 issued this week, 7 completed → 70% close rate.
    issued_at = (NOW - timedelta(days=2)).isoformat()
    old_at = (NOW - timedelta(days=30)).isoformat()
    handoffs = {
        "needs_attention": [
            _h(id="open-1", handoff_at=issued_at, handoff_relay_status="queued"),
            _h(id="fail-1", handoff_at=issued_at, handoff_relay_status="failed"),
        ],
        "in_progress": [
            _h(id="run-1", handoff_at=issued_at, handoff_relay_status="running"),
        ],
        "done": [
            *[_h(id=f"done-{i}", handoff_at=issued_at, handoff_relay_status="complete") for i in range(7)],
            _h(id="old-done", handoff_at=old_at, handoff_relay_status="complete"),
        ],
    }
    stats = _build_relay_stats(handoffs, now=NOW, window_days=7)
    assert stats["window_days"] == 7
    assert stats["issued"] == 10
    assert stats["completed"] == 7
    assert stats["failed"] == 1
    assert stats["open"] == 2
    assert stats["close_rate"] == 0.7


def test_relay_stats_empty_window_close_rate_none():
    stats = _build_relay_stats(
        {"needs_attention": [], "in_progress": [], "done": []},
        now=NOW,
    )
    assert stats["issued"] == 0
    assert stats["close_rate"] is None


def test_build_cmd_center_exposes_relay_board_and_stats():
    hours = STALLED_SLA["handoff_claimed_stuck_hours"]
    now = datetime.now(timezone.utc)
    handoffs = {
        "needs_attention": [_h(id="h-wait", handoff_relay_status="queued", handoff_at=now.isoformat())],
        "in_progress": [
            _h(
                id="h-stuck",
                handoff_relay_status="running",
                handoff_at=now.isoformat(),
                handoff_relay_started_at=(now - timedelta(hours=hours + 1)).isoformat(),
            )
        ],
        "done": [
            _h(id="h-done", handoff_at=now.isoformat(), handoff_relay_status="complete"),
        ],
        "counts": {"needs_attention": 1, "in_progress": 1, "done": 1},
    }
    data = build_cmd_center(
        notes=[],
        documents=[],
        tasks=[],
        sessions=[],
        handoffs=handoffs,
        include_globe=False,
    )

    assert "relay_board" in data
    assert "relay_stats" in data
    assert data["relay_board"]["counts"]["claimed_stuck"] == 1
    assert data["relay_board"]["counts"]["needs_attention"] == 1
    assert data["counts"]["handoffs_claimed_stuck"] == 1
    assert data["relay_stats"]["completed"] >= 1
    assert data["relay_stats"]["close_rate"] is not None
