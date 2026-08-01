"""PROD task_status server truth (cmd-center-active-systems phase 4)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from core.database import Note
from core.lineage import record_lineage_edge
from services.home.cmd_center import _build_priority_queue
from services.home.stalled import STALLED_SLA


NOW = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def notes_db(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'prod_task_status.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("core.lineage.SessionLocal", session_factory)
    return session_factory, engine


def _note_routes(monkeypatch, session_factory):
    import routes.note_routes as note_routes

    monkeypatch.setattr(note_routes, "SessionLocal", session_factory)
    monkeypatch.setattr(note_routes, "get_current_user", lambda request: "alice")
    router = note_routes.setup_note_routes()
    by_path = {}
    for route in router.routes:
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            by_path[(route.path, method)] = route.endpoint
    return by_path, note_routes


def test_notes_migration_adds_task_status_columns(tmp_path, monkeypatch):
    """Guarded ALTER adds task_status / task_status_at when missing."""
    db_path = tmp_path / "legacy_notes.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE notes ("
                "id VARCHAR PRIMARY KEY, owner VARCHAR, title VARCHAR, "
                "content TEXT, items TEXT, note_type VARCHAR, color VARCHAR, "
                "label VARCHAR, pinned BOOLEAN, archived BOOLEAN, due_date VARCHAR, "
                "source VARCHAR, session_id VARCHAR, sort_order INTEGER, "
                "image_url VARCHAR, repeat VARCHAR, "
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
        conn.commit()

    monkeypatch.setattr(cdb, "DATABASE_URL", f"sqlite:///{db_path}")
    cdb._migrate_add_notes_sort_order()

    cols = {c["name"] for c in inspect(engine).get_columns("notes")}
    assert "task_status" in cols
    assert "task_status_at" in cols


def test_task_status_persists_across_devices(notes_db, monkeypatch):
    """Device A writes blocked; device B (fresh GET, no localStorage) reads blocked."""
    session_factory, _engine = notes_db
    endpoints, note_routes = _note_routes(monkeypatch, session_factory)
    update = endpoints[("/api/notes/{note_id}", "PUT")]
    get_one = endpoints[("/api/notes/{note_id}", "GET")]
    NoteUpdate = note_routes.NoteUpdate

    note_id = str(uuid.uuid4())
    db = session_factory()
    try:
        db.add(
            Note(
                id=note_id,
                owner="alice",
                title="Cross-device task",
                note_type="todo",
                label="directive",
                archived=False,
            )
        )
        db.commit()
    finally:
        db.close()

    req = SimpleNamespace()
    updated = update(req, note_id, NoteUpdate(task_status="blocked"))
    assert updated["task_status"] == "blocked"
    assert updated["task_status_at"]

    # Simulate a different device: new session + GET only (no client cache).
    fresh = get_one(req, note_id)
    assert fresh["task_status"] == "blocked"
    assert fresh["task_status_at"] == updated["task_status_at"]


def test_blocked_round_trip_and_status_cycle(notes_db, monkeypatch):
    session_factory, _engine = notes_db
    endpoints, note_routes = _note_routes(monkeypatch, session_factory)
    update = endpoints[("/api/notes/{note_id}", "PUT")]
    NoteUpdate = note_routes.NoteUpdate

    note_id = str(uuid.uuid4())
    db = session_factory()
    try:
        db.add(
            Note(
                id=note_id,
                owner="alice",
                title="Cycle me",
                note_type="todo",
                archived=False,
            )
        )
        db.commit()
    finally:
        db.close()

    req = SimpleNamespace()
    for status in ("queued", "in_progress", "blocked", "done"):
        out = update(req, note_id, NoteUpdate(task_status=status))
        assert out["task_status"] == status
        assert out["task_status_at"]

    cleared = update(req, note_id, NoteUpdate(task_status=""))
    assert cleared["task_status"] is None
    assert cleared["task_status_at"] is None

    with pytest.raises(Exception) as excinfo:
        update(req, note_id, NoteUpdate(task_status="nope"))
    assert getattr(excinfo.value, "status_code", None) == 400


def test_stalled_in_progress_task_appears_in_priority_queue():
    days = STALLED_SLA["task_in_progress_days"]
    boost = int(STALLED_SLA["urgency_boost"])
    # Not pinned / due / checklist — would be skipped without stalled task_status.
    stalled_note = {
        "id": "task-stalled-1",
        "title": "Sitting idle",
        "note_type": "note",
        "label": "misc",
        "archived": False,
        "pinned": False,
        "due_date": None,
        "items": [],
        "task_status": "in_progress",
        "task_status_at": (NOW - timedelta(days=days + 1)).isoformat(),
        "updated_at": (NOW - timedelta(days=days + 1)).isoformat(),
    }
    with patch("services.home.cmd_center.lineage_for", return_value={}):
        queue = _build_priority_queue(
            notes_list=[stalled_note],
            active_tasks=[],
            handoffs={"needs_attention": [], "in_progress": [], "counts": {}},
            jobs={"needs_review": [], "ready_to_apply": []},
            now=NOW,
        )
    row = next(i for i in queue if i["id"] == "task-stalled-1")
    assert row["task_status"] == "in_progress"
    assert row["stalled"]["reason"] == "in_progress_sla"
    assert row["urgency"] >= 50 + boost
    assert row["branch"] == "prod"


def test_related_to_attached_for_promoted_prod_task(notes_db):
    session_factory, _engine = notes_db
    source_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    assert record_lineage_edge(
        source_kind="note",
        source_id=source_id,
        target_kind="note",
        target_id=task_id,
        relation="promoted",
    )
    note = {
        "id": task_id,
        "title": "Promoted task",
        "note_type": "todo",
        "label": "directive queued",
        "due_date": (NOW + timedelta(days=3)).isoformat(),
        "archived": False,
        "task_status": "queued",
        "task_status_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    queue = _build_priority_queue(
        notes_list=[note],
        active_tasks=[],
        handoffs={"needs_attention": [], "in_progress": [], "counts": {}},
        jobs={"needs_review": [], "ready_to_apply": []},
        now=NOW,
    )
    row = next(i for i in queue if i["id"] == task_id)
    assert {"kind": "note", "id": source_id} in (row.get("related_to") or [])


def test_create_note_accepts_initial_task_status(notes_db, monkeypatch):
    session_factory, _engine = notes_db
    endpoints, note_routes = _note_routes(monkeypatch, session_factory)
    create = endpoints[("/api/notes", "POST")]
    NoteCreate = note_routes.NoteCreate

    out = create(
        SimpleNamespace(),
        NoteCreate(title="New orbital", note_type="todo", task_status="queued"),
    )
    assert out["task_status"] == "queued"
    assert out["task_status_at"]
