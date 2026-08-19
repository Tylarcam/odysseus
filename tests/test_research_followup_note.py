"""Research save creates a vault follow-up note with the live report URL."""

import json

from src.research_handler import (
    ResearchHandler,
    create_research_followup_note,
    extract_finding_bullets,
    extract_report_title,
    list_recent_research_reports,
    research_report_url,
)
from src import research_handler as rh
from services.home.cmd_center import _is_directive_note


def _handler():
    handler = ResearchHandler.__new__(ResearchHandler)
    handler._active_tasks = {}
    return handler


def test_extract_title_prefers_heading_then_query():
    md = "# Visual Storytelling Canvas\n\n## What changed\n- beats\n"
    assert extract_report_title("fallback query", md) == "Visual Storytelling Canvas"
    assert extract_report_title("the query", "") == "the query"


def test_extract_bullets_from_headings():
    md = "# Title\n\n## Finding one\ntext\n## Finding two\nmore\n## Finding three\n"
    assert extract_finding_bullets(md, n=3) == ["Finding one", "Finding two", "Finding three"]


def test_create_followup_note_includes_url_and_brief_label(monkeypatch):
    captured = {}

    class _Col:
        def __eq__(self, _other):
            return True

    class FakeNote:
        session_id = _Col()
        source = _Col()
        archived = _Col()

        def __init__(self, **kw):
            self.id = kw.get("id")
            for key, value in kw.items():
                setattr(self, key, value)

    class _Query:
        def filter(self, *_a, **_k):
            return self

        def first(self):
            return None

    class _Db:
        def query(self, _model):
            return _Query()

        def add(self, note):
            captured["note"] = note

        def commit(self):
            captured["committed"] = True

        def rollback(self):
            captured["rollback"] = True

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr("core.database.SessionLocal", lambda: _Db())
    monkeypatch.setattr("core.database.Note", FakeNote)

    data = {
        "status": "done",
        "query": "visual storytelling canvas",
        "raw_report": "# Canvas Report\n\n## Story beats\n## Operator loop\n",
        "owner": "tcam",
        "raw_findings": [],
    }
    note_id = create_research_followup_note("rp-abc123", data)
    assert note_id
    note = captured["note"]
    assert "/api/research/report/rp-abc123" in note.content
    assert "Canvas Report" in note.title or "Canvas Report" in note.content
    assert "brief" in (note.label or "")
    assert note.pinned is False
    assert note.source == "research"
    assert _is_directive_note({
        "label": note.label,
        "note_type": note.note_type,
        "archived": False,
        "pinned": False,
    })


def test_create_followup_note_skips_non_done():
    assert create_research_followup_note("rp-abc123", {"status": "error", "query": "q"}) is None


def test_save_result_creates_followup_note(tmp_path, monkeypatch):
    data_dir = tmp_path / "deep_research"
    data_dir.mkdir()
    monkeypatch.setattr(rh, "RESEARCH_DATA_DIR", data_dir)
    called = {}

    def _fake_note(session_id, data):
        called["id"] = session_id
        called["url"] = research_report_url(session_id)
        called["title"] = data.get("query")
        return "note-1"

    monkeypatch.setattr(rh, "create_research_followup_note", _fake_note)
    monkeypatch.setattr("src.event_bus.fire_event", lambda *a, **k: None)
    monkeypatch.setattr("src.settings.load_settings", lambda: {"image_gen_enabled": False})

    handler = _handler()
    handler._save_result("rp-save1", {
        "query": "what is new in canvas tools",
        "status": "done",
        "result": "# Canvas tools\n\n## Finding A\n",
        "raw_report": "# Canvas tools\n\n## Finding A\n",
        "started_at": 1,
        "owner": "tcam",
    })
    saved = json.loads((data_dir / "rp-save1.json").read_text(encoding="utf-8"))
    assert saved["status"] == "done"
    assert called["id"] == "rp-save1"
    assert called["url"] == "/api/research/report/rp-save1"


def test_save_result_note_failure_does_not_block(tmp_path, monkeypatch):
    data_dir = tmp_path / "deep_research"
    data_dir.mkdir()
    monkeypatch.setattr(rh, "RESEARCH_DATA_DIR", data_dir)
    monkeypatch.setattr(rh, "create_research_followup_note", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr("src.event_bus.fire_event", lambda *a, **k: None)
    monkeypatch.setattr("src.settings.load_settings", lambda: {"image_gen_enabled": False})
    handler = _handler()
    handler._save_result("rp-save2", {
        "query": "q",
        "status": "done",
        "result": "r",
        "started_at": 1,
        "owner": "tcam",
    })
    assert (data_dir / "rp-save2.json").exists()


def test_list_recent_research_reports_owner_and_archived(tmp_path, monkeypatch):
    data_dir = tmp_path / "deep_research"
    data_dir.mkdir()
    monkeypatch.setattr(rh, "RESEARCH_DATA_DIR", data_dir)
    (data_dir / "rp-mine.json").write_text(json.dumps({
        "query": "mine",
        "status": "done",
        "owner": "tcam",
        "completed_at": 200,
        "raw_report": "# Mine Title\n",
    }), encoding="utf-8")
    (data_dir / "rp-other.json").write_text(json.dumps({
        "query": "other",
        "status": "done",
        "owner": "someone",
        "completed_at": 300,
    }), encoding="utf-8")
    (data_dir / "rp-old.json").write_text(json.dumps({
        "query": "archived",
        "status": "done",
        "owner": "tcam",
        "archived": True,
        "completed_at": 400,
    }), encoding="utf-8")
    rows = list_recent_research_reports(owner="tcam", limit=8)
    assert [r["id"] for r in rows] == ["rp-mine"]
    assert rows[0]["title"] == "Mine Title"
    assert rows[0]["url"] == "/api/research/report/rp-mine"
