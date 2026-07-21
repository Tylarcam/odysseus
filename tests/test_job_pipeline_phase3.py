"""Tests for job search pipeline Phase 3 — validation and routing."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
import routes.job_routes as job_routes_mod
from src.handoff_relay import _maybe_trigger_job_validation
from src.job_pipeline.orchestrator import validate_and_route
from src.job_pipeline.routing import route_job, routing_reasons
from src.job_pipeline.store import create_job_record, get_job_record, update_job_record
from src.job_pipeline.validator import parse_match_percent, validate_job_folder, write_validation_report


@pytest.fixture()
def job_db(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'jobs_phase3.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.store.SessionLocal", session_factory)
    monkeypatch.setattr("core.database.SessionLocal", session_factory)
    root = tmp_path / "job-app-ops"
    monkeypatch.setenv("JOB_APPLICATION_OPS_ROOT", str(root))
    return {"session_factory": session_factory, "root": root}


def _make_folder(root: Path, slug: str, *, match_percent: int | None = 85, with_pdf: bool = True) -> Path:
    folder = root / "positions" / "_active" / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "JD.md").write_text("# JD\n\nAcme AI Engineer role.\n", encoding="utf-8")
    notes = "# Notes\n\nTailoring summary.\n"
    if match_percent is not None:
        notes += f"\nMatch: {match_percent}%\n"
    (folder / "notes.md").write_text(notes, encoding="utf-8")
    (folder / "cover-letter.md").write_text("# Cover letter\n\nDear hiring manager,\n", encoding="utf-8")
    docx = folder / "resume.docx"
    docx.write_bytes(b"docx")
    if with_pdf:
        pdf = folder / "resume.pdf"
        pdf.write_bytes(b"pdf")
        time.sleep(0.05)
        os.utime(pdf, (time.time(), time.time()))
    return folder


def _create_tailoring_job(job_db, slug: str, *, match_percent: int | None = 85, with_pdf: bool = True):
    folder = _make_folder(job_db["root"], slug, match_percent=match_percent, with_pdf=with_pdf)
    record = create_job_record(
        owner="alice",
        status="tailoring_complete",
        company="Acme Corp",
        role="AI Engineer",
        folder_slug=slug,
        jd_path=str(folder / "JD.md"),
        handoff_doc_id="doc-handoff-1",
    )
    return record, folder


def test_parse_match_percent_variants():
    assert parse_match_percent("Keyword match: 85%") == 85
    assert parse_match_percent("Match: 72%") == 72
    assert parse_match_percent("no score here") is None


def test_validator_passes_complete_folder(job_db):
    slug = "AcmeCorp_AIEngineer_2026-06"
    folder = _make_folder(job_db["root"], slug, match_percent=85)
    report = validate_job_folder(folder)
    assert report["passed"] is True
    assert report["match_percent"] == 85
    assert report["score"] > 0.8
    assert any(c["name"] == "artifact_pdf" and c["passed"] for c in report["checks"])


def test_validator_fails_missing_pdf(job_db):
    slug = "AcmeCorp_AIEngineer_2026-06"
    folder = _make_folder(job_db["root"], slug, match_percent=85, with_pdf=False)
    report = validate_job_folder(folder)
    assert report["passed"] is False
    pdf_check = next(c for c in report["checks"] if c["name"] == "artifact_pdf")
    assert pdf_check["passed"] is False


def test_validator_fails_stale_pdf(job_db):
    slug = "AcmeCorp_AIEngineer_2026-06"
    folder = _make_folder(job_db["root"], slug, match_percent=85, with_pdf=False)
    docx = folder / "resume.docx"
    pdf = folder / "resume.pdf"
    pdf.write_bytes(b"pdf")
    old = time.time() - 3600
    os.utime(pdf, (old, old))
    os.utime(docx, (time.time(), time.time()))
    report = validate_job_folder(folder)
    freshness = next(c for c in report["checks"] if c["name"] == "pdf_freshness")
    assert freshness["passed"] is False
    assert report["passed"] is False


def test_router_ready_to_apply(job_db):
    record, folder = _create_tailoring_job(job_db, "AcmeCorp_AIEngineer_2026-06")
    report = validate_job_folder(folder)
    assert route_job(record, report) == "ready_to_apply"


def test_router_needs_review_low_match(job_db):
    record, folder = _create_tailoring_job(job_db, "AcmeCorp_AIEngineer_2026-06", match_percent=55)
    report = validate_job_folder(folder)
    terminal = route_job(record, report)
    assert terminal == "needs_review"
    reasons = routing_reasons(record, report, terminal)
    assert any("55%" in r or "below" in r for r in reasons)


def test_router_needs_review_unparseable_match(job_db):
    record, folder = _create_tailoring_job(job_db, "AcmeCorp_AIEngineer_2026-06", match_percent=None)
    report = validate_job_folder(folder)
    terminal = route_job(record, report)
    assert terminal == "needs_review"
    reasons = routing_reasons(record, report, terminal)
    assert any("not parseable" in r for r in reasons)


def test_validate_and_route_ready_to_apply(job_db, monkeypatch):
    slug = "AcmeCorp_AIEngineer_2026-06"
    record, folder = _create_tailoring_job(job_db, slug, match_percent=88)
    monkeypatch.setattr(
        "src.job_pipeline.apply_queue.on_ready_to_apply",
        lambda _jid: {"folder_path": str(folder)},
    )
    monkeypatch.setattr(
        "src.job_pipeline.notifier.notify_validation_terminal",
        lambda *a, **k: None,
    )
    result = validate_and_route(record.id)
    assert result["terminal_status"] == "ready_to_apply"
    loaded = get_job_record(record.id)
    assert loaded.status == "ready_to_apply"
    assert loaded.terminal_status == "ready_to_apply"
    assert loaded.validation_report_path
    assert os.path.isfile(loaded.validation_report_path)


def test_validate_and_route_needs_review_sets_status(job_db, monkeypatch):
    slug = "AcmeCorp_AIEngineer_2026-06"
    record, folder = _create_tailoring_job(job_db, slug, match_percent=55)
    monkeypatch.setattr(
        "src.job_pipeline.notifier.notify_validation_terminal",
        lambda *a, **k: None,
    )
    result = validate_and_route(record.id)
    assert result["terminal_status"] == "needs_review"
    loaded = get_job_record(record.id)
    assert loaded.status == "needs_review"
    assert loaded.terminal_status == "needs_review"


def test_handoff_finalize_triggers_validate(job_db, monkeypatch):
    slug = "AcmeCorp_AIEngineer_2026-06"
    record, folder = _create_tailoring_job(job_db, slug, match_percent=90)
    update_job_record(record.id, status="tailoring_started")

    calls = []

    def _fake_validate(job_id):
        calls.append(job_id)
        return {"terminal_status": "ready_to_apply"}

    monkeypatch.setattr("src.job_pipeline.orchestrator.validate_and_route", _fake_validate)

    doc = type("Doc", (), {
        "title": "handoff → cursor: Acme Corp — AI Engineer",
        "current_content": "---\nproject: C:\\job-application-ops\n---\n",
    })()
    _maybe_trigger_job_validation("doc-handoff-1", doc, "alice")
    assert calls == [record.id]


def test_api_validate_endpoint(job_db, monkeypatch):
    slug = "AcmeCorp_AIEngineer_2026-06"
    record, folder = _create_tailoring_job(job_db, slug, match_percent=91)
    monkeypatch.setattr(
        "src.job_pipeline.apply_queue.on_ready_to_apply",
        lambda _jid: {"folder_path": str(folder)},
    )
    monkeypatch.setattr(
        "src.job_pipeline.notifier.notify_validation_terminal",
        lambda *a, **k: None,
    )

    class FakeRequest:
        state = type("S", (), {})()

    monkeypatch.setattr(job_routes_mod, "effective_user", lambda _req: "alice")

    # Invoke route handlers directly (avoids re-instantiating APIRouter when
    # handoff_relay is loaded — Starlette/FastAPI version mismatch in test env).
    record_loaded = job_routes_mod.get_job_record(record.id)
    assert record_loaded is not None
    result = job_routes_mod.validate_and_route(record.id)
    assert result["terminal_status"] == "ready_to_apply"

    report = job_routes_mod.load_validation_report(
        job_routes_mod.get_job_record(record.id).validation_report_path or ""
    )
    assert report["match_percent"] == 91


def test_write_validation_report_roundtrip(job_db, tmp_path):
    folder = tmp_path / "job-folder"
    folder.mkdir()
    report = {"passed": True, "score": 1.0, "checks": [], "match_percent": 80, "artifact_paths": {}}
    path = write_validation_report(folder, report)
    with open(path, encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["match_percent"] == 80
