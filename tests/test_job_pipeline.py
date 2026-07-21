"""Tests for job search pipeline Phase 1."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from src.job_pipeline.deduper import check_duplicate
from src.job_pipeline.orchestrator import inbound_job_event
from src.job_pipeline.parser import compute_dedup_key, normalize_field, parse_manual_ingest
from src.job_pipeline.store import get_job_events, get_job_record, list_job_records


@pytest.fixture()
def job_db(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'jobs.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.store.SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.document_ingest.SessionLocal", session_factory)
    monkeypatch.setenv("JOB_APPLICATION_OPS_ROOT", str(tmp_path / "job-app-ops"))
    return session_factory


def _sample_payload(**overrides):
    base = {
        "company": "Acme Corp",
        "role": "AI Engineer",
        "jd_text": "**Employer:** Acme Corp\n**Title:** AI Engineer\n\nBuild agents.",
        "source": "manual",
        "apply_url": "https://apply.example.com/jobs/123",
    }
    base.update(overrides)
    return base


def test_parser_normalizes_fields():
    parsed = parse_manual_ingest(
        {
            "company": "  Acme Corp ",
            "role": "AI Engineer",
            "jd_text": "Job body",
            "apply_url": "https://handshake.com/jobs/99999/",
        }
    )
    assert parsed["company"] == "Acme Corp"
    assert parsed["handshake_job_id"] == "99999"
    key = compute_dedup_key(parsed["company"], parsed["role"], parsed["apply_url"])
    assert normalize_field("Acme Corp") in key


def test_ingest_creates_job_record_and_jd_md(job_db):
    record = inbound_job_event(_sample_payload(), owner="alice")
    assert record["status"] == "deduped"
    assert record["company"] == "Acme Corp"
    assert record["jd_path"]
    assert os.path.isfile(record["jd_path"])
    with open(record["jd_path"], encoding="utf-8") as fh:
        text = fh.read()
    assert "Acme Corp" in text


def test_dedup_prevents_duplicate_processing(job_db):
    first = inbound_job_event(_sample_payload(), owner="alice")
    assert first["status"] == "deduped"

    second = inbound_job_event(_sample_payload(), owner="alice")
    assert second["status"] == "archived"
    assert second["duplicate_of_id"] == first["id"]


def test_state_transitions_logged_in_job_events(job_db):
    record = inbound_job_event(_sample_payload(), owner="alice")
    events = get_job_events(record["id"])
    statuses = [e.to_status for e in events]
    assert statuses[0] == "email_received"
    assert "parsed" in statuses
    assert "normalized" in statuses
    assert statuses[-1] == "deduped"
    assert all(e.stage for e in events)


def test_dedup_key_and_jd_overlap(job_db):
    first = inbound_job_event(_sample_payload(), owner="alice")
    dup = check_duplicate(
        job_id=str(uuid.uuid4()),
        company="Acme Corp",
        role="AI Engineer",
        apply_url="https://apply.example.com/jobs/123",
        jd_text=_sample_payload()["jd_text"],
    )
    assert dup["is_duplicate"] is True
    assert dup["duplicate_of_id"] == first["id"]


def test_api_ingest_and_list(job_db):
    from routes.job_routes import JobIngestRequest
    from src.job_pipeline.store import get_job_events, job_record_to_dict, list_job_records

    body = JobIngestRequest(**_sample_payload())
    record = inbound_job_event(body.model_dump(exclude_none=True), owner="alice", source="manual")
    assert record["status"] == "deduped"

    listed = [job_record_to_dict(r) for r in list_job_records(limit=10, owner="alice")]
    assert any(j["id"] == record["id"] for j in listed)

    events = get_job_events(record["id"])
    assert len(events) >= 4
    assert events[-1].to_status == "deduped"


def test_list_job_records_respects_status_filter(job_db):
    inbound_job_event(_sample_payload(), owner="bob")
    deduped = list_job_records(status="deduped")
    archived = list_job_records(status="archived")
    assert len(deduped) == 1
    assert len(archived) == 0

    inbound_job_event(_sample_payload(), owner="bob")
    archived = list_job_records(status="archived")
    assert len(archived) == 1


def test_get_job_record_roundtrip(job_db):
    created = inbound_job_event(_sample_payload(), owner="carol")
    loaded = get_job_record(created["id"])
    assert loaded is not None
    assert loaded.status == "deduped"
    assert loaded.folder_slug


def test_email_ingest_builds_payload_from_subject_and_body():
    from src.job_pipeline.email_ingest import build_email_job_payload, ingest_email_to_job_pipeline

    payload = build_email_job_payload(
        subject="Acme Corp — Senior AI Engineer",
        body="We are hiring a senior AI engineer.\nhttps://apply.example.com/jobs/42",
        uid="123",
    )
    assert payload["source"] == "email"
    assert payload["job"]["company"] == "Acme Corp"
    assert payload["job"]["role"] == "Senior AI Engineer"
    assert "We are hiring" in payload["job"]["jd_snippet"]


def test_email_ingest_runs_pipeline(job_db):
    from src.job_pipeline.email_ingest import ingest_email_to_job_pipeline

    record = ingest_email_to_job_pipeline(
        subject="Beta Labs — Product Manager",
        body="Lead product for our AI platform.\nApply: https://careers.example.com/pm",
        owner="alice",
        auto_process=False,
    )
    assert record["status"] == "deduped"
    assert record["company"] == "Beta Labs"
    assert record["role"] == "Product Manager"
    assert record["jd_path"]
    assert os.path.isfile(record["jd_path"])


def test_email_ingest_requires_content():
    from src.job_pipeline.email_ingest import ingest_email_to_job_pipeline

    with pytest.raises(ValueError, match="subject or body"):
        ingest_email_to_job_pipeline(subject="", body="")


def test_document_ingest_builds_payload_from_title_and_content():
    from src.job_pipeline.document_ingest import build_document_job_payload

    payload = build_document_job_payload(
        title="Acme Corp — Senior AI Engineer",
        content="# Senior AI Engineer\n\nWe are hiring a senior AI engineer.\nhttps://apply.example.com/jobs/42",
        doc_id="doc-1",
    )
    assert payload["source"] == "document"
    assert payload["company"] == "Acme Corp"
    assert payload["role"] == "Senior AI Engineer"
    assert payload["document_id"] == "doc-1"
    assert "We are hiring" in payload["jd_text"]


def test_document_ingest_runs_pipeline(job_db):
    import uuid

    from core.database import Document
    from src.job_pipeline.document_ingest import ingest_document_to_job_pipeline

    doc_id = str(uuid.uuid4())
    db = job_db()
    try:
        db.add(
            Document(
                id=doc_id,
                title="Beta Labs — Product Manager",
                current_content="Lead product for our AI platform.\nApply: https://careers.example.com/pm",
                owner="alice",
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    record = ingest_document_to_job_pipeline(doc_id, owner="alice", auto_process=False)
    assert record["status"] == "deduped"
    assert record["company"] == "Beta Labs"
    assert record["role"] == "Product Manager"
    assert record["jd_path"]
    assert os.path.isfile(record["jd_path"])


def test_document_ingest_requires_readable_content():
    from src.job_pipeline.document_ingest import build_document_job_payload

    with pytest.raises(ValueError, match="No readable JD text"):
        build_document_job_payload(
            title="Empty PDF",
            content='<!-- pdf_source upload_id="abc" -->',
            doc_id="doc-empty",
        )
