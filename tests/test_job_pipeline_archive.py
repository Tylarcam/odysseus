"""User-initiated job archive — terminal archived without mark_applied."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from src.job_pipeline.orchestrator import archive_job, inbound_job_event
from src.job_pipeline.store import get_job_events, get_job_record


def _payload(**overrides):
    base = {
        "company": "Acme Corp",
        "role": "Senior AI Engineer",
        "jd_text": "**Employer:** Acme Corp\n**Title:** Senior AI Engineer\n\nBuild agents.",
        "apply_url": "https://apply.example.com/jobs/archive-test",
        "source": "manual",
    }
    base.update(overrides)
    return base


@pytest.fixture()
def job_db(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'jobs_archive.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.store.SessionLocal", session_factory)
    monkeypatch.setenv("JOB_APPLICATION_OPS_ROOT", str(tmp_path / "job-app-ops"))
    return session_factory


def test_archive_job_from_deduped(job_db):
    record = inbound_job_event(_payload(), owner="alice")
    assert record["status"] == "deduped"
    out = archive_job(record["id"], owner="alice", reason="pipeline paused")
    assert out["status"] == "archived"
    assert out["terminal_status"] == "archived"
    loaded = get_job_record(record["id"])
    assert loaded.status == "archived"
    events = get_job_events(record["id"])
    assert any(e.stage == "user_archive" and e.to_status == "archived" for e in events)


def test_archive_job_idempotent(job_db):
    record = inbound_job_event(
        _payload(apply_url="https://apply.example.com/jobs/idem"),
        owner="bob",
    )
    first = archive_job(record["id"], owner="bob")
    second = archive_job(record["id"], owner="bob")
    assert first["status"] == "archived"
    assert second["status"] == "archived"
    user_events = [e for e in get_job_events(record["id"]) if e.stage == "user_archive"]
    assert len(user_events) == 1


def test_archive_job_access_denied(job_db):
    record = inbound_job_event(
        _payload(apply_url="https://apply.example.com/jobs/own"),
        owner="carol",
    )
    with pytest.raises(ValueError, match="access denied"):
        archive_job(record["id"], owner="eve")


def test_archive_job_not_found(job_db):
    with pytest.raises(ValueError, match="not found"):
        archive_job("missing-id", owner="alice")


def test_archive_from_applied_repairs_mistaken_mark(job_db, monkeypatch):
    from src.job_pipeline.apply_queue import mark_applied as aq_mark

    record = inbound_job_event(
        _payload(apply_url="https://apply.example.com/jobs/repair"),
        owner="erin",
    )
    monkeypatch.setattr(
        "src.job_pipeline.followups.schedule_followup",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no follow-up on archive")),
    )
    aq_mark(record["id"], owner="erin")
    loaded = get_job_record(record["id"])
    assert loaded.status == "applied"
    out = archive_job(record["id"], owner="erin", reason="mistaken mark_applied")
    assert out["status"] == "archived"
    assert out["terminal_status"] == "archived"


@pytest.mark.asyncio
async def test_process_job_application_archive_action(job_db):
    from src.tool_implementations import do_process_job_application

    record = inbound_job_event(
        _payload(apply_url="https://apply.example.com/jobs/tool-arch"),
        owner="dave",
    )
    out = await do_process_job_application(
        json.dumps({
            "action": "archive",
            "job_id": record["id"],
            "reason": "Fred Hutch — pause search",
        }),
        owner="dave",
    )
    assert out["exit_code"] == 0
    assert out["job"]["status"] == "archived"
    assert "Archived" in out["response"]


@pytest.mark.asyncio
async def test_process_job_application_archive_missing(job_db):
    from src.tool_implementations import do_process_job_application

    out = await do_process_job_application(
        json.dumps({"action": "archive", "job_id": "nope"}),
        owner="dave",
    )
    assert out["exit_code"] == 1
    assert out.get("not_found") is True


def test_schema_includes_archive_action():
    from pathlib import Path

    text = Path("src/tool_schemas.py").read_text(encoding="utf-8")
    # Avoid importing FUNCTION_TOOL_SCHEMAS (circular with agent_tools).
    assert '"archive"' in text
    assert "process_job_application" in text
