"""Agency job_mode=watch: 30-day watch/archive, HUD must not steal CORE hero."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from services.home.cmd_center import build_cmd_center
from src.job_pipeline.brief import (
    classify_job_watch,
    get_job_mode,
    get_jobs_for_brief,
    job_last_touch,
    partition_jobs_for_watch,
)
from src.job_pipeline.store import create_job_record


def _now():
    return datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_job_mode_defaults_to_watch(monkeypatch):
    monkeypatch.delenv("ODYSSEUS_JOB_MODE", raising=False)
    monkeypatch.delenv("JOB_MODE", raising=False)
    monkeypatch.setattr("src.settings.get_setting", lambda key, default=None: default)
    assert get_job_mode() == "watch"
    assert get_job_mode(jobs={"ready_to_apply_count": 4}) == "watch"
    assert get_job_mode(jobs={"job_mode": "apply"}) == "apply"
    monkeypatch.setenv("ODYSSEUS_JOB_MODE", "apply")
    assert get_job_mode() == "apply"


def test_watch_window_uses_last_email_over_stale_update():
    """Clock is last email/update: a fresh email keeps the role on watch."""
    now = _now()
    stale = {
        "id": "old",
        "company": "Acme",
        "role": "Eng",
        "updated_at": (now - timedelta(days=45)).isoformat(),
        "raw_input": {"last_email_at": (now - timedelta(days=2)).isoformat()},
    }
    assert job_last_touch(stale).date() == (now - timedelta(days=2)).date()
    assert classify_job_watch(stale, now=now, window_days=30) == "watched"

    expired = {
        "id": "expired",
        "company": "OldCo",
        "role": "PM",
        "updated_at": (now - timedelta(days=45)).isoformat(),
        "ready_to_apply_at": (now - timedelta(days=40)).isoformat(),
    }
    assert classify_job_watch(expired, now=now, window_days=30) == "archive_candidate"

    expiring = {
        "id": "soon",
        "company": "SoonCo",
        "role": "DS",
        "last_email_at": (now - timedelta(days=26)).isoformat(),
    }
    assert classify_job_watch(expiring, now=now, window_days=30) == "expiring"


def test_partition_treats_past_window_as_archive_not_apply_now():
    now = _now()
    watched, expiring, archive = partition_jobs_for_watch(
        [
            {"id": "w", "company": "NewCo", "updated_at": now.isoformat()},
            {"id": "e", "company": "SoonCo", "last_email_at": (now - timedelta(days=26)).isoformat()},
            {"id": "a", "company": "OldCo", "updated_at": (now - timedelta(days=45)).isoformat()},
        ],
        now=now,
        window_days=30,
    )
    assert [j["id"] for j in watched] == ["w"]
    assert [j["id"] for j in expiring] == ["e"]
    assert [j["id"] for j in archive] == ["a"]
    assert archive[0]["watch_state"] == "archive_candidate"


def _job_db(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'jobs-watch.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.store.SessionLocal", session_factory)
    return session_factory


def test_jobs_for_brief_watch_splits_archive_candidates(monkeypatch, tmp_path):
    """Ready inventory older than 30 days is an archive candidate, not apply-now."""
    session_factory = _job_db(monkeypatch, tmp_path)
    monkeypatch.setenv("ODYSSEUS_JOB_MODE", "watch")

    fresh = create_job_record(
        owner="alice",
        status="ready_to_apply",
        terminal_status="ready_to_apply",
        company="Fresh Co",
        role="Engineer",
    )
    stale = create_job_record(
        owner="alice",
        status="ready_to_apply",
        terminal_status="ready_to_apply",
        company="Stale Co",
        role="PM",
    )
    old = datetime(2026, 6, 1, 12, 0, 0)
    db = session_factory()
    try:
        db.execute(
            text(
                "UPDATE job_records SET updated_at = :t, created_at = :t, "
                "ready_to_apply_at = :t WHERE id = :id"
            ),
            {"t": old, "id": stale.id},
        )
        db.commit()
    finally:
        db.close()

    brief = get_jobs_for_brief(owner="alice", limit=5)
    assert brief["job_mode"] == "watch"
    assert brief["watch_window_days"] == 30
    assert brief["archive_candidate_count"] == 1
    assert any(j["company"] == "Stale Co" for j in brief["archive_candidates"])
    assert not any(j["company"] == "Stale Co" for j in brief["ready_to_apply"])
    assert any(j["company"] == "Fresh Co" for j in brief["ready_to_apply"])
    assert brief["ready_to_apply_count"] == 1
    assert "watched" in brief["headline"].lower()
    assert "ready to apply" not in brief["headline"].lower()
    assert fresh.id  # created


def _search_as_code_note():
    return {
        "id": "n-sac",
        "title": "Search as Code",
        "pinned": True,
        "note_type": "checklist",
        "archived": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": [{"text": f"Directive {i}", "done": False} for i in range(10)],
    }


def test_full_picture_hero_skips_jobs_ready_in_watch_mode():
    """Default CORE hero stays Search as Code even when the apply queue has ready apps."""
    jobs = {
        "job_mode": "watch",
        "ready_to_apply_count": 4,
        "needs_review_count": 2,
        "watched_count": 5,
        "expiring_count": 1,
        "archive_candidate_count": 3,
        "ready_to_apply": [
            {
                "id": "j1",
                "company": "Acme",
                "role": "Engineer",
                "watch_state": "watched",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "needs_review": [
            {
                "id": "j2",
                "company": "Beta",
                "role": "PM",
                "watch_state": "expiring",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "headline": "5 watched · 1 expiring",
        "summary_lines": ["5 watched · 1 expiring"],
    }
    data = build_cmd_center(
        notes=[_search_as_code_note()],
        documents=[],
        tasks=[],
        sessions=[],
        include_globe=False,
        handoffs={"needs_attention": [], "counts": {"needs_attention": 0, "in_progress": 0}},
        jobs=jobs,
    )
    assert data["hero"]["unit"] == "DIRECTIVES"
    assert "Search as Code" in (data["hero"].get("title") or "")
    assert data["hero"]["unit"] != "JOBS READY"
    assert data["hero"].get("branch") != "agency"
    agency = next(b for b in data["branch_health"] if b["id"] == "agency")
    assert agency["count"] == 6
    assert agency["summary"] == "5 watched · 1 expiring"
    assert agency["state"] == "alive"
    assert data["jobs_detail"]["job_mode"] == "watch"
    assert data["money_hero"]["unit"] != "JOBS READY"


def test_apply_mode_still_promotes_jobs_ready_when_queue_is_empty_of_directives():
    data = build_cmd_center(
        notes=[],
        documents=[],
        tasks=[],
        sessions=[],
        include_globe=False,
        handoffs={"needs_attention": [], "counts": {"needs_attention": 0, "in_progress": 0}},
        jobs={
            "job_mode": "apply",
            "ready_to_apply_count": 2,
            "needs_review_count": 0,
            "ready_to_apply": [{"id": "j1", "company": "Acme", "role": "Engineer"}],
            "needs_review": [],
            "headline": "2 job(s) ready to apply",
        },
    )
    assert data["hero"]["unit"] == "JOBS READY"
    agency = next(b for b in data["branch_health"] if b["id"] == "agency")
    assert agency["summary"] == "2 ready · 0 review"
    assert agency["state"] == "busy"
