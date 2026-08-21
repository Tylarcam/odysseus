"""Home dashboard aggregation and API."""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import core.database as cdb
from core.database import Document, Note
import routes.home_routes as home_routes
from services.home.cmd_center import build_cmd_center, build_notes_preview
from services.home.dashboard import (
    build_recent_projects,
    note_project_tags,
    project_from_document_content,
    project_name_from_value,
)
from services.home.kg_graph import build_globe_graph


def test_note_project_tags_splits_and_dedupes():
    assert note_project_tags("alpha beta alpha") == ["alpha", "beta"]
    assert note_project_tags("#odysseus handoff") == ["odysseus", "handoff"]
    assert note_project_tags("") == []


def test_project_name_from_path_uses_basename():
    assert project_name_from_value(r"C:\Users\tylar\code\odysseus") == "odysseus"
    assert project_name_from_value("my-project") == "my-project"


def test_project_from_document_frontmatter():
    content = "---\nproject: grant-grafter\nstatus: pending\n---\n\nBody"
    assert project_from_document_content(content) == "grant-grafter"


def test_build_recent_projects_orders_by_activity():
    now = datetime(2026, 6, 18, 12, 0, 0)
    notes = [
        {
            "id": "n1",
            "title": "Old alpha note",
            "label": "alpha",
            "archived": False,
            "updated_at": (now - timedelta(days=3)).isoformat(),
        },
        {
            "id": "n2",
            "title": "Fresh beta note",
            "label": "beta",
            "archived": False,
            "updated_at": now.isoformat(),
        },
        {
            "id": "n3",
            "title": "Also beta",
            "label": "beta",
            "archived": False,
            "updated_at": (now - timedelta(hours=1)).isoformat(),
        },
    ]
    documents = [
        {
            "id": "d1",
            "title": "Alpha spec",
            "content": "",
            "session_folder": "alpha",
            "archived": False,
            "updated_at": (now - timedelta(hours=2)).isoformat(),
        }
    ]
    result = build_recent_projects(notes, documents, project_limit=5, items_per_project=3)
    names = [p["name"] for p in result["projects"]]
    assert names[0] == "beta"
    assert names[1] == "alpha"
    beta_items = result["projects"][0]["items"]
    assert beta_items[0]["id"] == "n2"
    assert len(beta_items) == 2


def test_recent_projects_route_queries_owner_scoped_rows(monkeypatch, tmp_path):
    """Route logic: notes + documents for the current user feed the aggregator."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'home2.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(home_routes, "SessionLocal", session_factory)

    db = session_factory()
    now = datetime.now()
    db.add(
        Note(
            id=str(uuid.uuid4()),
            owner="alice",
            title="Dashboard note",
            label="odysseus",
            archived=False,
            updated_at=now,
        )
    )
    db.add(
        Document(
            id=str(uuid.uuid4()),
            owner="alice",
            title="Dashboard doc",
            current_content="---\nproject: odysseus\n---\n",
            is_active=True,
            archived=False,
            updated_at=now,
        )
    )
    db.commit()
    db.close()

    db = session_factory()
    try:
        notes = [
            {
                "id": n.id,
                "title": n.title,
                "content": n.content,
                "label": n.label,
                "note_type": n.note_type,
                "archived": n.archived,
                "updated_at": n.updated_at.isoformat() if n.updated_at else None,
            }
            for n in db.query(Note).filter(Note.owner == "alice").all()
        ]
        documents = [
            {
                "id": doc.id,
                "title": doc.title,
                "content": doc.current_content,
                "language": doc.language,
                "archived": bool(doc.archived),
                "session_folder": None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
            for doc in db.query(Document).filter(Document.owner == "alice").all()
        ]
    finally:
        db.close()

    data = build_recent_projects(notes, documents)
    assert data["project_count"] == 1
    assert data["projects"][0]["name"] == "odysseus"
    assert len(data["projects"][0]["items"]) == 2


def test_build_cmd_center_maps_live_odysseus_surfaces():
    notes = [
        {
            "id": "n1",
            "title": "Morning brief",
            "label": "digest",
            "pinned": True,
            "note_type": "note",
            "archived": False,
            "updated_at": "2026-07-03T12:00:00",
        },
        {
            "id": "n2",
            "title": "Plan today",
            "label": "plan",
            "items": [{"text": "Ship CMD Center", "done": False}],
            "note_type": "checklist",
            "archived": False,
            "updated_at": "2026-07-03T11:00:00",
        },
    ]
    documents = [
        {
            "id": "d1",
            "title": "Spec.md",
            "content": "x" * 2048,
            "language": "markdown",
            "archived": False,
            "updated_at": "2026-07-03T10:00:00",
        }
    ]
    tasks = [{"id": "t1", "name": "Daily digest", "status": "active", "schedule": "daily"}]
    sessions = [{"id": "s1", "title": "Agent session", "last_message_at": "2026-07-03T09:00:00"}]
    handoffs = {
        "needs_attention": [
            {
                "id": "h1",
                "title": "Relay to Cursor",
                "handoff_target": "cursor",
                "handoff_doc_id": "doc-1",
                "updated_at": "2026-07-03T08:00:00",
            }
        ],
        "counts": {"needs_attention": 1, "in_progress": 0},
    }
    jobs = {
        "ready_to_apply_count": 2,
        "needs_review_count": 1,
        "ready_to_apply": [{"id": "j1", "company": "Acme", "role": "Engineer"}],
        "needs_review": [{"id": "j2", "company": "Beta", "role": "PM"}],
        "headline": "2 job(s) ready to apply",
        "summary_lines": ["2 job(s) ready to apply"],
    }

    data = build_cmd_center(
        notes=notes,
        documents=documents,
        tasks=tasks,
        sessions=sessions,
        handoffs=handoffs,
        jobs=jobs,
    )

    assert data["title"] == "V.A.U.L.T."
    assert data["counts"]["notes"] == 2
    assert data["counts"]["documents"] == 1
    assert data["counts"]["handoffs_attention"] == 1
    assert data["counts"]["jobs_ready"] == 2
    assert any(v["id"] == "notes" for v in data["vitals"])
    assert any(d["id"] == "n1" for d in data["directives"])
    assert data["documents"][0]["id"] == "d1"
    assert data["documents"][0]["tag"] == "MD"
    assert any(n["id"] == "n1" for n in data["notes_preview"])
    assert data["notes_preview"][0]["action"] == "open_note"
    assert any(c["id"] == "morning_report" for c in data["stage_cards"])
    assert len(data["stage_cards"]) == 5
    assert all("branch" in c for c in data["stage_cards"])
    assert any(c["id"] == "up_next" for c in data["stage_cards"])
    assert not any(c["id"] == "metrics_pull" for c in data["stage_cards"])
    assert any(c["id"] == "plan_today" for c in data["stage_cards"])
    assert not any(c.get("id") == "s_sync" for c in data.get("suggested_commands") or [])
    assert data["hero"]["value"] == 1
    assert data["hero"]["unit"] == "HANDOFFS"
    assert data["hero"].get("explain")
    assert data["hero"].get("cta_label")
    assert data.get("priority_queue")
    assert data.get("branch_health")
    assert len(data["branch_health"]) >= 8
    assert data["priority_queue"][0]["kind"] == "handoff"
    assert any(c["action"] == "plan_today" for c in data["commands"])
    assert any(c["action"] == "relay_watcher" for c in data["commands"])
    assert not any(c["action"] == "start_clicky" for c in data["commands"])
    assert any("NOTE ·" in w["text"] for w in data["wire"])
    assert data["wire"][0].get("branch")
    assert "Esc dismisses vault" in (data["audio"].get("hint") or "")
    assert data["jobs_detail"]["ready_to_apply"][0]["id"] == "j1"
    assert data["jobs_detail"]["needs_review"][0]["id"] == "j2"
    assert data.get("comms_preview") == []

    graph = data.get("globe_graph") or {}
    assert graph.get("nodes")
    assert graph.get("edges") is not None
    assert graph["meta"]["mempalace"] in ("skipped", "disabled", "ok", "unavailable", "empty")
    kinds = {n["kind"] for n in graph["nodes"]}
    assert "urgent" in kinds
    urgent_ids = {n["id"] for n in graph["nodes"] if n["kind"] == "urgent"}
    assert "handoff:h1" in urgent_ids


def test_cmd_center_intel_includes_research_on_wire(monkeypatch):
    reports = [{
        "id": "rp-abc",
        "title": "Visual Storytelling Canvas",
        "query": "visual storytelling canvas",
        "status": "done",
        "completed_at_iso": "2026-08-18T12:00:00+00:00",
        "url": "/api/research/report/rp-abc",
        "bullets": ["Story beats beat decks"],
    }]
    monkeypatch.setattr(
        "services.home.cmd_center.list_recent_research_reports",
        lambda **_k: reports,
    )
    data = build_cmd_center(
        notes=[],
        documents=[{
            "id": "d1",
            "title": "Spec.md",
            "content": "x",
            "language": "markdown",
            "archived": False,
            "updated_at": "2026-08-18T10:00:00",
        }],
        tasks=[],
        sessions=[],
        include_globe=False,
    )
    intel = next(b for b in data["branch_health"] if b["id"] == "intel")
    assert intel["count"] >= 2
    assert "report" in (intel["summary"] or "").lower()
    assert any(w["text"].startswith("RESEARCH ·") for w in data["wire"])
    assert any("Visual Storytelling Canvas" in (w["text"] or "") for w in data["wire"])
    blob = " ".join(line.get("text") or "" for line in (data.get("brief_script") or []))
    assert "Visual Storytelling Canvas" in blob


def test_signal_registry_assigns_one_primary_slot_per_item():
    """vault-signal-priority: exactly one CTA slot per directive item."""
    notes = [
        {
            "id": "n1",
            "title": "Overdue reminder",
            "pinned": True,
            "archived": False,
            "updated_at": "2026-07-03T12:00:00",
        },
    ]
    handoffs = {
        "needs_attention": [
            {
                "id": "h1",
                "title": "Relay to Cursor",
                "handoff_target": "cursor",
                "updated_at": "2026-07-03T08:00:00",
            }
        ],
        "counts": {"needs_attention": 1, "in_progress": 0},
    }
    jobs = {
        "ready_to_apply_count": 1,
        "needs_review_count": 0,
        "ready_to_apply": [{"id": "j1", "company": "Acme", "role": "Engineer"}],
        "needs_review": [],
    }

    data = build_cmd_center(
        notes=notes, documents=[], tasks=[], sessions=[], handoffs=handoffs, jobs=jobs,
    )

    hero_key = data["hero"].get("dedup_key")
    assert hero_key == "handoff:h1"

    queue = data["priority_queue"]
    primary_items = [i for i in queue if i.get("primary_slot") == "hero"]
    assert len(primary_items) == 1
    assert primary_items[0]["dedup_key"] == hero_key
    for item in queue:
        if item is not primary_items[0]:
            assert item.get("primary_slot") != "hero"

    # The stage card representing the same handoff is flagged primary; the
    # note's stage card (a different item) is not.
    agent_relay = next(c for c in data["stage_cards"] if c["id"] == "agent_relay")
    assert agent_relay.get("dedup_key") == hero_key
    assert agent_relay.get("primary") is True

    note_item = next(i for i in queue if i["kind"] == "note")
    note_card = next(
        (c for c in data["stage_cards"] if c.get("dedup_key") == note_item.get("dedup_key")),
        None,
    )
    if note_card:
        assert note_card.get("primary") is False


def test_signal_registry_never_filters_priority_queue():
    """vault-signal-priority: dedup only trims duplicate CTAs, never the queue."""
    notes = [
        {
            "id": f"n{i}",
            "title": f"Pinned {i}",
            "pinned": True,
            "archived": False,
            "updated_at": f"2026-07-0{i}T12:00:00",
        }
        for i in range(1, 5)
    ]
    handoffs = {
        "needs_attention": [
            {"id": "h1", "title": "Relay", "handoff_target": "cursor", "updated_at": "2026-07-03T08:00:00"}
        ],
        "counts": {"needs_attention": 1, "in_progress": 0},
    }

    data = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[], handoffs=handoffs)

    queue = data["priority_queue"]
    hero_key = data["hero"].get("dedup_key")
    # The item suppressed from suggested_commands (dedup_key == hero) is
    # still present, unfiltered, in priority_queue.
    assert any(i.get("dedup_key") == hero_key for i in queue)
    assert not any(
        c.get("action") == data["hero"].get("action") for c in data.get("suggested_commands") or []
    )
    # Queue reflects every directive-worthy item (1 handoff + 4 pinned notes) —
    # the registry never trims the queue itself.
    assert len(queue) == 5


def test_payload_hash_stable_for_identical_input():
    """vault-live-sync-efficiency: identical data hashes identically."""
    notes = [{"id": "n1", "title": "Note", "archived": False, "updated_at": "2026-07-03T12:00:00"}]
    data1 = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[])
    data2 = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[])
    assert data1["payload_hash"] == data2["payload_hash"]


def test_payload_hash_changes_with_data():
    """vault-live-sync-efficiency: a real data change produces a different hash."""
    base_note = {"id": "n1", "title": "Note", "archived": False, "updated_at": "2026-07-03T12:00:00"}
    data1 = build_cmd_center(notes=[dict(base_note)], documents=[], tasks=[], sessions=[])
    note2 = dict(base_note, due_date="2026-08-01T00:00:00")
    data2 = build_cmd_center(notes=[note2], documents=[], tasks=[], sessions=[])
    assert data1["payload_hash"] != data2["payload_hash"]


def test_include_globe_false_skips_mempalace_and_omits_key(monkeypatch):
    """vault-live-sync-efficiency: include_globe=False skips the MemPalace
    fetch entirely and omits globe_graph rather than sending it empty."""
    import services.home.cmd_center as cmd_center_module

    calls = []

    def fake_fetch():
        calls.append(1)
        return [], [], "skipped"

    monkeypatch.setattr(cmd_center_module, "fetch_mempalace_globe_graph", fake_fetch)

    notes = [{"id": "n1", "title": "Note", "archived": False, "updated_at": "2026-07-03T12:00:00"}]
    data = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[], include_globe=False)
    assert "globe_graph" not in data
    assert calls == []

    data2 = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[], include_globe=True)
    assert "globe_graph" in data2
    assert calls == [1]


def test_cmd_center_vault_timeouts_fit_request_hard_limit():
    """Vault Sync CalDAV + IMAP caps must fit under the 45s request timeout."""
    from routes.home_routes import _VAULT_CALDAV_TIMEOUT_SEC, _VAULT_INBOX_TIMEOUT_SEC

    assert _VAULT_CALDAV_TIMEOUT_SEC + _VAULT_INBOX_TIMEOUT_SEC < 45
    with open(home_routes.__file__, encoding="utf-8") as f:
        src = f.read()
    assert "include_inbox" in src
    assert "COMMS inbox preview timed out" in src
    assert "CalDAV sync timed out during vault refresh" in src


def test_cmd_center_hud_client_url_skips_globe_and_inbox():
    """HUD first paint and poll must request include_globe=0 (and include_inbox=0).

    Full cmd-center (globe + inbox) 504s on the 45s proxy timeout; Money Move
    lives on the light GET. Globe/inbox/CalDAV hydrate after paint, not on the HUD URL.
    """
    cmd_js = (Path(__file__).resolve().parents[1] / "static" / "js" / "cmdCenter.js").read_text(
        encoding="utf-8"
    )
    assert "/api/home/cmd-center?include_globe=0&include_inbox=0" in cmd_js
    fetch_fn = cmd_js[cmd_js.index("async function _fetchData") : cmd_js.index("async function _hydrateGlobeAndInbox")]
    assert "params.set('include_globe', includeGlobe ? '1' : '0')" in fetch_fn
    assert "params.set('include_inbox', includeInbox ? '1' : '0')" in fetch_fn
    assert "if (syncCalendar) params.set('sync_calendar', '1')" in fetch_fn
    # Regression: flags used to be inside `if (live)` so first paint hung.
    assert "if (live)" not in fetch_fn.replace("if (live && _data?.payload_hash)", "")
    assert "void _hydrateGlobeAndInbox()" in cmd_js

    open_fn = cmd_js[cmd_js.index("export async function openCmdCenter") : cmd_js.index("export function minimizeCmdCenter")]
    assert "await _fetchData();" in open_fn
    assert "syncCalendar: true" not in open_fn
    assert "void _hydrateCalendar()" in open_fn
    assert "void _hydrateGlobeAndInbox()" in open_fn

    hydrate_cal = cmd_js[cmd_js.index("async function _hydrateCalendar") : cmd_js.index("function _renderVitals")]
    assert "params.set('sync_calendar', '1')" in hydrate_cal
    assert "_mergeCalendarSurfaces" in hydrate_cal

    # Explicit Vault Sync still blocks on CalDAV; live poll does not.
    assert "await _fetchData({ syncCalendar: true });" in cmd_js
    assert "await _fetchData({ live: true })" in cmd_js


def test_build_notes_preview_newest_first_with_preview_text():
    notes = [
        {
            "id": "older",
            "title": "Older",
            "content": "First line older\nmore",
            "label": "alpha",
            "updated_at": "2026-07-01T10:00:00",
        },
        {
            "id": "newer",
            "title": "Newer",
            "content": "First line newer",
            "pinned": True,
            "updated_at": "2026-07-03T12:00:00",
        },
    ]
    preview = build_notes_preview(notes)
    assert [p["id"] for p in preview] == ["newer", "older"]
    assert preview[0]["preview"] == "First line newer"
    assert preview[0]["pinned"] is True
    assert preview[0]["action"] == "open_note"
    assert preview[0]["tags"] == []


def test_build_notes_preview_respects_limit_and_label_tags():
    notes = [
        {"id": f"n{i}", "title": f"N{i}", "updated_at": f"2026-07-0{i}T12:00:00", "label": "tag"}
        for i in range(1, 20)
    ]
    preview = build_notes_preview(notes, limit=5)
    assert len(preview) == 5
    assert preview[0]["tags"] == ["tag"]


def test_cmd_center_route_payload_includes_notes_preview(monkeypatch, tmp_path):
    """Route wiring: owner-scoped notes feed build_cmd_center → notes_preview."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'cmd_center.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(home_routes, "SessionLocal", session_factory)

    db = session_factory()
    now = datetime.now(timezone.utc)
    db.add(
        Note(
            id="rail-note-1",
            owner="alice",
            title="MEM rail note",
            content="Preview body line",
            label="mem",
            pinned=True,
            archived=False,
            updated_at=now,
        )
    )
    db.commit()
    db.close()

    db = session_factory()
    try:
        from src.auth_helpers import owner_filter

        user = "alice"
        note_q = db.query(Note).filter(Note.archived == False)  # noqa: E712
        note_q = owner_filter(note_q, Note, user)
        notes = [home_routes._note_row_to_cmd(n) for n in note_q.all()]
    finally:
        db.close()

    data = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[], owner=user)
    assert data["counts"]["notes"] == 1
    assert len(data["notes_preview"]) == 1
    assert data["notes_preview"][0]["id"] == "rail-note-1"
    assert data["notes_preview"][0]["preview"] == "Preview body line"
    assert data["notes_preview"][0]["target_id"] == "rail-note-1"


def test_build_comms_preview_from_email_urgency():
    from services.home.cmd_center import _build_comms_preview

    preview = _build_comms_preview({
        "per_uid": {
            "acc:1": {"subject": "Interview", "from": "hr@co.com", "score": 3, "reason": "Reply today"},
            "acc:2": {"subject": "Newsletter", "from": "news@co.com", "score": 0},
        },
    })
    assert len(preview) == 2
    assert preview[0]["subject"] == "Interview"
    assert preview[0]["urgent"] is True
    assert preview[0]["action"] == "email"

    data = build_cmd_center(
        notes=[],
        documents=[],
        tasks=[],
        sessions=[],
        email_urgency={
            "total_unread": 2,
            "total_urgent": 1,
            "per_uid": {
                "acc:1": {"subject": "Interview", "from": "hr@co.com", "score": 3},
            },
        },
    )
    assert len(data["comms_preview"]) == 1
    comms = next(b for b in data["branch_health"] if b["id"] == "comms")
    assert comms["count"] == 2
    assert comms["state"] == "busy"


def test_build_comms_preview_from_live_inbox():
    from services.home.cmd_center import _build_comms_preview

    inbox = [
        {
            "uid": "42",
            "subject": "Standup notes",
            "from_name": "Alex",
            "from_address": "alex@example.com",
            "is_read": False,
            "date_epoch": 1700000000.0,
        },
        {
            "uid": "41",
            "subject": "Receipt",
            "from_name": "Store",
            "from_address": "store@example.com",
            "is_read": True,
            "date_epoch": 1699990000.0,
        },
    ]
    preview = _build_comms_preview({}, inbox, "acct-1")
    assert len(preview) == 2
    assert preview[0]["subject"] == "Standup notes"
    assert preview[0]["id"] == "acct-1:42"
    assert preview[0]["is_read"] is False
    assert preview[0]["urgent"] is False

    data = build_cmd_center(
        notes=[],
        documents=[],
        tasks=[],
        sessions=[],
        inbox_emails=inbox,
        inbox_account_id="acct-1",
    )
    assert len(data["comms_preview"]) == 2
    comms = next(b for b in data["branch_health"] if b["id"] == "comms")
    assert comms["count"] == 1
    assert comms["summary"] == "1 unread"


def test_build_comms_preview_merges_inbox_with_urgency():
    from services.home.cmd_center import _build_comms_preview

    inbox = [{
        "uid": "7",
        "subject": "Offer letter",
        "from_name": "HR",
        "from_address": "hr@co.com",
        "is_read": False,
        "date_epoch": 1700000100.0,
    }]
    preview = _build_comms_preview(
        {"per_uid": {"acct:7": {"score": 3, "reason": "Reply today", "from": "hr@co.com"}}},
        inbox,
        "acct",
    )
    assert len(preview) == 1
    assert preview[0]["urgent"] is True
    assert preview[0]["reason"] == "Reply today"
    assert preview[0]["score"] == 3


def test_build_cmd_center_up_next_card_prefers_calendar_event():
    now = datetime.now(timezone.utc)
    calendar_events = [
        {"uid": "evt-1", "title": "Standup", "start": (now + timedelta(minutes=45)).isoformat()},
    ]
    data = build_cmd_center(
        notes=[],
        documents=[],
        tasks=[],
        sessions=[],
        calendar_events=calendar_events,
    )
    up_next = next(c for c in data["stage_cards"] if c["id"] == "up_next")
    assert "Standup" in up_next["subtitle"]
    assert up_next["action"] == "calendar"
    assert up_next["target_id"] == "evt-1"
    assert data["agenda"]["next_event"]["uid"] == "evt-1"
    assert data["agenda"]["today_events"] >= 1

    graph = data["globe_graph"]
    event_nodes = [n for n in graph["nodes"] if n["id"] == "event:evt-1"]
    assert event_nodes
    assert event_nodes[0]["tone"] == "scheduled"
    assert event_nodes[0]["action"] == "calendar"


def test_build_cmd_center_up_next_card_falls_back_to_due_note_then_task():
    now = datetime.now(timezone.utc)
    notes = [
        {
            "id": "n-due-soon",
            "title": "Send invoice",
            "due_date": (now + timedelta(hours=2)).isoformat(),
            "archived": False,
            "updated_at": now.isoformat(),
        }
    ]
    data = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[])
    up_next = next(c for c in data["stage_cards"] if c["id"] == "up_next")
    assert "Send invoice" in up_next["subtitle"]
    assert up_next["action"] == "open_note"
    assert up_next["target_id"] == "n-due-soon"

    tasks = [
        {
            "id": "t-next",
            "name": "Nightly sync",
            "status": "active",
            "schedule": "daily",
            "next_run": (now + timedelta(hours=6)).isoformat(),
        }
    ]
    data2 = build_cmd_center(notes=[], documents=[], tasks=tasks, sessions=[])
    up_next2 = next(c for c in data2["stage_cards"] if c["id"] == "up_next")
    assert "Nightly sync" in up_next2["subtitle"]
    assert up_next2["action"] == "open_task"
    assert up_next2["target_id"] == "t-next"

    data3 = build_cmd_center(notes=[], documents=[], tasks=[], sessions=[])
    up_next3 = next(c for c in data3["stage_cards"] if c["id"] == "up_next")
    assert up_next3["subtitle"] == "Nothing scheduled"


def test_build_cmd_center_bumps_overdue_note_urgency():
    now = datetime.now(timezone.utc)
    notes = [
        {
            "id": "n-overdue",
            "title": "Overdue reminder",
            "due_date": (now - timedelta(hours=3)).isoformat(),
            "archived": False,
            "updated_at": now.isoformat(),
        }
    ]
    data = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[])
    entry = next(i for i in data["priority_queue"] if i["id"] == "n-overdue")
    assert entry["urgency"] == 85
    assert entry["status"] == "overdue"
    assert "OVERDUE" in (entry.get("due_label") or "")
    assert "T" not in (entry.get("due_label") or "")  # no raw ISO in chip
    assert data["agenda"]["overdue"][0]["id"] == "n-overdue"
    assert data["hero"]["unit"] == "OVERDUE"
    assert data["hero"]["value"] >= 1
    assert data.get("brief_script")
    assert any(line.get("highlight", {}).get("type") == "overdue" for line in data["brief_script"])
    directive = next(d for d in data["directives"] if d["id"] == "n-overdue")
    assert directive["due_label"] == entry["due_label"]
    assert directive["status"] == "overdue"
    assert data.get("attention_stack")
    assert data["attention_stack"][0]["id"] == "n-overdue"
    assert data["attention_stack"][0]["status"] == "overdue"


def test_attention_stack_includes_pinned_and_due_notes():
    """OPEN DIRECTIVE stack = all directive notes, not overdue-only."""
    now = datetime.now(timezone.utc)
    notes = [
        {
            "id": "n-pinned",
            "title": "Pinned directive",
            "pinned": True,
            "archived": False,
            "updated_at": now.isoformat(),
        },
        {
            "id": "n-due",
            "title": "Due tomorrow",
            "due_date": (now + timedelta(days=1)).isoformat(),
            "archived": False,
            "updated_at": now.isoformat(),
        },
        {
            "id": "n-plain",
            "title": "Plain note should not triage",
            "archived": False,
            "updated_at": now.isoformat(),
        },
    ]
    data = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[])
    stack_ids = {i["id"] for i in data["attention_stack"]}
    assert "n-pinned" in stack_ids
    assert "n-due" in stack_ids
    assert "n-plain" not in stack_ids
    assert data["hero"]["cta_label"] == "Open directive"


def test_attention_stack_ranks_handoffs_before_overdue_notes():
    now = datetime.now(timezone.utc)
    notes = [
        {
            "id": "n-overdue",
            "title": "Overdue reminder",
            "due_date": (now - timedelta(days=2)).isoformat(),
            "archived": False,
            "updated_at": now.isoformat(),
        }
    ]
    handoffs = {
        "needs_attention": [
            {
                "id": "h1",
                "title": "Relay to Cursor",
                "handoff_target": "cursor",
                "updated_at": now.isoformat(),
            }
        ],
        "counts": {"needs_attention": 1, "in_progress": 0},
    }
    data = build_cmd_center(notes=notes, documents=[], tasks=[], sessions=[], handoffs=handoffs)
    stack = data["attention_stack"]
    assert stack[0]["kind"] == "handoff"
    assert any(i["id"] == "n-overdue" for i in stack)


def test_build_globe_graph_projects_agent_and_scheduled():
    now = datetime(2026, 7, 3, 12, 0, 0)
    notes = [
        {
            "id": "n-due",
            "title": "Deadline note",
            "due_date": "2026-07-10",
            "archived": False,
            "updated_at": now.isoformat(),
        },
        {
            "id": "n1",
            "title": "Alpha work",
            "label": "alpha",
            "archived": False,
            "updated_at": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "id": "n2",
            "title": "Beta work",
            "label": "beta",
            "archived": False,
            "updated_at": now.isoformat(),
        },
    ]
    documents = [
        {
            "id": "d1",
            "title": "Beta spec",
            "session_folder": "beta",
            "archived": False,
            "updated_at": now.isoformat(),
        }
    ]
    projects = build_recent_projects(notes, documents)
    tasks = [
        {"id": "t1", "name": "Nightly digest", "status": "active", "schedule": "0 6 * * *"},
    ]
    agent_activity = [
        {
            "id": "run-1",
            "agent": "Swarm-01",
            "status": "running",
            "text": "⋯ indexing",
            "swarm": True,
            "ts": now.isoformat(),
            "action": "open_task",
            "target_id": "swarm-1",
        }
    ]
    priority_queue = [
        {
            "id": "j2",
            "kind": "job",
            "title": "Beta — PM",
            "subtitle": "Agency · needs review",
            "branch": "agency",
            "urgency": 95,
            "action": "jobs",
            "target_id": "j2",
            "ts": now.isoformat(),
        }
    ]

    graph = build_globe_graph(
        notes=notes,
        documents=documents,
        tasks=tasks,
        handoffs={"needs_attention": [], "counts": {}},
        priority_queue=priority_queue,
        agent_activity=agent_activity,
        projects=projects,
    )

    nodes = {n["id"]: n for n in graph["nodes"]}
    project_nodes = [n for n in graph["nodes"] if n["kind"] == "project"]
    assert project_nodes
    assert project_nodes[0]["kind"] == "project"
    assert project_nodes[0]["tone"] == "bright"
    assert project_nodes[0]["size"] >= project_nodes[-1]["size"] or len(project_nodes) == 1

    assert "agent:run-1" in nodes
    assert nodes["agent:run-1"]["tone"] == "agent"
    assert nodes["agent:run-1"]["branch"] == "mycelia"

    assert "task:t1" in nodes
    assert nodes["task:t1"]["tone"] == "scheduled"

    assert "note:n-due" in nodes
    assert nodes["note:n-due"]["tone"] == "urgent"

    assert any(e["kind"] == "run" for e in graph["edges"])


def test_today_plan_surfaces_stale_daily_brief_above_low_noise():
    """PLAN TODAY must not bury fat/stale briefs under low-urgency noise."""
    from datetime import date

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    items = [{"text": f"Item {i}", "done": False} for i in range(38)]
    notes = [
        {
            "id": "brief-stale",
            "title": f"Daily Brief — {yesterday} (Thursday)",
            "items": items,
            "note_type": "checklist",
            "archived": False,
            "updated_at": f"{yesterday}T12:00:00+00:00",
        },
        {
            "id": "n-noise",
            "title": "Random checklist",
            "items": [{"text": "one", "done": False}],
            "note_type": "checklist",
            "archived": False,
            "updated_at": "2026-07-31T08:00:00+00:00",
        },
    ]
    data = build_cmd_center(
        notes=notes,
        documents=[],
        tasks=[],
        sessions=[],
        handoffs={"needs_attention": [], "counts": {"needs_attention": 0, "in_progress": 0}},
        jobs={
            "ready_to_apply_count": 0,
            "needs_review_count": 0,
            "ready_to_apply": [],
            "needs_review": [],
            "headline": "",
            "summary_lines": [],
        },
    )
    plan = data.get("today_plan") or {}
    assert plan.get("summary", {}).get("stale", 0) >= 1
    assert plan.get("summary", {}).get("open_items", 0) >= 38
    assert plan["items"][0]["id"] == "brief-stale"
    assert plan["items"][0]["band"] == "stale"

    note_rows = [i for i in data["priority_queue"] if i.get("kind") == "note"]
    assert note_rows
    assert note_rows[0]["id"] == "brief-stale"
    assert note_rows[0]["urgency"] >= 86
    assert any(c["action"] == "plan_today" for c in data["stage_cards"] if c["id"] == "plan_today")


def test_jobs_for_brief_counts_uncapped_above_display_limit(monkeypatch, tmp_path):
    """AGENCY undercount fix: ready/review counts must not follow the limit=5 list cap."""
    from src.job_pipeline.brief import get_jobs_for_brief
    from src.job_pipeline.store import create_job_record

    engine = create_engine(
        f"sqlite:///{tmp_path / 'jobs-brief-uncapped.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.store.SessionLocal", session_factory)

    for i in range(7):
        create_job_record(
            owner="alice",
            status="ready_to_apply",
            terminal_status="ready_to_apply",
            company=f"Ready Co {i}",
            role="Engineer",
        )
    for i in range(6):
        create_job_record(
            owner="alice",
            status="needs_review",
            terminal_status="needs_review",
            company=f"Review Co {i}",
            role="PM",
        )

    brief = get_jobs_for_brief(owner="alice", limit=5)
    assert brief["ready_to_apply_count"] == 7
    assert brief["needs_review_count"] == 6
    assert len(brief["ready_to_apply"]) == 5
    assert len(brief["needs_review"]) == 5

    data = build_cmd_center(
        notes=[],
        documents=[],
        tasks=[],
        sessions=[],
        handoffs={"needs_attention": [], "counts": {"needs_attention": 0, "in_progress": 0}},
        jobs=brief,
    )
    assert data["counts"]["jobs_ready"] == 7
    agency = next(b for b in data["branch_health"] if b["id"] == "agency")
    assert agency["count"] == 13


# --- cmd-center-active-systems phase 3 (CORE lineage + stalled-chain) ----------


def _lineage_session(monkeypatch, tmp_path, name: str = "phase3"):
    engine = create_engine(
        f"sqlite:///{tmp_path / f'{name}.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("core.lineage.SessionLocal", session_factory)
    return session_factory


def test_priority_queue_attaches_related_to_one_hop(monkeypatch, tmp_path):
    """3.1 — handoff queue row includes related_to job from batched lineage."""
    from core.lineage import record_lineage_edge
    from services.home.cmd_center import _build_priority_queue

    _lineage_session(monkeypatch, tmp_path, "pq-related")
    assert record_lineage_edge(
        source_kind="job",
        source_id="j-spawn",
        target_kind="handoff",
        target_id="h-child",
        relation="materialized",
    )

    now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)
    queue = _build_priority_queue(
        notes_list=[],
        active_tasks=[],
        handoffs={
            "needs_attention": [
                {
                    "id": "h-child",
                    "title": "Relay from job",
                    "handoff_target": "cursor",
                    "handoff_at": now.isoformat(),
                }
            ],
            "in_progress": [],
            "counts": {},
        },
        jobs={
            "needs_review": [
                {
                    "id": "j-spawn",
                    "company": "SpawnCo",
                    "role": "Eng",
                    "updated_at": now.isoformat(),
                }
            ],
            "ready_to_apply": [],
        },
        now=now,
    )
    by_id = {i["id"]: i for i in queue}
    assert by_id["h-child"]["related_to"] == [{"kind": "job", "id": "j-spawn"}]
    assert by_id["j-spawn"]["related_to"] == [{"kind": "handoff", "id": "h-child"}]


def test_priority_queue_related_to_empty_without_lineage(monkeypatch, tmp_path):
    """Pre-capability objects get related_to: [] (no fuzzy backfill)."""
    from services.home.cmd_center import _build_priority_queue

    _lineage_session(monkeypatch, tmp_path, "pq-empty")
    now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)
    queue = _build_priority_queue(
        notes_list=[],
        active_tasks=[],
        handoffs={
            "needs_attention": [
                {
                    "id": "h-orphan",
                    "title": "Old handoff",
                    "handoff_target": "cursor",
                    "handoff_at": now.isoformat(),
                }
            ],
            "in_progress": [],
            "counts": {},
        },
        jobs={"needs_review": [], "ready_to_apply": []},
        now=now,
    )
    row = next(i for i in queue if i["id"] == "h-orphan")
    assert row["related_to"] == []


def test_stalled_job_surfaces_independent_of_healthy_handoff(monkeypatch, tmp_path):
    """3.3 — stalled needs_review job escalates even when its handoff looks fine."""
    from core.lineage import record_lineage_edge
    from services.home.cmd_center import _build_priority_queue
    from services.home.stalled import STALLED_SLA

    _lineage_session(monkeypatch, tmp_path, "pq-stalled-chain")
    assert record_lineage_edge(
        source_kind="job",
        source_id="j-stale",
        target_kind="handoff",
        target_id="h-fine",
        relation="materialized",
    )

    now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)
    days = STALLED_SLA["job_needs_review_days"]
    boost = int(STALLED_SLA["urgency_boost"])
    # Healthy handoff: not in needs_attention / not claimed-stuck — absent from queue.
    # Stalled job still surfaces at escalated urgency.
    queue = _build_priority_queue(
        notes_list=[],
        active_tasks=[],
        handoffs={
            "needs_attention": [],
            "in_progress": [
                {
                    "id": "h-fine",
                    "title": "Not-yet-due handoff",
                    "handoff_target": "cursor",
                    "handoff_relay_status": "queued",
                    "updated_at": now.isoformat(),
                }
            ],
            "counts": {"needs_attention": 0, "in_progress": 1},
        },
        jobs={
            "needs_review": [
                {
                    "id": "j-stale",
                    "company": "StaleCo",
                    "role": "PM",
                    "updated_at": (now - timedelta(days=days + 1)).isoformat(),
                }
            ],
            "ready_to_apply": [],
        },
        now=now,
    )
    assert not any(i["id"] == "h-fine" for i in queue)
    job_row = next(i for i in queue if i["id"] == "j-stale")
    assert job_row["stalled"]["reason"] == "needs_review_sla"
    assert job_row["urgency"] == 95 + boost
    assert job_row["related_to"] == [{"kind": "handoff", "id": "h-fine"}]


def test_stalled_chain_escalates_terminal_item_urgency(monkeypatch, tmp_path):
    """Healthy-looking terminal in the queue is raised to the stalled source floor."""
    from core.lineage import record_lineage_edge
    from services.home.cmd_center import _build_priority_queue
    from services.home.stalled import STALLED_SLA

    _lineage_session(monkeypatch, tmp_path, "pq-chain-escalate")
    assert record_lineage_edge(
        source_kind="job",
        source_id="j-stale",
        target_kind="note",
        target_id="n-due",
        relation="materialized",
    )

    now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)
    days = STALLED_SLA["job_needs_review_days"]
    boost = int(STALLED_SLA["urgency_boost"])
    due_soon = (now + timedelta(hours=6)).isoformat()
    queue = _build_priority_queue(
        notes_list=[
            {
                "id": "n-due",
                "title": "Due reminder from job",
                "due_date": due_soon,
                "archived": False,
                "updated_at": now.isoformat(),
            }
        ],
        active_tasks=[],
        handoffs={"needs_attention": [], "in_progress": [], "counts": {}},
        jobs={
            "needs_review": [
                {
                    "id": "j-stale",
                    "company": "StaleCo",
                    "role": "PM",
                    "updated_at": (now - timedelta(days=days + 1)).isoformat(),
                }
            ],
            "ready_to_apply": [],
        },
        now=now,
    )
    by_id = {i["id"]: i for i in queue}
    assert by_id["j-stale"]["urgency"] == 95 + boost
    # Note alone would be ~80 (due); stalled job floor raises it.
    assert by_id["n-due"]["urgency"] >= by_id["j-stale"]["urgency"]
    assert by_id["n-due"]["related_to"] == [{"kind": "job", "id": "j-stale"}]


def test_build_globe_graph_adds_lineage_cross_object_edges(monkeypatch, tmp_path):
    """3.2 — globe draws an edge between two rendered nodes linked by lineage."""
    from core.lineage import record_lineage_edge

    _lineage_session(monkeypatch, tmp_path, "globe-lineage")
    assert record_lineage_edge(
        source_kind="note",
        source_id="n-src",
        target_kind="task",
        target_id="t-promoted",
        relation="promoted",
    )

    now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)
    notes = [
        {
            "id": "n-src",
            "title": "Source note",
            "due_date": "2026-08-01",
            "archived": False,
            "updated_at": now.isoformat(),
        }
    ]
    tasks = [
        {
            "id": "t-promoted",
            "name": "Promoted task",
            "status": "active",
            "schedule": "0 9 * * *",
            "updated_at": now.isoformat(),
        }
    ]
    graph = build_globe_graph(
        notes=notes,
        documents=[],
        tasks=tasks,
        handoffs={"needs_attention": [], "counts": {}},
        priority_queue=[],
        agent_activity=[],
        projects={},
    )
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "note:n-src" in node_ids
    assert "task:t-promoted" in node_ids
    lineage_edges = [
        e
        for e in graph["edges"]
        if e["kind"] == "promoted"
        and {e["source"], e["target"]} == {"note:n-src", "task:t-promoted"}
    ]
    assert len(lineage_edges) == 1
    # Branch→node edges still present alongside the cross-object edge.
    assert any(e["source"] == "branch:prod" and e["target"] == "note:n-src" for e in graph["edges"])
    assert any(
        e["source"] == "branch:prod" and e["target"] == "task:t-promoted" for e in graph["edges"]
    )


def test_build_globe_graph_no_lineage_edge_when_neighbor_not_rendered(monkeypatch, tmp_path):
    """Lineage edge is skipped when only one endpoint made the globe node set."""
    from core.lineage import record_lineage_edge

    _lineage_session(monkeypatch, tmp_path, "globe-partial")
    assert record_lineage_edge(
        source_kind="job",
        source_id="j-missing",
        target_kind="handoff",
        target_id="h-only",
        relation="materialized",
    )
    now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)
    graph = build_globe_graph(
        notes=[],
        documents=[],
        tasks=[],
        handoffs={
            "needs_attention": [
                {
                    "id": "h-only",
                    "title": "Alone handoff",
                    "handoff_target": "cursor",
                    "handoff_at": now.isoformat(),
                }
            ],
            "counts": {},
        },
        priority_queue=[],
        agent_activity=[],
        projects={},
    )
    assert any(n["id"] == "handoff:h-only" for n in graph["nodes"])
    assert not any(e["kind"] == "materialized" for e in graph["edges"])


# --- cmd-center-active-systems phase 6 (AGENCY funnel + lineage + stalled) -----


def test_agency_funnel_counts_match_job_pipeline_state(monkeypatch, tmp_path):
    """6.1/6.4 — funnel stage counts mirror JobRecord statuses."""
    from src.job_pipeline.brief import get_jobs_for_brief
    from src.job_pipeline.store import count_job_funnel_stages, create_job_record

    engine = create_engine(
        f"sqlite:///{tmp_path / 'agency-funnel.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    cdb.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cdb, "SessionLocal", session_factory)
    monkeypatch.setattr("src.job_pipeline.store.SessionLocal", session_factory)

    for status in ("email_received", "deduped", "normalized"):
        create_job_record(owner="alice", status=status, company="IngestCo", role="A")
    for status in ("evaluated", "tailoring_started", "needs_review"):
        create_job_record(
            owner="alice",
            status=status,
            terminal_status="needs_review" if status == "needs_review" else None,
            company="EvalCo",
            role="B",
        )
    create_job_record(
        owner="alice",
        status="ready_to_apply",
        terminal_status="ready_to_apply",
        company="ReadyCo",
        role="C",
    )
    create_job_record(
        owner="alice",
        status="applied",
        terminal_status="applied",
        company="AppliedCo",
        role="D",
    )
    # Out-of-funnel — must not inflate stage counts.
    create_job_record(owner="alice", status="archived", company="ArchivedCo", role="E")
    create_job_record(owner="alice", status="error", company="ErrCo", role="F")

    expected = {"ingested": 3, "evaluated": 3, "ready": 1, "applied": 1}
    assert count_job_funnel_stages(owner="alice") == expected

    brief = get_jobs_for_brief(owner="alice", limit=5)
    assert brief["funnel"] == expected

    data = build_cmd_center(
        notes=[],
        documents=[],
        tasks=[],
        sessions=[],
        handoffs={"needs_attention": [], "counts": {"needs_attention": 0, "in_progress": 0}},
        jobs=brief,
    )
    assert data["jobs_detail"]["funnel"] == expected


def test_agency_job_rows_include_related_to_handoff(monkeypatch, tmp_path):
    """6.2/6.4 — AGENCY job rows expose related_to when a handoff was materialized."""
    from core.lineage import record_lineage_edge

    _lineage_session(monkeypatch, tmp_path, "agency-related")
    assert record_lineage_edge(
        source_kind="job",
        source_id="j-ready",
        target_kind="handoff",
        target_id="h-from-job",
        relation="materialized",
    )

    data = build_cmd_center(
        notes=[],
        documents=[],
        tasks=[],
        sessions=[],
        handoffs={"needs_attention": [], "counts": {"needs_attention": 0, "in_progress": 0}},
        jobs={
            "ready_to_apply_count": 1,
            "needs_review_count": 0,
            "ready_to_apply": [
                {"id": "j-ready", "company": "Acme", "role": "Engineer", "status": "ready_to_apply"}
            ],
            "needs_review": [],
            "funnel": {"ingested": 0, "evaluated": 0, "ready": 1, "applied": 0},
            "headline": "1 job(s) ready to apply",
            "summary_lines": [],
        },
    )
    row = data["jobs_detail"]["ready_to_apply"][0]
    assert row["related_to"] == [{"kind": "handoff", "id": "h-from-job"}]
    assert data["jobs_detail"]["funnel"]["ready"] == 1


def test_agency_stalled_review_escalates_in_priority_queue():
    """6.3/6.4 — needs_review past SLA is flagged stalled at elevated urgency."""
    from services.home.cmd_center import _build_priority_queue
    from services.home.stalled import STALLED_SLA

    now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)
    days = STALLED_SLA["job_needs_review_days"]
    boost = int(STALLED_SLA["urgency_boost"])
    queue = _build_priority_queue(
        notes_list=[],
        active_tasks=[],
        handoffs={"needs_attention": [], "in_progress": [], "counts": {}},
        jobs={
            "needs_review": [
                {
                    "id": "j-stale-review",
                    "company": "SlowCo",
                    "role": "PM",
                    "attention": "needs_review",
                    "updated_at": (now - timedelta(days=days + 1)).isoformat(),
                }
            ],
            "ready_to_apply": [],
        },
        now=now,
    )
    row = next(i for i in queue if i["id"] == "j-stale-review")
    assert row["stalled"]["reason"] == "needs_review_sla"
    assert row["urgency"] == 95 + boost
    assert row["branch"] == "agency"


def _quiet_agency():
    return {
        "handoffs": {"needs_attention": [], "counts": {"needs_attention": 0, "in_progress": 0}},
        "jobs": {
            "ready_to_apply_count": 0,
            "needs_review_count": 0,
            "ready_to_apply": [],
            "needs_review": [],
            "headline": "",
            "summary_lines": [],
        },
    }


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


def test_cmd_center_full_picture_hero_is_directives_when_jobs_and_relay_quiet():
    """Default CORE hero stays the full-picture directive (Search as Code), not the money needle."""
    from services.documents.ceo_brief_store import date_label

    yesterday = date_label(datetime.now(timezone.utc) - timedelta(days=1))
    data = build_cmd_center(
        notes=[_search_as_code_note()],
        documents=[{
            "id": "ceo-stale",
            "title": f"CEO Brief — {yesterday}",
            "content": "Yesterday's ranking.",
            "language": "markdown",
            "archived": False,
            "updated_at": f"{yesterday}T09:00:00+00:00",
        }],
        tasks=[],
        sessions=[],
        include_globe=False,
        **_quiet_agency(),
    )
    assert data["hero"]["unit"] == "DIRECTIVES"
    assert "Search as Code" in (data["hero"].get("title") or "")
    assert len(data["stage_cards"]) == 5
    assert data["core_lenses"] == ["full_picture", "money_move"]
    assert data["money_hero"]["unit"] == "STALE"
    assert data["money_hero"]["action"] == "ceo_brief"


def test_cmd_center_money_hero_uses_brief_top3_without_replacing_default_hero():
    """Money Move lens reads the brief Top 3; full-picture hero stays on directives."""
    from services.documents.ceo_brief_store import date_label, canonical_title

    today = date_label()
    data = build_cmd_center(
        notes=[_search_as_code_note()],
        documents=[{
            "id": "ceo-today",
            "title": canonical_title(),
            "content": (
                f"# CEO Brief — {today}\n\n"
                "## Top 3 actions that move the needle\n"
                "1. Ship Loom pack `9ee7b1d6` — convert the demo\n"
                "2. Protect focus\n"
                "3. Capture inbound\n"
            ),
            "language": "markdown",
            "archived": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }],
        tasks=[],
        sessions=[],
        include_globe=False,
        **_quiet_agency(),
    )
    assert data["hero"]["unit"] == "DIRECTIVES"
    assert "Search as Code" in (data["hero"].get("title") or "")
    assert data["money_hero"]["unit"] == "TOP 3"
    assert "Loom" in (data["money_hero"].get("title") or "")
    assert len(data["stage_cards"]) == 5
    blob = " ".join(line.get("text") or "" for line in (data.get("brief_script") or []))
    assert "Loom" in blob
    assert "Top 3" in blob
    assert "Needs you" in blob
    assert "Can wait" in blob
    assert "Search as Code" not in blob
    assert "What changed" not in blob
