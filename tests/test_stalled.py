"""Read-time stalled-item detector (cmd-center-active-systems phase 2)."""

from datetime import datetime, timedelta, timezone

from services.home.cmd_center import _build_priority_queue
from services.home.stalled import STALLED_SLA, compute_stalled


NOW = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)


def test_job_needs_review_boundary():
    days = STALLED_SLA["job_needs_review_days"]
    at_threshold = {
        "id": "j1",
        "attention": "needs_review",
        "updated_at": (NOW - timedelta(days=days)).isoformat(),
    }
    past_threshold = {
        "id": "j2",
        "attention": "needs_review",
        "updated_at": (NOW - timedelta(days=days, hours=1)).isoformat(),
    }
    assert compute_stalled("job", at_threshold, NOW) is None
    stalled = compute_stalled("job", past_threshold, NOW)
    assert stalled is not None
    assert stalled["reason"] == "needs_review_sla"
    assert "since" in stalled


def test_job_not_needs_review_never_stalled():
    obj = {
        "id": "j3",
        "attention": "ready_to_apply",
        "updated_at": (NOW - timedelta(days=30)).isoformat(),
    }
    assert compute_stalled("job", obj, NOW) is None


def test_handoff_claimed_stuck_boundary():
    hours = STALLED_SLA["handoff_claimed_stuck_hours"]
    at_threshold = {
        "id": "h1",
        "handoff_relay_status": "running",
        "handoff_relay_started_at": (NOW - timedelta(hours=hours)).isoformat(),
    }
    past = {
        "id": "h2",
        "handoff_relay_status": "running",
        "handoff_relay_started_at": (NOW - timedelta(hours=hours, minutes=1)).isoformat(),
    }
    assert compute_stalled("handoff", at_threshold, NOW) is None
    stalled = compute_stalled("handoff", past, NOW)
    assert stalled is not None
    assert stalled["reason"] == "claimed_stuck"


def test_handoff_complete_or_queued_not_claimed_stuck():
    old = (NOW - timedelta(days=10)).isoformat()
    assert (
        compute_stalled(
            "handoff",
            {"handoff_relay_status": "complete", "handoff_relay_started_at": old},
            NOW,
        )
        is None
    )
    assert (
        compute_stalled(
            "handoff",
            {"handoff_relay_status": "queued", "handoff_at": old},
            NOW,
        )
        is None
    )
    assert (
        compute_stalled(
            "handoff",
            {"handoff_relay_status": "failed", "handoff_at": old},
            NOW,
        )
        is None
    )


def test_task_in_progress_boundary():
    days = STALLED_SLA["task_in_progress_days"]
    at_threshold = {
        "id": "t1",
        "task_status": "in_progress",
        "task_status_at": (NOW - timedelta(days=days)).isoformat(),
    }
    past = {
        "id": "t2",
        "task_status": "in_progress",
        "task_status_at": (NOW - timedelta(days=days, seconds=1)).isoformat(),
    }
    assert compute_stalled("task", at_threshold, NOW) is None
    stalled = compute_stalled("task", past, NOW)
    assert stalled is not None
    assert stalled["reason"] == "in_progress_sla"


def test_task_queued_not_stalled():
    obj = {
        "task_status": "queued",
        "task_status_at": (NOW - timedelta(days=30)).isoformat(),
    }
    assert compute_stalled("task", obj, NOW) is None


def test_note_stale_brief_and_fresh():
    stale = {
        "id": "n1",
        "title": "Daily Brief — 2026-07-28 (Tuesday)",
        "archived": False,
        "updated_at": "2026-07-28T08:00:00+00:00",
    }
    fresh = {
        "id": "n2",
        "title": "Daily Brief — 2026-07-31 (Friday)",
        "archived": False,
        "updated_at": NOW.isoformat(),
        "items": [{"text": "a"}, {"text": "b"}, {"text": "c"}],
    }
    stalled = compute_stalled("note", stale, NOW)
    assert stalled is not None
    assert stalled["reason"] == "stale_brief"
    assert compute_stalled("note", fresh, NOW) is None


def test_compute_stalled_no_persisted_state_recovers_across_calls():
    """Recompute reflects live status — no DB flag to clear."""
    days = STALLED_SLA["task_in_progress_days"]
    obj = {
        "id": "t-live",
        "task_status": "in_progress",
        "task_status_at": (NOW - timedelta(days=days + 1)).isoformat(),
    }
    first = compute_stalled("task", obj, NOW)
    assert first is not None
    assert first["reason"] == "in_progress_sla"

    # Operator updates status before next poll — same object dict, no unstall API.
    obj["task_status"] = "done"
    obj["task_status_at"] = NOW.isoformat()
    second = compute_stalled("task", obj, NOW)
    assert second is None


def test_priority_queue_boosts_stalled_job_urgency():
    days = STALLED_SLA["job_needs_review_days"]
    boost = int(STALLED_SLA["urgency_boost"])
    fresh_job = {
        "id": "j-fresh",
        "company": "FreshCo",
        "role": "Eng",
        "updated_at": (NOW - timedelta(days=1)).isoformat(),
    }
    stalled_job = {
        "id": "j-stale",
        "company": "StaleCo",
        "role": "PM",
        "updated_at": (NOW - timedelta(days=days + 1)).isoformat(),
    }
    queue = _build_priority_queue(
        notes_list=[],
        active_tasks=[],
        handoffs={"needs_attention": [], "in_progress": [], "counts": {}},
        jobs={
            "needs_review": [fresh_job, stalled_job],
            "ready_to_apply": [],
        },
        now=NOW,
    )
    by_id = {i["id"]: i for i in queue}
    assert by_id["j-fresh"]["urgency"] == 95
    assert "stalled" not in by_id["j-fresh"]
    assert by_id["j-stale"]["urgency"] == 95 + boost
    assert by_id["j-stale"]["stalled"]["reason"] == "needs_review_sla"


def test_priority_queue_surfaces_claimed_stuck_handoff():
    hours = STALLED_SLA["handoff_claimed_stuck_hours"]
    boost = int(STALLED_SLA["urgency_boost"])
    stuck = {
        "id": "h-stuck",
        "title": "Stuck relay",
        "handoff_target": "cursor",
        "handoff_relay_status": "running",
        "handoff_relay_started_at": (NOW - timedelta(hours=hours + 2)).isoformat(),
    }
    queue = _build_priority_queue(
        notes_list=[],
        active_tasks=[],
        handoffs={
            "needs_attention": [],
            "in_progress": [stuck],
            "counts": {"needs_attention": 0, "in_progress": 1},
        },
        jobs={"needs_review": [], "ready_to_apply": []},
        now=NOW,
    )
    row = next(i for i in queue if i["id"] == "h-stuck")
    assert row["stalled"]["reason"] == "claimed_stuck"
    assert row["urgency"] == 100 + boost
    assert row["due_label"] == "CLAIMED STUCK"


def test_email_unread_urgent_48h_boundary():
    hours = STALLED_SLA["email_unread_urgent_hours"]
    assert hours == 48
    at_threshold = {
        "id": "acc:u1",
        "score": 3,
        "urgent": True,
        "is_read": False,
        "ts": (NOW - timedelta(hours=hours)).timestamp(),
        "subject": "At threshold",
    }
    past = {
        "id": "acc:u2",
        "score": 2,
        "urgent": True,
        "is_read": False,
        "ts": (NOW - timedelta(hours=hours, minutes=1)).timestamp(),
        "subject": "Past SLA",
    }
    assert compute_stalled("email", at_threshold, NOW) is None
    stalled = compute_stalled("email", past, NOW)
    assert stalled is not None
    assert stalled["reason"] == "unread_urgent_sla"


def test_email_read_or_non_urgent_not_stalled():
    old_ts = (NOW - timedelta(days=5)).timestamp()
    assert (
        compute_stalled(
            "email",
            {"score": 3, "urgent": True, "is_read": True, "ts": old_ts},
            NOW,
        )
        is None
    )
    assert (
        compute_stalled(
            "email",
            {"score": 1, "urgent": False, "is_read": False, "ts": old_ts},
            NOW,
        )
        is None
    )


def test_priority_queue_escalates_unread_urgent_email():
    hours = STALLED_SLA["email_unread_urgent_hours"]
    boost = int(STALLED_SLA["urgency_boost"])
    fresh = {
        "id": "acc:fresh",
        "subject": "Fresh urgent",
        "score": 3,
        "urgent": True,
        "is_read": False,
        "ts": (NOW - timedelta(hours=1)).timestamp(),
    }
    stalled_em = {
        "id": "acc:stale",
        "subject": "Ignored urgent",
        "score": 3,
        "urgent": True,
        "is_read": False,
        "ts": (NOW - timedelta(hours=hours + 2)).timestamp(),
    }
    queue = _build_priority_queue(
        notes_list=[],
        active_tasks=[],
        handoffs={"needs_attention": [], "in_progress": [], "counts": {}},
        jobs={"needs_review": [], "ready_to_apply": []},
        comms_preview=[fresh, stalled_em],
        now=NOW,
    )
    by_id = {i["id"]: i for i in queue}
    assert "acc:fresh" not in by_id
    row = by_id["acc:stale"]
    assert row["kind"] == "email"
    assert row["branch"] == "comms"
    assert row["stalled"]["reason"] == "unread_urgent_sla"
    assert row["urgency"] == 92 + boost
    assert row["due_label"] == "UNREAD 48H+"
    assert row["action"] == "email"
