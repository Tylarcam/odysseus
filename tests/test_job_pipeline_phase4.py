"""Tests for job search pipeline Phase 4 — apply queue, follow-ups, brief."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from src.job_pipeline.apply_queue import (
    build_apply_package,
    compose_handshake_apply_message,
    get_apply_package,
    mark_applied,
    on_ready_to_apply,
)
from src.job_pipeline.brief import get_jobs_for_brief
from src.job_pipeline.followups import schedule_followup
from src.job_pipeline.orchestrator import transition_to_ready_to_apply
from src.job_pipeline.research_enrichment import maybe_start_job_research
from src.job_pipeline.store import create_job_record, get_job_record, update_job_record


@pytest.fixture()
def job_db(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'jobs-phase4.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.store.SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.followups.SessionLocal", session_factory)
    root = tmp_path / "job-app-ops"
    monkeypatch.setenv("JOB_APPLICATION_OPS_ROOT", str(root))
    return session_factory, root


def _ready_job(job_db, *, handshake_job_id: str = "11098487"):
    _, root = job_db
    folder = "AcmeCorp_AIEngineer_2026-06"
    folder_path = root / "positions" / "_active" / folder
    folder_path.mkdir(parents=True)
    jd_path = folder_path / "JD.md"
    jd_path.write_text("# JD\n\nBuild agents.\n", encoding="utf-8")
    pdf_path = folder_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    cover_path = folder_path / "cover-letter.md"
    cover_path.write_text("Dear hiring manager,\n", encoding="utf-8")

    record = create_job_record(
        owner="alice",
        status="ready_to_apply",
        company="Acme Corp",
        role="AI Engineer",
        handshake_job_id=handshake_job_id,
        folder_slug=folder,
        jd_path=str(jd_path),
        apply_url="https://stanford.joinhandshake.com/jobs/11098487",
    )
    return record, folder_path


def test_compose_handshake_apply_message_includes_playbook():
    msg = compose_handshake_apply_message(handshake_job_id="11098487", goal="Acme AI Engineer")
    assert "handshake-apply-workflow.md" in msg
    assert "Stop before Submit Application" in msg
    assert "11098487" in msg
    assert "Acme AI Engineer" in msg


def test_apply_package_returns_correct_paths(job_db):
    record, folder_path = _ready_job(job_db)
    package = build_apply_package(record)
    assert package["company"] == "Acme Corp"
    assert package["role"] == "AI Engineer"
    assert package["handshake_job_id"] == "11098487"
    assert package["pdf_path"] == str(folder_path / "resume.pdf")
    assert package["cover_letter_path"] == str(folder_path / "cover-letter.md")
    assert "Handshake job ID: 11098487" in package["composed_message"]

    stored = get_apply_package(record.id)
    assert stored["pdf_path"] == package["pdf_path"]
    artifact = folder_path / "apply-package.json"
    assert artifact.is_file()
    on_disk = json.loads(artifact.read_text(encoding="utf-8"))
    assert on_disk["job_id"] == record.id


def test_mark_applied_sets_state_and_writes_status_md(job_db):
    record, folder_path = _ready_job(job_db)
    with patch("src.job_pipeline.followups.schedule_followup") as mock_followup:
        mock_followup.return_value = {"task_id": "task-1"}
        result = mark_applied(record.id, owner="alice")

    assert result["status"] == "applied"
    assert result["terminal_status"] == "applied"
    assert result["applied_at"]

    status_path = folder_path / "status.md"
    assert status_path.is_file()
    text = status_path.read_text(encoding="utf-8")
    assert "**Status:** applied" in text
    assert "Acme Corp" in text

    reloaded = get_job_record(record.id)
    assert reloaded.status == "applied"
    mock_followup.assert_called_once()


def test_mark_applied_succeeds_when_status_md_unwritable(job_db):
    """Docker often cannot write under JOB_APPLICATION_OPS_ROOT (/app/code/...)."""
    record, _ = _ready_job(job_db)
    with patch("src.job_pipeline.followups.schedule_followup") as mock_followup, patch(
        "src.job_pipeline.apply_queue.os.makedirs",
        side_effect=PermissionError(13, "Permission denied", "/app/code"),
    ):
        mock_followup.return_value = {"task_id": "task-1"}
        result = mark_applied(record.id, owner="alice")

    assert result["status"] == "applied"
    assert result["terminal_status"] == "applied"
    assert get_job_record(record.id).status == "applied"
    mock_followup.assert_called_once()


def test_followup_task_creation(job_db):
    record, _ = _ready_job(job_db)
    update_job_record(record.id, status="applied")
    task_id = str(uuid.uuid4())

    def _fake_create(**kwargs):
        db = cdb.SessionLocal()
        try:
            from core.database import ScheduledTask

            task = ScheduledTask(
                id=task_id,
                owner=kwargs.get("owner"),
                name=kwargs["name"],
                prompt=kwargs["prompt"],
                task_type=kwargs.get("task_type", "llm"),
                schedule=kwargs["schedule"],
                scheduled_date=kwargs.get("scheduled_date"),
                trigger_type="schedule",
                next_run=kwargs.get("scheduled_date"),
                status="active",
                output_target="session",
            )
            db.add(task)
            db.commit()
        finally:
            db.close()
        return task_id

    with patch("src.job_pipeline.followups._create_scheduled_task", side_effect=_fake_create):
        result = schedule_followup(record.id, days=7, owner="alice")

    assert result["task_id"] == task_id
    reloaded = get_job_record(record.id)
    assert reloaded.followup_task_id == task_id


def test_transition_to_ready_to_apply_builds_package(job_db):
    _, root = job_db
    folder = "BetaCo_MLEngineer_2026-06"
    folder_path = root / "positions" / "_active" / folder
    folder_path.mkdir(parents=True)
    jd_path = folder_path / "JD.md"
    jd_path.write_text("JD body\n", encoding="utf-8")

    record = create_job_record(
        owner="alice",
        status="validated",
        company="Beta Co",
        role="ML Engineer",
        folder_slug=folder,
        jd_path=str(jd_path),
    )

    with patch("src.job_pipeline.followups.schedule_ready_to_apply_reminder") as mock_reminder:
        mock_reminder.return_value = {"task_id": "rem-1"}
        result = transition_to_ready_to_apply(record.id)

    assert result["job"]["status"] == "ready_to_apply"
    assert result["apply_package"]["company"] == "Beta Co"
    mock_reminder.assert_called_once()


def test_get_jobs_for_brief_returns_ready_to_apply(job_db):
    _ready_job(job_db)
    create_job_record(
        owner="alice",
        status="needs_review",
        terminal_status="needs_review",
        company="Review Co",
        role="Data Scientist",
    )

    brief = get_jobs_for_brief(owner="alice")
    assert brief["ready_to_apply_count"] >= 1
    assert brief["needs_review_count"] >= 1
    assert any(j["company"] == "Acme Corp" for j in brief["ready_to_apply"])
    assert "ready to apply" in brief["headline"].lower() or brief["ready_to_apply_count"] > 0


def test_get_jobs_for_brief_surfaces_legacy_validated_terminal_status(job_db):
    """Rows with status=validated but terminal_status set must still appear."""
    create_job_record(
        owner="alice",
        status="validated",
        terminal_status="ready_to_apply",
        company="Legacy Corp",
        role="Staff Engineer",
    )
    brief = get_jobs_for_brief(owner="alice")
    assert any(j["company"] == "Legacy Corp" for j in brief["ready_to_apply"])


def test_research_enrichment_skipped_when_disabled(job_db, monkeypatch):
    record, _ = _ready_job(job_db)
    update_job_record(record.id, status="normalized")
    monkeypatch.delenv("ENABLE_JOB_RESEARCH", raising=False)

    with patch("src.job_pipeline.research_enrichment.is_job_research_enabled", return_value=False):
        result = maybe_start_job_research(record.id, owner="alice")

    assert result["skipped"] is True
    reloaded = get_job_record(record.id)
    assert reloaded.research_session_id is None


def test_on_ready_to_apply_persists_package(job_db):
    record, folder_path = _ready_job(job_db)
    with patch("src.job_pipeline.followups.schedule_ready_to_apply_reminder"):
        package = on_ready_to_apply(record.id)
    assert package["folder_path"] == str(folder_path)
    reloaded = get_job_record(record.id)
    assert reloaded.apply_package_json is not None
    assert reloaded.ready_to_apply_at is not None
