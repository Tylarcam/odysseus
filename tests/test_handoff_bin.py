"""Tests for Agent Bin handoff bucketing."""

from src.handoff_bin import (
    attention_rank,
    bucket_handoff_notes,
    classify_handoff_bucket,
)


def _note(**kwargs):
    base = {
        "id": "n1",
        "title": "Test",
        "archived": False,
        "handoff_doc_id": "d1",
        "handoff_target": "cursor",
        "handoff_at": "2026-06-13T10:00:00Z",
        "handoff_relay_status": "queued",
    }
    base.update(kwargs)
    return base


def test_classify_running_in_progress():
    assert classify_handoff_bucket(_note(handoff_relay_status="running")) == "in_progress"


def test_classify_archived_done():
    assert classify_handoff_bucket(_note(archived=True, handoff_relay_status="complete")) == "done"


def test_classify_complete_unarchived_done():
    assert classify_handoff_bucket(_note(handoff_relay_status="complete")) == "done"


def test_classify_failed_needs_attention():
    assert classify_handoff_bucket(_note(handoff_relay_status="failed")) == "needs_attention"


def test_attention_rank_failed_first():
    failed = _note(handoff_relay_status="failed")
    queued = _note(handoff_relay_status="queued")
    assert attention_rank(failed) < attention_rank(queued)


def test_bucket_handoff_notes_groups():
    notes = [
        _note(id="a", handoff_relay_status="queued"),
        _note(id="b", handoff_relay_status="running"),
        _note(id="c", archived=True, handoff_relay_status="complete"),
        _note(id="d", handoff_relay_status="complete"),
        {"id": "x", "title": "no handoff"},
    ]
    out = bucket_handoff_notes(notes)
    assert len(out["needs_attention"]) == 1
    assert len(out["in_progress"]) == 1
    assert len(out["done"]) == 2
    assert out["counts"]["total"] == 4
