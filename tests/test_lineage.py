"""Lineage backbone — edge writes, batched reads, fail-soft wiring."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from core.database import LineageEdge, Note
from core.lineage import lineage_for, record_lineage_edge
from src.builtin_actions import create_urgent_email_reminder_note


@pytest.fixture
def lineage_db(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'lineage.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("core.lineage.SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.store.SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.tailoring_dispatch.SessionLocal", session_factory)
    monkeypatch.setattr("src.handoff_relay.SessionLocal", session_factory)
    monkeypatch.setattr("src.builtin_actions.SessionLocal", session_factory, raising=False)
    return session_factory


def test_record_and_lineage_for_batch(lineage_db):
    assert record_lineage_edge(
        source_kind="job",
        source_id="job-1",
        target_kind="handoff",
        target_id="ho-1",
        relation="materialized",
    )
    assert record_lineage_edge(
        source_kind="email",
        source_id="acc:42",
        target_kind="note",
        target_id="note-1",
        relation="reminded",
    )
    assert record_lineage_edge(
        source_kind="note",
        source_id="src-note",
        target_kind="note",
        target_id="task-note",
        relation="promoted",
    )

    result = lineage_for(
        [
            ("handoff", "ho-1"),
            ("note", "note-1"),
            ("note", "task-note"),
            ("job", "job-1"),
            ("note", "orphan"),
        ]
    )
    assert result[("handoff", "ho-1")] == [
        {"kind": "job", "id": "job-1", "relation": "materialized"}
    ]
    assert result[("note", "note-1")] == [
        {"kind": "email", "id": "acc:42", "relation": "reminded"}
    ]
    assert result[("note", "task-note")] == [
        {"kind": "note", "id": "src-note", "relation": "promoted"}
    ]
    assert result[("job", "job-1")] == [
        {"kind": "handoff", "id": "ho-1", "relation": "materialized"}
    ]
    assert result[("note", "orphan")] == []


def test_record_lineage_edge_fail_soft(lineage_db):
    assert record_lineage_edge(
        source_kind="",
        source_id="x",
        target_kind="note",
        target_id="y",
        relation="promoted",
    ) is False

    with patch("core.lineage.SessionLocal", side_effect=RuntimeError("db down")):
        assert (
            record_lineage_edge(
                source_kind="job",
                source_id="j",
                target_kind="handoff",
                target_id="h",
                relation="materialized",
            )
            is False
        )


def test_job_dispatch_records_materialized_edge(lineage_db, monkeypatch, tmp_path):
    from src.job_pipeline.store import create_job_record
    from src.job_pipeline.tailoring_dispatch import dispatch_tailoring

    root = tmp_path / "job-app-ops"
    (root / "config").mkdir(parents=True)
    (root / "config" / "AGENT_WORKFLOW_SPEC.md").write_text("# Workflow\n", encoding="utf-8")
    monkeypatch.setenv("JOB_APPLICATION_OPS_ROOT", str(root))

    record = create_job_record(
        owner="alice",
        status="evaluated",
        company="Acme",
        role="Engineer",
        jd_text="Build things",
        folder_slug="acme-engineer",
    )
    fake_doc = SimpleNamespace(
        id="doc-h1",
        current_content="handoff body",
        title="handoff → cursor: Acme — Engineer",
        owner="alice",
    )

    with patch(
        "src.job_pipeline.tailoring_dispatch._create_handoff_document",
        return_value=fake_doc,
    ), patch(
        "src.job_pipeline.tailoring_dispatch.queue_handoff_relay_for_document",
        return_value={"ok": True, "inbox_path": "/tmp/inbox.md", "note_id": "relay-n1"},
    ):
        out = dispatch_tailoring(record.id, owner="alice", relay=True)

    assert out["relay_note_id"] == "relay-n1"
    related = lineage_for([("handoff", "relay-n1"), ("job", record.id)])
    assert related[("handoff", "relay-n1")] == [
        {"kind": "job", "id": record.id, "relation": "materialized"}
    ]
    assert related[("job", record.id)] == [
        {"kind": "handoff", "id": "relay-n1", "relation": "materialized"}
    ]


def test_job_dispatch_survives_lineage_failure(lineage_db, monkeypatch, tmp_path):
    from src.job_pipeline.store import create_job_record, get_job_record
    from src.job_pipeline.tailoring_dispatch import dispatch_tailoring

    root = tmp_path / "job-app-ops"
    (root / "config").mkdir(parents=True)
    (root / "config" / "AGENT_WORKFLOW_SPEC.md").write_text("# Workflow\n", encoding="utf-8")
    monkeypatch.setenv("JOB_APPLICATION_OPS_ROOT", str(root))

    record = create_job_record(
        owner="alice",
        status="evaluated",
        company="Beta",
        role="Dev",
        jd_text="Code",
        folder_slug="beta-dev",
    )
    fake_doc = SimpleNamespace(
        id="doc-h2",
        current_content="body",
        title="handoff → cursor: Beta — Dev",
        owner="alice",
    )

    with patch(
        "src.job_pipeline.tailoring_dispatch._create_handoff_document",
        return_value=fake_doc,
    ), patch(
        "src.job_pipeline.tailoring_dispatch.queue_handoff_relay_for_document",
        return_value={"ok": True, "inbox_path": "/tmp/i.md", "note_id": "n2"},
    ), patch(
        "core.lineage.record_lineage_edge",
        side_effect=RuntimeError("boom"),
    ):
        out = dispatch_tailoring(record.id, owner="alice")

    assert out["handoff_doc_id"] == "doc-h2"
    assert get_job_record(record.id).handoff_doc_id == "doc-h2"


def test_urgent_email_reminder_note_records_reminded_edges(lineage_db, monkeypatch):
    """5.1 / 1.4 — email→reminder note lineage end-to-end (comms-system scenario)."""
    monkeypatch.setattr("core.database.SessionLocal", lineage_db)

    note_id = create_urgent_email_reminder_note(
        owner="alice",
        title="Urgent email",
        body="2 emails need a reply",
        urgent_keys=["acc-1:uid-9", "acc-1:uid-10"],
    )
    assert note_id
    db = lineage_db()
    try:
        note = db.query(Note).filter(Note.id == note_id).first()
        assert note is not None
        assert note.source == "email_urgency"
        assert note.label == "urgent-email"
    finally:
        db.close()

    related = lineage_for([("note", note_id)])
    parents = {(r["kind"], r["id"], r["relation"]) for r in related[("note", note_id)]}
    assert ("email", "acc-1:uid-9", "reminded") in parents
    assert ("email", "acc-1:uid-10", "reminded") in parents
    # Comms-system related_to surface: {kind: "email", id: "account_id:uid"}
    related_to = [{"kind": r["kind"], "id": r["id"]} for r in related[("note", note_id)]]
    assert {"kind": "email", "id": "acc-1:uid-9"} in related_to
    assert {"kind": "email", "id": "acc-1:uid-10"} in related_to


def test_count_reminded_edges_over_rolling_window(lineage_db, monkeypatch):
    """5.2 / 5.4 — conversion_count counts reminded edges inside the window only."""
    from datetime import datetime, timedelta, timezone

    from core.database import LineageEdge, utcnow_naive
    from core.lineage import count_lineage_edges
    from services.home.cmd_center import COMMS_CONVERSION_WINDOW_DAYS, _build_comms_focus

    monkeypatch.setattr("core.database.SessionLocal", lineage_db)
    monkeypatch.setattr("core.lineage.SessionLocal", lineage_db)

    now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)
    window = timedelta(days=COMMS_CONVERSION_WINDOW_DAYS)
    db = lineage_db()
    try:
        # 3 inside the rolling week
        for i in range(3):
            db.add(
                LineageEdge(
                    id=f"in-{i}",
                    source_kind="email",
                    source_id=f"acc:in-{i}",
                    target_kind="note",
                    target_id=f"note-in-{i}",
                    relation="reminded",
                    created_at=(now - timedelta(days=i + 1)).replace(tzinfo=None),
                )
            )
        # 1 outside the window
        db.add(
            LineageEdge(
                id="out-1",
                source_kind="email",
                source_id="acc:out",
                target_kind="note",
                target_id="note-out",
                relation="reminded",
                created_at=(now - window - timedelta(days=1)).replace(tzinfo=None),
            )
        )
        # Noise: different relation must not count
        db.add(
            LineageEdge(
                id="mat-1",
                source_kind="job",
                source_id="j1",
                target_kind="handoff",
                target_id="h1",
                relation="materialized",
                created_at=utcnow_naive(),
            )
        )
        db.commit()
    finally:
        db.close()

    since = now - window
    assert count_lineage_edges(relation="reminded", since=since) == 3
    focus = _build_comms_focus(now=now)
    assert focus["conversion_count"] == 3
    assert focus["conversion_window_days"] == COMMS_CONVERSION_WINDOW_DAYS


def test_urgent_email_reminder_survives_lineage_failure(lineage_db, monkeypatch):
    monkeypatch.setattr("core.database.SessionLocal", lineage_db)

    with patch("core.lineage.record_lineage_edge", side_effect=RuntimeError("nope")):
        note_id = create_urgent_email_reminder_note(
            owner="alice",
            title="Urgent email",
            body="body",
            urgent_keys=["acc:1"],
        )
    assert note_id
    db = lineage_db()
    try:
        assert db.query(Note).filter(Note.id == note_id).first() is not None
        assert db.query(LineageEdge).count() == 0
    finally:
        db.close()


def _create_note_endpoint(monkeypatch, session_factory):
    import routes.note_routes as note_routes
    from routes.note_routes import NoteCreate

    monkeypatch.setattr(note_routes, "SessionLocal", session_factory)
    monkeypatch.setattr(note_routes, "get_current_user", lambda request: "alice")

    router = note_routes.setup_note_routes()
    endpoint = next(
        route.endpoint
        for route in router.routes
        if route.path == "/api/notes" and "POST" in getattr(route, "methods", set())
    )
    return endpoint, NoteCreate


def test_note_create_promoted_from_records_edge(lineage_db, monkeypatch):
    endpoint, NoteCreate = _create_note_endpoint(monkeypatch, lineage_db)

    source_id = str(uuid.uuid4())
    db = lineage_db()
    try:
        db.add(
            Note(
                id=source_id,
                owner="alice",
                title="Source memo",
                content="ideas",
                note_type="note",
                source="user",
            )
        )
        db.commit()
    finally:
        db.close()

    request = SimpleNamespace(state=SimpleNamespace(current_user="alice"))
    result = endpoint(
        request,
        NoteCreate(
            title="Promoted task",
            content="",
            note_type="todo",
            label="directive queued",
            source="cmd_center",
            promoted_from=source_id,
        ),
    )
    task_id = result["id"]
    related = lineage_for([("note", task_id)])
    assert related[("note", task_id)] == [
        {"kind": "note", "id": source_id, "relation": "promoted"}
    ]


def test_note_create_survives_lineage_failure(lineage_db, monkeypatch):
    endpoint, NoteCreate = _create_note_endpoint(monkeypatch, lineage_db)

    request = SimpleNamespace(state=SimpleNamespace(current_user="alice"))
    with patch("core.lineage.record_lineage_edge", side_effect=RuntimeError("edge fail")):
        result = endpoint(
            request,
            NoteCreate(
                title="Still created",
                note_type="todo",
                source="cmd_center",
                promoted_from="any-source",
            ),
        )
    assert result["title"] == "Still created"
    assert result["id"]
