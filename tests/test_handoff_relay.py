"""Tests for handoff relay helpers."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from src.handoff_relay import (
    _ensure_relay_session,
    _extract_outcome,
    _outcome_looks_failed,
    _parse_frontmatter,
    _replace_frontmatter_field,
    build_relay_agent_prompt,
    claim_external_relay,
    is_external_relay_target,
    queue_handoff_relay_for_document,
    retry_handoff_relay,
    scan_stuck_relays,
    should_run_odysseus_relay,
    write_external_inbox,
)


@pytest.fixture()
def relay_db(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'handoff_relay.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("src.handoff_relay.SessionLocal", session_factory)
    return session_factory


def test_build_relay_agent_prompt_includes_packet():
    prompt = build_relay_agent_prompt("## Goal\nShip it", "cursor")
    assert "HANDOFF PACKET" in prompt
    assert "Ship it" in prompt
    assert "do NOT ask them to paste an ID" in prompt


def test_extract_outcome_section():
    text = "Working…\n\n## Outcome\n- **Done:** wired relay\n- **Remaining:** none"
    assert "wired relay" in _extract_outcome(text)


def test_extract_outcome_fallback_truncates():
    long = "x" * 5000
    assert len(_extract_outcome(long)) == 4000


def test_frontmatter_roundtrip():
    content = "---\nstatus: queued\ntarget: cursor\n---\n\nBody"
    meta, body = _parse_frontmatter(content)
    assert meta["status"] == "queued"
    assert body.strip() == "Body"
    updated = _replace_frontmatter_field(content, "status", "complete")
    assert "status: complete" in updated
    assert "Body" in updated


def test_write_external_inbox(tmp_path):
    def _fake_inbox(target):
        d = tmp_path / target
        d.mkdir(parents=True, exist_ok=True)
        return d

    with patch("src.handoff_relay._inbox_dir", _fake_inbox):
        path = write_external_inbox(
            "doc-abc",
            "cursor",
            "Test handoff",
            "---\nstatus: queued\n---\n\nGoal here",
            "note-1",
        )
        p = Path(path)
        assert p.exists()
        text = p.read_text(encoding="utf-8")
        assert "doc-abc" in text
        assert "Goal here" in text
        assert "HANDOFF PACKET" in text


def test_write_external_inbox_hermes(tmp_path):
    def _fake_inbox(target):
        d = tmp_path / target
        d.mkdir(parents=True, exist_ok=True)
        return d

    with patch("src.handoff_relay._inbox_dir", _fake_inbox):
        path = write_external_inbox(
            "doc-hermes",
            "hermes",
            "Test Hermes handoff",
            "---\nstatus: queued\n---\n\nGoal here",
            "note-2",
        )
        p = Path(path)
        assert p.parent.name == "hermes"
        assert p.exists()


def test_external_relay_target_helpers():
    assert is_external_relay_target("cursor")
    assert is_external_relay_target("claude-code")
    assert is_external_relay_target("hermes")
    assert is_external_relay_target("brudda")
    assert not is_external_relay_target("odysseus")
    assert should_run_odysseus_relay("odysseus")
    assert not should_run_odysseus_relay("cursor")
    assert not should_run_odysseus_relay("hermes")


def test_scan_stuck_skips_external_queued_schedule():
    """External queued handoffs must not spawn Odysseus agent relay."""
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    note = SimpleNamespace(
        id="n1",
        handoff_doc_id="d1",
        handoff_target="cursor",
        handoff_relay_status="queued",
        handoff_at=old.strftime("%Y-%m-%dT%H:%M:%SZ"),
        owner="alice",
    )
    with patch("src.handoff_relay.schedule_relay") as sched, patch(
        "src.handoff_relay._finalize_relay", new_callable=AsyncMock
    ), patch("src.handoff_relay.SessionLocal") as sl:
        db = sl.return_value
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = [note]
        asyncio.run(scan_stuck_relays())
    sched.assert_not_called()


def test_ensure_relay_session_no_duplicate_insert():
    """ensure_task_session + db.add must not both INSERT the same session id."""
    note = SimpleNamespace(
        handoff_relay_session_id=None,
        agent_session_id=None,
        owner="alice",
    )
    existing_sess = SimpleNamespace(id="fixed-session-id", folder=None, mode=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing_sess

    fake_sm = MagicMock()

    with patch("src.handoff_relay._session_manager", fake_sm), patch(
        "src.handoff_relay.uuid.uuid4", return_value="fixed-session-id"
    ):
        sid = _ensure_relay_session(
            db,
            note=note,
            endpoint_url="http://localhost/v1",
            model="test-model",
            title="Relay: test handoff",
        )

    assert sid == "fixed-session-id"
    fake_sm.ensure_task_session.assert_called_once()
    db.add.assert_not_called()
    assert existing_sess.folder == "Handoffs"
    assert existing_sess.mode == "agent"
    assert note.handoff_relay_session_id == "fixed-session-id"


def test_outcome_looks_failed_detects_cli_and_db_errors():
    assert _outcome_looks_failed("UNIQUE constraint failed: sessions.id")
    assert _outcome_looks_failed("At C:\\agent.ps1:62 char:1\n+ node.exe")
    assert not _outcome_looks_failed("- **Done:** shipped relay\n- **Remaining:** none")


def test_retry_handoff_relay_resets_and_schedules_odysseus():
    note = SimpleNamespace(
        id="n1",
        handoff_doc_id="d1",
        handoff_target="odysseus",
        owner="alice",
        handoff_relay_status="failed",
        handoff_outcome="old error",
        handoff_relay_started_at="2026-01-01",
        handoff_relay_completed_at="2026-01-01",
        handoff_relay_session_id="old-sid",
        handoff_at="2026-01-01",
    )
    doc = SimpleNamespace(id="d1", title="Handoff doc", current_content="body")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [note, doc]

    with patch("src.handoff_relay.SessionLocal", return_value=db), patch(
        "src.handoff_relay.write_external_inbox", return_value="/tmp/inbox.md"
    ) as inbox, patch("src.handoff_relay.schedule_relay") as sched:
        out = retry_handoff_relay("n1", owner="alice")

    assert out["ok"] is True
    assert note.handoff_relay_status == "queued"
    assert note.handoff_outcome is None
    assert note.handoff_relay_session_id is None
    inbox.assert_called_once()
    sched.assert_called_once_with("n1", "d1", "alice")
    db.commit.assert_called_once()


def test_queue_handoff_relay_for_document_creates_note(relay_db):
    """Document-only handoffs (selection highlight) must queue relay for watcher."""
    from core.database import Document, Note

    db = relay_db()
    doc = Document(
        id="doc-orphan-1",
        title="handoff → cursor: MeritFirst — AI Engineer",
        language="markdown",
        current_content="---\ntarget: cursor\n---\n\n## Goal\n\nTailor resume",
        version_count=1,
        is_active=True,
        owner="alice",
    )
    db.add(doc)
    db.commit()

    with patch("src.handoff_relay.write_external_inbox", return_value="/tmp/inbox.md") as inbox:
        out = queue_handoff_relay_for_document("doc-orphan-1", owner="alice")

    assert out["ok"] is True
    assert out["status"] == "queued"
    assert out["target"] == "cursor"
    inbox.assert_called_once()

    db2 = relay_db()
    note = db2.query(Note).filter(Note.handoff_doc_id == "doc-orphan-1").first()
    assert note is not None
    assert note.handoff_relay_status == "queued"
    assert note.handoff_target == "cursor"


def test_claim_external_relay_marks_running_and_stores_cli_session(relay_db):
    from core.database import Document, Note

    db = relay_db()
    doc = Document(
        id="doc-cli-1",
        title="handoff → cursor: Live CLI",
        language="markdown",
        current_content="---\ntarget: cursor\nstatus: pending\n---\n\n## Goal\nGo",
        version_count=1,
        is_active=True,
        owner=None,
    )
    note = Note(
        id="note-cli-1",
        owner=None,
        title="Live CLI",
        handoff_doc_id="doc-cli-1",
        handoff_target="cursor",
        handoff_relay_status="queued",
    )
    db.add(doc)
    db.add(note)
    db.commit()

    sid = "ae628ff4-d881-4031-a6e1-b9e9c660482d"
    assert claim_external_relay("doc-cli-1", owner="alice", session_id=sid) is True

    db2 = relay_db()
    note2 = db2.query(Note).filter(Note.id == "note-cli-1").first()
    assert note2.handoff_relay_status == "running"
    assert note2.handoff_relay_session_id == sid
    doc2 = db2.query(Document).filter(Document.id == "doc-cli-1").first()
    assert "status: running" in (doc2.current_content or "")
    assert f"external_session_id: {sid}" in (doc2.current_content or "")

    assert claim_external_relay("doc-cli-1", owner="alice", session_id=sid) is True

